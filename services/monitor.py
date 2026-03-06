"""监控服务 - 数据采集与异常检测"""
import sys
sys.path.insert(0, '..')
from datetime import datetime
from clients.ikuai_local import IKuaiLocalClient
from services.alerter import AlerterService
import storage


class MonitorService:
    """监控服务"""
    
    def __init__(self, ikuai_config: dict, monitor_config: dict):
        self.config = monitor_config
        self.ikuai_config = ikuai_config
        
        # 使用本地 API
        self.client = IKuaiLocalClient(
            base_url=ikuai_config.get('local_url', 'http://192.168.1.1'),
            username=ikuai_config.get('username', 'admin'),
            password=ikuai_config.get('password', ''),
            session_timeout=monitor_config.get('session_timeout', 120)
        )
        
        # 初始化告警服务
        self.alerter = AlerterService(monitor_config)
        
        # 已知设备集合
        self._known_devices = set()
        self._last_known_devices = set()
        self._load_known_devices()
    
    def can_collect(self) -> bool:
        """检查是否可以采集数据"""
        # 需要密码且连接已验证
        password = self.ikuai_config.get('password', '')
        validated = self.ikuai_config.get('connection_validated', False)
        return bool(password) and validated
    
    def keepalive(self) -> bool:
        """保活会话"""
        if not self.can_collect():
            return False
        return self.client.keepalive()
    
    def _load_known_devices(self):
        """加载已知设备列表"""
        for device in storage.get_all_devices():
            self._known_devices.add(device['mac'].upper())
    
    def collect(self) -> dict:
        """采集数据"""
        # 检查是否可以采集
        if not self.can_collect():
            print("[监控] 连接未验证或无密码，跳过采集")
            return {'devices': [], 'stats': {}}
        
        # 获取在线设备
        online_devices = self.client.get_online_devices()
        
        current_devices = set()
        total_upload = 0
        total_download = 0
        max_connections = 0
        total_upload_speed = 0  # 实时上传速度汇总
        total_download_speed = 0  # 实时下载速度汇总
        
        for dev in online_devices:
            mac = dev.get('mac', '').upper()
            ip = dev.get('ip', '') or dev.get('ip_addr', '')
            upload = int(dev.get('total_up', 0) or dev.get('upload', 0) or 0)
            download = int(dev.get('total_down', 0) or dev.get('download', 0) or 0)
            connections = int(dev.get('connect', 0) or dev.get('connections', 0) or 0)
            upload_speed = int(dev.get('up', 0) or dev.get('upload_speed', 0) or 0)
            download_speed = int(dev.get('down', 0) or dev.get('download_speed', 0) or 0)
            hostname = dev.get('hostname', '') or dev.get('comment', '')
            
            current_devices.add(mac)
            total_upload = max(total_upload, upload)
            total_download = max(total_download, download)
            max_connections = max(max_connections, connections)
            total_upload_speed += upload_speed
            total_download_speed += download_speed
            
            # 更新设备信息
            storage.upsert_device(mac, ip, hostname)
            
            # 记录在线数据
            storage.add_online_record(mac, ip, upload, download, 
                                      upload_speed, download_speed, connections)
            
            # 检测新设备
            if self.config.get('alert_new_device', True):
                if mac not in self._known_devices:
                    self._handle_new_device(mac, ip, hostname)
                    self._known_devices.add(mac)
        
        # 检测设备上下线事件
        self._detect_device_events(current_devices)
        
        # 执行告警检测
        alerts = self.alerter.check_all(online_devices, {
            'total_upload': total_upload,
            'total_download': total_download
        })
        
        return {
            'device_count': len(online_devices),
            'total_upload': total_upload,
            'total_download': total_download,
            'total_upload_speed': total_upload_speed,
            'total_download_speed': total_download_speed,
            'max_connections': max_connections,
            'alerts': alerts
        }
    
    def _detect_device_events(self, current_devices: set):
        """检测设备上下线事件"""
        # 上线设备
        online_devices = current_devices - self._last_known_devices
        for mac in online_devices:
            device = storage.get_device(mac)
            ip = device.get('ip', '') if device else ''
            storage.add_device_event(mac, 'online', ip)
            # 开始在线会话
            storage.start_online_session(mac, ip)
            print(f"[在线] {mac[:8]}... 上线")
        
        # 离线设备
        offline_devices = self._last_known_devices - current_devices
        for mac in offline_devices:
            device = storage.get_device(mac)
            ip = device.get('ip', '') if device else ''
            storage.add_device_event(mac, 'offline', ip)
            # 结束在线会话
            storage.end_online_session(mac)
            # 获取今日在线时长
            today_online = storage.get_today_online_time(mac)
            print(f"[离线] {mac[:8]}... 下线 (今日在线: {today_online}分钟)")
            
            # 信任设备离线推送
            if device and device.get('is_trusted') and self.config.get('alert_offline', True):
                self._send_offline_notification(mac, device)
        
        # 检测离线告警
        self.alerter.check_offline_devices(current_devices, self._last_known_devices)
        
        self._last_known_devices = current_devices
    
    def _handle_new_device(self, mac: str, ip: str, hostname: str):
        """处理新设备接入"""
        storage.add_device_event(mac, 'online', ip)
        
        device = storage.get_device(mac)
        if not device or not device.get('is_trusted'):
            # 添加告警记录
            storage.add_alert(
                alert_type='new_device',
                severity='warning',
                mac=mac,
                message=f'新设备接入: {hostname or mac[:8]} ({ip})'
            )
            
            # 推送通知
            if self.config.get('alert_new_device', True):
                self._send_new_device_notification(mac, ip, hostname)
    
    def _send_new_device_notification(self, mac: str, ip: str, hostname: str):
        """发送新设备接入通知"""
        try:
            from services.pusher import MultiPushClient
            import config as cfg_module
            
            cfg = cfg_module.get_config()
            pusher = MultiPushClient(cfg.get('pushme', {}))
            
            if not pusher.enabled:
                print(f"[通知] 推送已禁用，跳过")
                return
            
            # 获取设备厂商
            from services.vendor import get_vendor_cached
            vendor = get_vendor_cached(mac)
            
            title = "🔐 安全告警 - 新设备接入"
            content = f"""## ⚠️ 新设备接入告警

### 📱 设备信息
| 项目 | 详情 |
|------|------|
| MAC 地址 | `{mac}` |
| IP 地址 | `{ip}` |
| 主机名 | {hostname or '未知'} |
| 厂商 | {vendor or '未知'} |

### ⏰ 接入时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*如非本人操作，请及时检查网络安全性*"""
            
            success, msg = pusher.send(title, content, 'markdown')
            if success:
                print(f"[推送] 新设备通知已发送: {mac}")
            else:
                print(f"[推送] 发送失败: {msg}")
        except Exception as e:
            print(f"[推送] 异常: {e}")
    
    def _send_offline_notification(self, mac: str, device: dict):
        """发送设备离线通知"""
        try:
            from services.pusher import MultiPushClient
            import config as cfg_module
            
            cfg = cfg_module.get_config()
            pusher = MultiPushClient(cfg.get('pushme', {}))
            
            if not pusher.enabled:
                return
            
            alias = device.get('alias', '') or device.get('hostname', '') or mac[:8]
            ip = device.get('ip', '')
            
            title = "📴 设备离线告警"
            content = f"""## ⚠️ 信任设备离线

### 📱 设备信息
| 项目 | 详情 |
|------|------|
| 设备名称 | **{alias}** |
| MAC 地址 | `{mac}` |
| IP 地址 | `{ip}` |

### ⏰ 离线时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*iHomeGuard 设备监控*"""
            
            success, msg = pusher.send(title, content, 'markdown')
            if success:
                print(f"[推送] 离线通知已发送: {alias}")
        except Exception as e:
            print(f"[推送] 离线通知异常: {e}")
    
    def get_current_status(self) -> dict:
        """获取当前状态"""
        if not self.can_collect():
            return {'online_count': 0, 'devices': []}
        
        online_devices = self.client.get_online_devices()
        
        devices = []
        for dev in online_devices:
            mac = dev.get('mac', '').upper()
            device_info = storage.get_device(mac) or {}
            
            # 爱快 monitor_lanip API 返回的字段：
            # ip_addr: IP地址
            # total_up / total_down: 累计上传/下载流量
            # download / upload: 实时下载/上传速度
            # connect_num: 连接数
            # comment: 设备备注
            # hostname: 设备主机名
            # client_model: 设备型号识别
            
            # 获取今日在线时长
            today_online_minutes = storage.get_today_online_time(mac)
            
            devices.append({
                'mac': mac,
                'ip': dev.get('ip_addr', ''),
                'hostname': dev.get('hostname', '') or dev.get('comment', ''),
                'alias': device_info.get('alias', '') or dev.get('comment', ''),
                'is_trusted': device_info.get('is_trusted', 0),
                'upload_speed': dev.get('upload', 0),  # 实时上传速度
                'download_speed': dev.get('download', 0),  # 实时下载速度
                'total_upload': dev.get('total_up', 0),  # 累计上传
                'total_download': dev.get('total_down', 0),  # 累计下载
                'connections': dev.get('connect_num', 0),  # 连接数
                'client_model': dev.get('client_model', ''),  # 设备型号
                'client_device': dev.get('client_device', ''),  # 设备厂商
                'today_online_minutes': today_online_minutes  # 今日在线时长
            })
        
        return {
            'online_count': len(devices),
            'devices': devices
        }
    
    def get_terminal_list(self) -> list:
        """获取终端列表（包含历史设备）"""
        if not self.can_collect():
            return []
        return self.client.get_terminal_list()
    
    def set_device_alias(self, mac: str, alias: str) -> bool:
        """设置设备备注（同步到路由器）"""
        storage.update_device_alias(mac, alias)
        return self.client.set_terminal_alias(mac, alias)
    
    def kick_device(self, mac: str) -> bool:
        """踢设备下线"""
        return self.client.kick_device(mac)
