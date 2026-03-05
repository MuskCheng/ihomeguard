"""监控服务 - 数据采集与异常检测"""
import sys
sys.path.insert(0, '..')
from clients.ikuai_local import IKuaiLocalClient
from services.alerter import AlerterService
import storage


class MonitorService:
    """监控服务"""
    
    def __init__(self, ikuai_config: dict, monitor_config: dict):
        self.config = monitor_config
        
        # 使用本地 API
        self.client = IKuaiLocalClient(
            base_url=ikuai_config.get('local_url', 'http://192.168.1.1'),
            username=ikuai_config.get('username', 'admin'),
            password=ikuai_config.get('password', '')
        )
        
        # 初始化告警服务
        self.alerter = AlerterService(monitor_config)
        
        # 已知设备集合
        self._known_devices = set()
        self._last_known_devices = set()
        self._load_known_devices()
    
    def _load_known_devices(self):
        """加载已知设备列表"""
        for device in storage.get_all_devices():
            self._known_devices.add(device['mac'].upper())
    
    def collect(self) -> dict:
        """采集数据"""
        # 获取在线设备
        online_devices = self.client.get_online_devices()
        
        current_devices = set()
        total_upload = 0
        total_download = 0
        max_connections = 0
        
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
        
        # 离线设备
        offline_devices = self._last_known_devices - current_devices
        for mac in offline_devices:
            device = storage.get_device(mac)
            ip = device.get('ip', '') if device else ''
            storage.add_device_event(mac, 'offline', ip)
        
        self._last_known_devices = current_devices
    
    def _handle_new_device(self, mac: str, ip: str, hostname: str):
        """处理新设备接入"""
        storage.add_device_event(mac, 'online', ip)
        
        device = storage.get_device(mac)
        if not device or not device.get('is_trusted'):
            storage.add_alert(
                alert_type='new_device',
                severity='warning',
                mac=mac,
                message=f'新设备接入: {hostname or mac[:8]} ({ip})'
            )
    
    def get_current_status(self) -> dict:
        """获取当前状态"""
        online_devices = self.client.get_online_devices()
        
        devices = []
        for dev in online_devices:
            mac = dev.get('mac', '').upper()
            device_info = storage.get_device(mac) or {}
            
            devices.append({
                'mac': mac,
                'ip': dev.get('ip', '') or dev.get('ip_addr', ''),
                'hostname': dev.get('hostname', '') or dev.get('comment', ''),
                'alias': device_info.get('alias', ''),
                'is_trusted': device_info.get('is_trusted', 0),
                'upload_speed': dev.get('up', 0) or dev.get('upload_speed', 0),
                'download_speed': dev.get('down', 0) or dev.get('download_speed', 0),
                'total_upload': dev.get('total_up', 0) or dev.get('upload', 0),
                'total_download': dev.get('total_down', 0) or dev.get('download', 0),
                'connections': dev.get('connect', 0) or dev.get('connections', 0)
            })
        
        return {
            'online_count': len(devices),
            'devices': devices
        }
    
    def get_terminal_list(self) -> list:
        """获取终端列表（包含历史设备）"""
        return self.client.get_terminal_list()
    
    def set_device_alias(self, mac: str, alias: str) -> bool:
        """设置设备备注（同步到路由器）"""
        storage.update_device_alias(mac, alias)
        return self.client.set_terminal_alias(mac, alias)
    
    def kick_device(self, mac: str) -> bool:
        """踢设备下线"""
        return self.client.kick_device(mac)
