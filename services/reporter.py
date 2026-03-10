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
        """生成日报数据
        
        Args:
            date: 报告日期，默认为昨天（日报通常发送前一天数据）
        """
        if not date:
            # 日报默认发送昨天的数据
            date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 获取当日统计（已保存的增量数据）
        stats = storage.get_daily_stats(date)
        
        if not stats:
            # 如果没有保存的统计，计算当日数据
            stats = self._calculate_daily_stats(date)
        
        # 获取设备流量排行（使用增量计算）
        devices = self._get_device_stats(date)
        
        # 获取当日告警（按日期过滤）
        alerts = storage.get_alerts_by_date(date, 10)
        
        # 获取当日上下线事件
        events = self._get_events_by_date(date)
        
        # 获取前一天统计用于环比
        prev_date = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_stats = storage.get_daily_stats(prev_date)
        
        # 计算环比变化
        comparison = self._calculate_comparison(stats, prev_stats)
        
        return {
            'date': date,
            'total_upload': stats.get('total_upload', 0),
            'total_download': stats.get('total_download', 0),
            'device_count': stats.get('device_count', 0),
            'peak_device_count': stats.get('peak_device_count', 0),
            'max_connections': stats.get('max_connections', 0),
            'devices': devices,
            'alerts': alerts,
            'events': events,
            'comparison': comparison
        }
    
    def _calculate_daily_stats(self, date: str) -> dict:
        """计算当日统计（增量计算）
        
        计算方式：当日最后记录 - 前一日最后记录 = 当日增量
        """
        records = storage.get_records_by_date(date)
        
        if not records:
            return {
                'total_upload': 0, 
                'total_download': 0, 
                'device_count': 0, 
                'max_connections': 0, 
                'peak_device_count': 0
            }
        
        # 获取前一天记录作为基准
        prev_date = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_records = storage.get_records_by_date(prev_date)
        
        # 构建前一天每设备的最后记录
        prev_last = {}
        for r in prev_records:
            mac = r['mac']
            if mac not in prev_last or r['recorded_at'] > prev_last[mac]['recorded_at']:
                prev_last[mac] = r
        
        # 构建当日每设备的首条和最后记录
        today_first = {}
        today_last = {}
        for r in records:
            mac = r['mac']
            if mac not in today_first or r['recorded_at'] < today_first[mac]['recorded_at']:
                today_first[mac] = r
            if mac not in today_last or r['recorded_at'] > today_last[mac]['recorded_at']:
                today_last[mac] = r
        
        # 计算增量
        total_upload = 0
        total_download = 0
        max_connections = 0
        unique_devices = set()
        
        for mac, last_record in today_last.items():
            unique_devices.add(mac)
            max_connections = max(max_connections, last_record.get('connections', 0))
            
            # 计算增量：当日最后 - 基准值
            if mac in prev_last:
                # 有前一天记录，使用前一天最后记录作为基准
                base_upload = prev_last[mac]['upload_bytes']
                base_download = prev_last[mac]['download_bytes']
            else:
                # 没有前一天记录，使用当日首条记录作为基准
                if mac in today_first:
                    base_upload = today_first[mac]['upload_bytes']
                    base_download = today_first[mac]['download_bytes']
                else:
                    base_upload = 0
                    base_download = 0
            
            upload_delta = max(0, last_record['upload_bytes'] - base_upload)
            download_delta = max(0, last_record['download_bytes'] - base_download)
            
            total_upload += upload_delta
            total_download += download_delta
        
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
        """获取设备流量统计（增量计算）"""
        records = storage.get_records_by_date(date)
        
        if not records:
            return []
        
        # 获取前一天记录作为基准
        prev_date = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_records = storage.get_records_by_date(prev_date)
        
        # 构建前一天每设备的最后记录
        prev_last = {}
        for r in prev_records:
            mac = r['mac']
            if mac not in prev_last or r['recorded_at'] > prev_last[mac]['recorded_at']:
                prev_last[mac] = r
        
        # 构建当日每设备的首条和最后记录
        today_first = {}
        today_last = {}
        for r in records:
            mac = r['mac']
            if mac not in today_first or r['recorded_at'] < today_first[mac]['recorded_at']:
                today_first[mac] = r
            if mac not in today_last or r['recorded_at'] > today_last[mac]['recorded_at']:
                today_last[mac] = r
        
        # 获取当日在线时长
        online_times = self._get_device_online_times(date)
        
        # 计算每设备增量
        device_stats = {}
        for mac, last_record in today_last.items():
            device_info = storage.get_device(mac) or {}
            vendor = get_vendor_cached(mac)
            
            # 计算增量
            if mac in prev_last:
                base_upload = prev_last[mac]['upload_bytes']
                base_download = prev_last[mac]['download_bytes']
            elif mac in today_first:
                base_upload = today_first[mac]['upload_bytes']
                base_download = today_first[mac]['download_bytes']
            else:
                base_upload = 0
                base_download = 0
            
            upload_delta = max(0, last_record['upload_bytes'] - base_upload)
            download_delta = max(0, last_record['download_bytes'] - base_download)
            
            device_stats[mac] = {
                'mac': mac,
                'alias': device_info.get('alias', ''),
                'hostname': device_info.get('hostname', ''),
                'vendor': vendor,
                'is_trusted': device_info.get('is_trusted', 0),
                'total_upload': upload_delta,
                'total_download': download_delta,
                'online_minutes': online_times.get(mac, 0)
            }
        
        return list(device_stats.values())
    
    def _get_device_online_times(self, date: str) -> dict:
        """获取设备当日在线时长"""
        with storage.get_db() as conn:
            rows = conn.execute('''
                SELECT mac, COALESCE(SUM(duration_minutes), 0) as total
                FROM online_sessions 
                WHERE date(online_at) = ?
                GROUP BY mac
            ''', (date,)).fetchall()
            
            result = {row['mac']: row['total'] for row in rows}
            
            # 加上当前在线的时长
            active_sessions = conn.execute('''
                SELECT mac, online_at FROM online_sessions 
                WHERE offline_at IS NULL AND date(online_at) = ?
            ''', (date,)).fetchall()
            
            for session in active_sessions:
                mac = session['mac']
                online_at = datetime.fromisoformat(session['online_at'])
                current_minutes = int((datetime.now() - online_at).total_seconds() / 60)
                result[mac] = result.get(mac, 0) + current_minutes
            
            return result
    
    def _get_events_by_date(self, date: str) -> list:
        """获取指定日期上下线事件"""
        events = storage.get_events_by_date(date, limit=50)
        
        # 添加设备别名信息
        for event in events:
            device = storage.get_device(event['mac'])
            event['alias'] = device.get('alias', '') if device else ''
            event['hostname'] = device.get('hostname', '') if device else ''
        
        return events
    
    def _calculate_comparison(self, today_stats: dict, prev_stats: dict) -> dict:
        """计算环比变化"""
        if not prev_stats:
            return {'upload_change': 0, 'download_change': 0, 'upload_percent': 0, 'download_percent': 0}
        
        today_upload = today_stats.get('total_upload', 0)
        today_download = today_stats.get('total_download', 0)
        prev_upload = prev_stats.get('total_upload', 0)
        prev_download = prev_stats.get('total_download', 0)
        
        upload_change = today_upload - prev_upload
        download_change = today_download - prev_download
        
        upload_percent = (upload_change / prev_upload * 100) if prev_upload > 0 else 0
        download_percent = (download_change / prev_download * 100) if prev_download > 0 else 0
        
        return {
            'upload_change': upload_change,
            'download_change': download_change,
            'upload_percent': upload_percent,
            'download_percent': download_percent,
            'prev_upload': prev_upload,
            'prev_download': prev_download
        }
    
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
