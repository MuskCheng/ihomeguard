"""爱快路由器本地 API 客户端

参考: https://blog.51cto.com/infrado/13378327
"""
import hashlib
import requests
from typing import Optional, List, Dict


class IKuaiLocalClient:
    """爱快路由器本地 API 客户端"""
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._sess_key = None
    
    def _md5(self, text: str) -> str:
        """计算 MD5"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def login(self) -> bool:
        """登录获取会话"""
        passwd_md5 = self._md5(self.password)
        
        try:
            login_url = f"{self.base_url}/Action/login"
            
            # 使用 JSON 格式登录
            resp = self.session.post(
                login_url,
                json={
                    "username": self.username,
                    "passwd": passwd_md5
                },
                timeout=10
            )
            
            print(f"[爱快] 登录请求: {login_url}", flush=True)
            print(f"[爱快] 响应状态: {resp.status_code}", flush=True)
            
            if resp.status_code == 200:
                result = resp.json()
                print(f"[爱快] 响应内容: {result}", flush=True)
                # 爱快成功码是 10000
                if result.get("Result") in [10000, 30000]:
                    self._sess_key = self.session.cookies.get('sess_key') or "logged_in"
                    print(f"[爱快] 登录成功", flush=True)
                    return True
                else:
                    print(f"[爱快] 登录失败: {result.get('ErrMsg', '未知错误')}", flush=True)
            else:
                print(f"[爱快] 登录请求失败: HTTP {resp.status_code}", flush=True)
        except Exception as e:
            print(f"[爱快] 登录异常: {e}", flush=True)
        return False
    
    def _ensure_login(self):
        """确保已登录"""
        # 每次调用前重新登录以确保会话有效
        if not self.login():
            raise Exception("登录失败")
    
    def _call(self, func_name: str, action: str, param: dict = None) -> dict:
        """调用 API"""
        self._ensure_login()
        
        body = {
            "func_name": func_name,
            "action": action,
            "param": param or {}
        }
        
        print(f"[爱快] API调用: {func_name}.{action}, body={body}", flush=True)
        
        # 爱快 API 端点是 /Action/call
        resp = self.session.post(
            f"{self.base_url}/Action/call",
            json=body,
            timeout=30
        )
        
        print(f"[爱快] API响应状态: {resp.status_code}", flush=True)
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"[爱快] API响应: {result}", flush=True)
            return result
        print(f"[爱快] API失败: HTTP {resp.status_code}", flush=True)
        return {"Result": -1, "ErrMsg": f"HTTP {resp.status_code}"}
    
    # ========== 系统信息 ==========
    
    def get_system_info(self) -> dict:
        """获取系统信息"""
        result = self._call("sysstat", "show")
        return result.get("Data", {})
    
    def get_router_info(self) -> dict:
        """获取路由器基本信息"""
        result = self._call("router", "show")
        return result.get("Data", {})
    
    # ========== 在线设备 ==========
    
    def get_online_devices(self, limit: int = 100, skip: int = 0) -> List[dict]:
        """获取在线设备列表"""
        result = self._call("monitor_lanip", "show", {
            "TYPE": "data,total",
            "limit": f"{skip},{limit}",
            "ORDER_BY": "ip_addr_int",
            "ORDER": "",
            "orderType": "IP"
        })
        
        print(f"[爱快] get_online_devices 结果: {result}", flush=True)
        
        if result.get("Result") in [10000, 30000]:
            data = result.get("Data", {})
            if isinstance(data, dict):
                devices = data.get("data", [])
            else:
                devices = data if isinstance(data, list) else []
            print(f"[爱快] 在线设备数: {len(devices)}", flush=True)
            return devices
        return []
    
    def get_online_count(self) -> int:
        """获取在线设备数量"""
        result = self._call("monitor_lanip", "show", {"TYPE": "total", "orderType": "IP"})
        if result.get("Result") in [10000, 30000]:
            return result.get("Data", {}).get("total", 0)
        return 0
    
    def kick_device(self, mac: str) -> bool:
        """踢设备下线"""
        result = self._call("online", "offline", {"mac": mac.upper()})
        return result.get("Result") == 30000
    
    # ========== 流量统计 ==========
    
    def get_flow_stat(self) -> dict:
        """获取流量统计"""
        result = self._call("flow_stat", "show")
        return result.get("Data", {})
    
    def get_interface_flow(self) -> List[dict]:
        """获取接口流量"""
        result = self._call("interface", "show", {"TYPE": "data,total"})
        return result.get("Data", {}).get("data", [])
    
    def get_ip_flow(self, ip: str = None, limit: int = 100) -> List[dict]:
        """获取 IP 流量统计"""
        param = {
            "TYPE": "data,total",
            "limit": f"0,{limit}",
            "ORDER_BY": "total_down",
            "ORDER": "desc"
        }
        if ip:
            param["ip_addr"] = ip
        
        result = self._call("stat_ip", "show", param)
        return result.get("Data", {}).get("data", [])
    
    # ========== 终端管理 ==========
    
    def get_terminal_list(self, limit: int = 100) -> List[dict]:
        """获取终端设备列表（包含离线设备）"""
        result = self._call("terminal", "show", {
            "TYPE": "data,total",
            "limit": f"0,{limit}",
            "ORDER_BY": "last_time",
            "ORDER": "desc"
        })
        
        if result.get("Result") == 30000:
            return result.get("Data", {}).get("data", [])
        return []
    
    def get_terminal_detail(self, mac: str) -> dict:
        """获取终端详情"""
        result = self._call("terminal", "show", {"mac": mac.upper()})
        data = result.get("Data", {}).get("data", [])
        return data[0] if data else {}
    
    def set_terminal_alias(self, mac: str, alias: str) -> bool:
        """设置终端备注名"""
        result = self._call("terminal", "edit", {
            "mac": mac.upper(),
            "comment": alias
        })
        return result.get("Result") == 30000
    
    # ========== 连接数统计 ==========
    
    def get_connection_stat(self) -> dict:
        """获取连接数统计"""
        result = self._call("connection", "show")
        return result.get("Data", {})
    
    # ========== 日志 ==========
    
    def get_system_log(self, limit: int = 100) -> List[dict]:
        """获取系统日志"""
        result = self._call("syslog", "show", {
            "TYPE": "data,total",
            "limit": f"0,{limit}",
            "ORDER_BY": "time",
            "ORDER": "desc"
        })
        
        if result.get("Result") == 30000:
            return result.get("Data", {}).get("data", [])
        return []