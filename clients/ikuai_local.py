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
        
        resp = self.session.post(
            f"{self.base_url}/Action/login",
            data={
                "username": self.username,
                "passwd": passwd_md5,
                "pass": "true",
                "remember_password": "false"
            },
            timeout=10
        )
        
        if resp.status_code == 200:
            result = resp.json()
            if result.get("Result") == 30000:
                self._sess_key = self.session.cookies.get('sess_key')
                return True
        return False
    
    def _ensure_login(self):
        """确保已登录"""
        if not self._sess_key:
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
        
        resp = self.session.post(
            f"{self.base_url}/Action/login",
            json=body,
            timeout=30
        )
        
        if resp.status_code == 200:
            return resp.json()
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
        result = self._call("online", "show", {
            "TYPE": "data,total",
            "limit": f"{skip},{limit}",
            "ORDER_BY": "ip_addr",
            "ORDER": ""
        })
        
        if result.get("Result") == 30000:
            return result.get("Data", {}).get("data", [])
        return []
    
    def get_online_count(self) -> int:
        """获取在线设备数量"""
        result = self._call("online", "show", {"TYPE": "total"})
        if result.get("Result") == 30000:
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