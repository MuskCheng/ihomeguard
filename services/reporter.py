"""日报生成服务"""
import sys
sys.path.insert(0, '..')
from datetime import datetime, timedelta
from services.pusher import MultiPushClient
from services.vendor import get_vendor_cached
import storage


class ReporterService:
    """日报生成服务"""
    
    def __init__(self, pushme_config: dict):
        self.pusher = MultiPushClient(pushme_config)
        self.enabled = pushme_config.get('enabled', True)
    
    def generate_daily_report(self, date: str = None) -> dict:
        """生成日报数据"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        # 获取当日统计
        stats = storage.get_daily_stats(date)
        
        if not stats:
            # 计算当日数据
            stats = self._calculate_daily_stats(date)
        
        # 获取设备流量排行
        devices = self._get_device_stats(date)
        
        # 获取告警
        alerts = storage.get_recent_alerts(10)
        
        # 获取今日上下线事件
        events = self._get_today_events(date)
        
        return {
            'date': date,
            'total_upload': stats.get('total_upload', 0),
            'total_download': stats.get('total_download', 0),
            'device_count': stats.get('device_count', 0),
            'peak_device_count': stats.get('peak_device_count', 0),
            'max_connections': stats.get('max_connections', 0),
            'devices': devices,
            'alerts': alerts,
            'events': events
        }
    
    def _calculate_daily_stats(self, date: str) -> dict:
        """计算当日统计"""
        records = storage.get_today_records()
        
        if not records:
            return {'total_upload': 0, 'total_download': 0, 
                    'device_count': 0, 'max_connections': 0, 'peak_device_count': 0}
        
        # 统计
        total_upload = max(r['upload_bytes'] for r in records) if records else 0
        total_download = max(r['download_bytes'] for r in records) if records else 0
        max_connections = max(r['connections'] for r in records) if records else 0
        
        # 峰值设备数
        unique_devices = set(r['mac'] for r in records)
        
        stats = {
            'total_upload': total_upload,
            'total_download': total_download,
            'device_count': len(unique_devices),
            'max_connections': max_connections,
            'peak_device_count': len(unique_devices)
        }
        
        # 保存统计
        storage.save_daily_stats(date, **stats)
        
        return stats
    
    def _get_device_stats(self, date: str) -> list:
        """获取设备流量统计"""
        records = storage.get_today_records()
        
        device_stats = {}
        for r in records:
            mac = r['mac']
            if mac not in device_stats:
                device_info = storage.get_device(mac) or {}
                vendor = get_vendor_cached(mac)
                device_stats[mac] = {
                    'mac': mac,
                    'alias': device_info.get('alias', ''),
                    'hostname': device_info.get('hostname', ''),
                    'vendor': vendor,
                    'is_trusted': device_info.get('is_trusted', 0),
                    'total_upload': 0,
                    'total_download': 0
                }
            device_stats[mac]['total_upload'] = max(device_stats[mac]['total_upload'], r['upload_bytes'])
            device_stats[mac]['total_download'] = max(device_stats[mac]['total_download'], r['download_bytes'])
        
        return list(device_stats.values())
    
    def _get_today_events(self, date: str) -> list:
        """获取今日上下线事件"""
        events = storage.get_events_by_date(date, limit=50)
        
        # 添加设备别名信息
        for event in events:
            device = storage.get_device(event['mac'])
            event['alias'] = device.get('alias', '') if device else ''
            event['hostname'] = device.get('hostname', '') if device else ''
        
        return events
    
    def send_report(self, date: str = None) -> bool:
        """发送日报"""
        if not self.enabled:
            return False
        
        report = self.generate_daily_report(date)
        success, _ = self.pusher.send_daily_report(report)
        return success
    
    def send_alert_now(self, alert_type: str, message: str) -> bool:
        """立即发送告警"""
        if not self.enabled:
            return False
        success, _ = self.pusher.send_alert(alert_type, message)
        return success
    
    def send_enhanced_report(self, date: str = None) -> bool:
        """发送增强版日报（含上下线事件）"""
        if not self.enabled:
            return False
        
        report = self.generate_daily_report(date)
        return self.pusher.send_daily_report(report)