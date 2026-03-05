"""告警检测服务 - 流量阈值、长时间在线、异常行为检测"""
import sys
import time
sys.path.insert(0, '..')
from datetime import datetime, timedelta
from typing import List, Dict
import storage


class AlerterService:
    """告警检测服务"""
    
    def __init__(self, config: dict):
        self.config = config
        self.traffic_threshold_gb = config.get('traffic_threshold_gb', 10)
        self.alert_new_device = config.get('alert_new_device', True)
        self.long_online_hours = config.get('long_online_hours', 24)
        self.high_connection_threshold = config.get('high_connection_threshold', 500)
    
    def check_all(self, online_devices: List[dict], collect_data: dict) -> List[dict]:
        """执行所有告警检测"""
        alerts = []
        
        # 1. 流量阈值检测
        alerts.extend(self._check_traffic_threshold(online_devices))
        
        # 2. 长时间在线检测
        alerts.extend(self._check_long_online(online_devices))
        
        # 3. 高连接数检测
        alerts.extend(self._check_high_connections(online_devices))
        
        # 4. 异常流量突增检测
        alerts.extend(self._check_traffic_spike(collect_data))
        
        return alerts
    
    def _check_traffic_threshold(self, devices: List[dict]) -> List[dict]:
        """检测流量超阈值设备"""
        alerts = []
        threshold_bytes = self.traffic_threshold_gb * 1024 * 1024 * 1024
        
        for dev in devices:
            mac = dev.get('mac', '').upper()
            download = int(dev.get('total_down', 0) or 0)
            upload = int(dev.get('total_up', 0) or 0)
            total = download + upload
            
            if total > threshold_bytes:
                device = storage.get_device(mac)
                alias = device.get('alias', '') if device else ''
                
                # 检查是否今天已告警过
                today = datetime.now().strftime('%Y-%m-%d')
                existing = storage.get_alerts_by_type_date('high_traffic', mac, today)
                
                if not existing:
                    total_gb = total / (1024 ** 3)
                    alert_id = storage.add_alert(
                        alert_type='high_traffic',
                        severity='warning',
                        mac=mac,
                        message=f'{alias or mac[:8]} 流量超阈值: {total_gb:.2f} GB'
                    )
                    alerts.append({
                        'id': alert_id,
                        'type': 'high_traffic',
                        'mac': mac,
                        'message': f'{alias or mac[:8]} 流量超阈值: {total_gb:.2f} GB'
                    })
        
        return alerts
    
    def _check_long_online(self, devices: List[dict]) -> List[dict]:
        """检测长时间在线设备"""
        alerts = []
        threshold_hours = self.long_online_hours
        
        for dev in devices:
            mac = dev.get('mac', '').upper()
            # 爱快返回的连接时间可能是秒数或时间戳
            connect_time = dev.get('connect_time', 0)
            
            if connect_time:
                try:
                    # 计算在线时长
                    if isinstance(connect_time, (int, float)):
                        if connect_time > 1000000000:  # 时间戳
                            online_seconds = time.time() - connect_time
                        else:  # 已经是秒数
                            online_seconds = connect_time
                        
                        online_hours = online_seconds / 3600
                        
                        if online_hours > threshold_hours:
                            device = storage.get_device(mac)
                            alias = device.get('alias', '') if device else ''
                            
                            # 检查是否今天已告警
                            today = datetime.now().strftime('%Y-%m-%d')
                            existing = storage.get_alerts_by_type_date('long_online', mac, today)
                            
                            if not existing:
                                alert_id = storage.add_alert(
                                    alert_type='long_online',
                                    severity='info',
                                    mac=mac,
                                    message=f'{alias or mac[:8]} 已在线 {online_hours:.1f} 小时'
                                )
                                alerts.append({
                                    'id': alert_id,
                                    'type': 'long_online',
                                    'mac': mac,
                                    'message': f'{alias or mac[:8]} 已在线 {online_hours:.1f} 小时'
                                })
                except:
                    pass
        
        return alerts
    
    def _check_high_connections(self, devices: List[dict]) -> List[dict]:
        """检测高连接数设备"""
        alerts = []
        
        for dev in devices:
            mac = dev.get('mac', '').upper()
            connections = int(dev.get('connect', 0) or 0)
            
            if connections > self.high_connection_threshold:
                device = storage.get_device(mac)
                alias = device.get('alias', '') if device else ''
                
                # 检查是否今天已告警
                today = datetime.now().strftime('%Y-%m-%d')
                existing = storage.get_alerts_by_type_date('high_connections', mac, today)
                
                if not existing:
                    alert_id = storage.add_alert(
                        alert_type='high_connections',
                        severity='warning',
                        mac=mac,
                        message=f'{alias or mac[:8]} 连接数异常: {connections}'
                    )
                    alerts.append({
                        'id': alert_id,
                        'type': 'high_connections',
                        'mac': mac,
                        'message': f'{alias or mac[:8]} 连接数异常: {connections}'
                    })
        
        return alerts
    
    def _check_traffic_spike(self, collect_data: dict) -> List[dict]:
        """检测流量突增"""
        alerts = []
        
        # 获取昨天同时段数据对比
        # 这里简化处理，实际可以根据历史数据计算
        # TODO: 实现更精确的突增检测
        
        return alerts
