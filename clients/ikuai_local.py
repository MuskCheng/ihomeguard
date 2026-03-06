"""爱快路由器本地 API 客户端

参考: https://blog.51cto.com/infrado/13378327
"""
import hashlib
import requests
import time
from typing import Optional, List, Dict
from datetime import datetime, timedelta


class IKuaiLocalClient:
    """爱快路由器本地 API 客户端"""
    
    # 锁定状态缓存（类级别，所有实例共享）
    _lock_until = None  # 锁定解除时间
    _last_login_time = None  # 上次登录时间
    _last_keepalive_time = None  # 上次保活时间
    _login_session_valid = False  # 会话是否有效
    _session_timeout = 120  # 会话超时时间（分钟）
    _shared_session = None  # 共享的 requests Session
    _sess_key = None  # 共享的 session key
    
    @classmethod
    def reset_lock_state(cls):
        """重置锁定状态（系统启动时调用）"""
        cls._lock_until = None
        cls._last_login_time = None
        cls._login_session_valid = False
        cls._last_keepalive_time = None
        cls._shared_session = None
        cls._sess_key = None
        print("[爱快] 锁定状态已重置", flush=True)
    
    def __init__(self, base_url: str, username: str, password: str, session_timeout: int = 120):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        # 使用共享的 Session
        if IKuaiLocalClient._shared_session is None:
            IKuaiLocalClient._shared_session = requests.Session()
        self.session = IKuaiLocalClient._shared_session
        IKuaiLocalClient._session_timeout = session_timeout
    
    def _md5(self, text: str) -> str:
        """计算 MD5"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def _is_locked(self) -> bool:
        """检查是否处于锁定状态"""
        if IKuaiLocalClient._lock_until:
            if datetime.now() < IKuaiLocalClient._lock_until:
                remaining = (IKuaiLocalClient._lock_until - datetime.now()).seconds
                print(f"[爱快] 账号锁定中，剩余 {remaining} 秒", flush=True)
                return True
            else:
                # 锁定已过期，清除
                IKuaiLocalClient._lock_until = None
        return False
    
    def _set_lock(self, seconds: int = 310):
        """设置锁定状态（默认5分钟+10秒缓冲）"""
        IKuaiLocalClient._lock_until = datetime.now() + timedelta(seconds=seconds)
        print(f"[爱快] 设置登录锁定 {seconds} 秒，直至 {IKuaiLocalClient._lock_until.strftime('%H:%M:%S')}", flush=True)
    
    def _is_session_expired(self) -> bool:
        """检查会话是否过期"""
        if not IKuaiLocalClient._last_keepalive_time:
            return True
        
        # 超过超时时间的80%就认为需要保活
        timeout_seconds = IKuaiLocalClient._session_timeout * 60 * 0.8
        elapsed = (datetime.now() - IKuaiLocalClient._last_keepalive_time).total_seconds()
        return elapsed > timeout_seconds
    
    def login(self) -> bool:
        """登录获取会话"""
        # 检查是否被锁定
        if self._is_locked():
            return False
        
        # 登录频率限制：最小间隔3秒
        if IKuaiLocalClient._last_login_time:
            elapsed = (datetime.now() - IKuaiLocalClient._last_login_time).total_seconds()
            if elapsed < 3:
                wait_time = 3 - elapsed
                print(f"[爱快] 登录频率限制，等待 {wait_time:.1f} 秒", flush=True)
                time.sleep(wait_time)
        
        passwd_md5 = self._md5(self.password)
        
        try:
            login_url = f"{self.base_url}/Action/login"
            IKuaiLocalClient._last_login_time = datetime.now()
            
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
                    IKuaiLocalClient._login_session_valid = True
                    IKuaiLocalClient._last_keepalive_time = datetime.now()
                    print(f"[爱快] 登录成功", flush=True)
                    return True
                else:
                    IKuaiLocalClient._login_session_valid = False
                    error_code = result.get("Result")
                    error_msg = result.get('ErrMsg', '未知错误')
                    
                    # 账号锁定 (10015)
                    if error_code == 10015:
                        print(f"[爱快] 账号被锁定: {error_msg}", flush=True)
                        self._set_lock(490)  # 锁定8分钟+10秒
                    # 密码错误 (10001)
                    elif error_code == 10001:
                        print(f"[爱快] 密码错误: {error_msg}", flush=True)
                        # 连续错误也可能触发锁定，设置8分钟延时
                        self._set_lock(490)
                    else:
                        print(f"[爱快] 登录失败: {error_msg}", flush=True)
            else:
                print(f"[爱快] 登录请求失败: HTTP {resp.status_code}", flush=True)
                IKuaiLocalClient._login_session_valid = False
        except Exception as e:
            print(f"[爱快] 登录异常: {e}", flush=True)
            IKuaiLocalClient._login_session_valid = False
        return False
    
    def keepalive(self) -> bool:
        """保活 - 定期调用以保持会话有效"""
        # 检查锁定状态
        if self._is_locked():
            return False
        
        # 如果会话有效且未过期，不需要保活
        if IKuaiLocalClient._login_session_valid and not self._is_session_expired():
            return True
        
        try:
            # 调用一个轻量级API来保持会话
            print(f"[爱快] 执行保活...", flush=True)
            resp = self.session.post(
                f"{self.base_url}/Action/call",
                json={"func_name": "sysstat", "action": "show", "param": {}},
                timeout=10
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get("Result") in [10000, 30000]:
                    IKuaiLocalClient._last_keepalive_time = datetime.now()
                    IKuaiLocalClient._login_session_valid = True
                    print(f"[爱快] 保活成功", flush=True)
                    return True
                else:
                    # 会话已失效，需要重新登录
                    print(f"[爱快] 会话已失效，尝试重新登录", flush=True)
                    IKuaiLocalClient._login_session_valid = False
                    return self.login()
            else:
                print(f"[爱快] 保活请求失败: HTTP {resp.status_code}", flush=True)
                return False
        except Exception as e:
            print(f"[爱快] 保活异常: {e}", flush=True)
            return False
    
    def _ensure_login(self):
        """确保已登录"""
        # 检查锁定状态
        if self._is_locked():
            raise Exception("账号被锁定，请稍后重试")
        
        # 如果会话有效且未过期，不需要重新登录
        if IKuaiLocalClient._login_session_valid and self._sess_key and not self._is_session_expired():
            return
        
        # 尝试保活或登录
        if not self.keepalive():
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