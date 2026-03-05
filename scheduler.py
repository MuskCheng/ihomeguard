"""定时任务调度"""
import sys
sys.path.insert(0, '..')
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import config
import storage
from services.monitor import MonitorService
from services.reporter import ReporterService


scheduler = BackgroundScheduler()


def collect_task():
    """数据采集任务"""
    try:
        cfg = config.get_config()
        monitor = MonitorService(cfg['ikuai'], cfg['monitor'])
        result = monitor.collect()
        
        print(f"[采集] {datetime.now().strftime('%H:%M:%S')} - "
              f"在线: {result['device_count']}台, "
              f"上行: {format_bytes(result['total_upload'])}, "
              f"下行: {format_bytes(result['total_download'])}")
        
        # 实时告警推送
        if result.get('alerts'):
            reporter = ReporterService(cfg['pushme'])
            for alert in result['alerts']:
                reporter.send_alert_now(alert['type'], alert['message'])
                
    except Exception as e:
        print(f"[采集错误] {e}")


def daily_report_task():
    """日报任务"""
    try:
        cfg = config.get_config()
        reporter = ReporterService(cfg['pushme'])
        
        if reporter.enabled:
            success = reporter.send_report()
            print(f"[日报] 推送{'成功' if success else '失败'}")
    except Exception as e:
        print(f"[日报错误] {e}")


def daily_stats_task():
    """每日统计任务"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        records = storage.get_today_records()
        
        if records:
            # 计算统计数据
            unique_devices = set(r['mac'] for r in records)
            total_upload = max(r['upload_bytes'] for r in records)
            total_download = max(r['download_bytes'] for r in records)
            max_connections = max(r['connections'] for r in records)
            
            storage.save_daily_stats(
                date=today,
                total_upload=total_upload,
                total_download=total_download,
                device_count=len(unique_devices),
                max_connections=max_connections,
                peak_device_count=len(unique_devices)
            )
            print(f"[统计] {today} 数据已保存")
    except Exception as e:
        print(f"[统计错误] {e}")


def format_bytes(bytes_val):
    """格式化字节数"""
    if not bytes_val:
        return '0 B'
    k = 1024
    sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    i = min(len(sizes) - 1, int(bytes_val.bit_length() / 10))
    return f"{bytes_val / (k ** i):.1f} {sizes[i]}"


def start_scheduler():
    """启动调度器"""
    cfg = config.get_config()
    monitor_cfg = cfg.get('monitor', {})
    
    # 数据采集任务
    interval = monitor_cfg.get('collect_interval', 300)
    scheduler.add_job(collect_task, 'interval', seconds=interval, id='collect')
    
    # 日报任务
    report_time = monitor_cfg.get('report_time', '21:00')
    hour, minute = map(int, report_time.split(':'))
    scheduler.add_job(daily_report_task, CronTrigger(hour=hour, minute=minute), id='daily_report')
    
    # 每日统计任务（每天 23:55）
    scheduler.add_job(daily_stats_task, CronTrigger(hour=23, minute=55), id='daily_stats')
    
    scheduler.start()
    print(f"[调度] 采集间隔: {interval}秒, 日报时间: {report_time}")