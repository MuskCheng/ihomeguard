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
        self.total_connection_threshold = config.get('total_connection_threshold', 1000)
        # 实时速度阈值（KB/s），默认上传10MB/s，下载50MB/s
        self.upload_speed_threshold = config.get('upload_speed_threshold_kbps', 10240) * 1024
        self.download_speed_threshold = config.get('download_speed_threshold_kbps', 51200) * 1024
    
    def check_all(self, online_devices: List[dict], collect_data: dict) -> List[dict]:
        """执行所有告警检测"""
        alerts = []

        # 1. 流量阈值检测
        alerts.extend(self._check_traffic_threshold(online_devices))

        # 2. 长时间在线检测
        alerts.extend(self._check_long_online(online_devices))

        # 3. 高连接数检测（单设备）
        alerts.extend(self._check_high_connections(online_devices))

        # 4. 异常流量突增检测
        alerts.extend(self._check_traffic_spike(collect_data))

        # 5. 实时速度阈值检测
        alerts.extend(self._check_speed_threshold(online_devices))

        # 6. 总连接数告警
        alerts.extend(self._check_total_connections(online_devices))

        return alerts
    
    def check_offline_devices(self, current_devices: set, previous_devices: set) -> List[dict]:
        """检测离线设备（信任设备离线告警）"""
        alerts = []
        
        if not self.config.get('alert_offline', True):
            return alerts
        
        # 找出离线的设备
        offline_devices = previous_devices - current_devices
        
        for mac in offline_devices:
            device = storage.get_device(mac)
            if device and device.get('is_trusted'):
                # 信任设备离线告警
                alias = device.get('alias', '') or device.get('hostname', '') or mac[:8]
                alert_id = storage.add_alert(
                    alert_type='device_offline',
                    severity='warning',
                    mac=mac,
                    message=f'信任设备离线: {alias}'
                )
                alerts.append({
                    'id': alert_id,
                    'type': 'device_offline',
                    'mac': mac,
                    'message': f'信任设备离线: {alias}'
                })
                print(f"[告警] 信任设备离线: {alias} ({mac})")
        
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
            # 爱快API字段名是 connect_num
            connections = int(dev.get('connect_num', 0) or dev.get('connect', 0) or 0)
            
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

    def _check_speed_threshold(self, devices: List[dict]) -> List[dict]:
        """检测实时速度超阈值设备"""
        alerts = []

        for dev in devices:
            mac = dev.get('mac', '').upper()
            # 爱快API中 upload/download 字段是实时速度（bytes/s）
            upload_speed = int(dev.get('upload', 0) or 0)
            download_speed = int(dev.get('download', 0) or 0)

            # 检查上传速度
            if upload_speed > self.upload_speed_threshold:
                device = storage.get_device(mac)
                alias = device.get('alias', '') if device else ''

                # 检查是否最近10分钟已告警过
                recent_alerts = storage.get_recent_alerts_by_type('high_upload_speed', mac, minutes=10)
                if not recent_alerts:
                    speed_mbps = upload_speed / (1024 * 1024)
                    alert_id = storage.add_alert(
                        alert_type='high_upload_speed',
                        severity='warning',
                        mac=mac,
                        message=f'{alias or mac[:8]} 上传速度异常: {speed_mbps:.2f} MB/s'
                    )
                    alerts.append({
                        'id': alert_id,
                        'type': 'high_upload_speed',
                        'mac': mac,
                        'message': f'{alias or mac[:8]} 上传速度异常: {speed_mbps:.2f} MB/s'
                    })

            # 检查下载速度
            if download_speed > self.download_speed_threshold:
                device = storage.get_device(mac)
                alias = device.get('alias', '') if device else ''

                recent_alerts = storage.get_recent_alerts_by_type('high_download_speed', mac, minutes=10)
                if not recent_alerts:
                    speed_mbps = download_speed / (1024 * 1024)
                    alert_id = storage.add_alert(
                        alert_type='high_download_speed',
                        severity='warning',
                        mac=mac,
                        message=f'{alias or mac[:8]} 下载速度异常: {speed_mbps:.2f} MB/s'
                    )
                    alerts.append({
                        'id': alert_id,
                        'type': 'high_download_speed',
                        'mac': mac,
                        'message': f'{alias or mac[:8]} 下载速度异常: {speed_mbps:.2f} MB/s'
                    })

        return alerts

    def _check_total_connections(self, devices: List[dict]) -> List[dict]:
        """检测总连接数超阈值"""
        alerts = []

        # 计算总连接数
        total_connections = 0
        for dev in devices:
            connections = int(dev.get('connect_num', 0) or dev.get('connect', 0) or 0)
            total_connections += connections

        # 检查是否超阈值
        if total_connections > self.total_connection_threshold:
            # 检查是否最近10分钟已告警过
            recent_alerts = storage.get_recent_alerts_by_type_all('high_total_connections', minutes=10)
            if not recent_alerts:
                alert_id = storage.add_alert(
                    alert_type='high_total_connections',
                    severity='warning',
                    mac='',
                    message=f'总连接数异常: {total_connections} 个连接'
                )
                alerts.append({
                    'id': alert_id,
                    'type': 'high_total_connections',
                    'mac': '',
                    'message': f'总连接数异常: {total_connections} 个连接'
                })

        return alerts
