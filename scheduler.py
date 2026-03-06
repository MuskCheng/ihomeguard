"""定时任务调度"""
import sys
sys.path.insert(0, '..')
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import config
import storage
from services.monitor import MonitorService
from services.reporter import ReporterService


scheduler = BackgroundScheduler()

# 全局监控服务实例（用于保活）
_monitor_instance = None


def get_monitor_instance():
    """获取监控服务实例"""
    global _monitor_instance
    if _monitor_instance is None:
        cfg = config.get_config()
        _monitor_instance = MonitorService(cfg['ikuai'], cfg['monitor'])
    return _monitor_instance


def collect_task():
    """数据采集任务"""
    try:
        monitor = get_monitor_instance()
        result = monitor.collect()
        
        print(f"[采集] {datetime.now().strftime('%H:%M:%S')} - "
              f"在线: {result['device_count']}台, "
              f"上行: {format_bytes(result['total_upload'])}, "
              f"下行: {format_bytes(result['total_download'])}")
        
        # 保存流量快照用于实时监控
        storage.save_traffic_snapshot(
            result.get('total_upload_speed', 0),
            result.get('total_download_speed', 0),
            result.get('device_count', 0),
            result.get('total_connections', 0)
        )
        
        # 实时告警推送
        if result.get('alerts'):
            cfg = config.get_config()
            reporter = ReporterService(cfg['pushme'])
            for alert in result['alerts']:
                reporter.send_alert_now(alert['type'], alert['message'])
                
    except Exception as e:
        print(f"[采集错误] {e}")


def keepalive_task():
    """会话保活任务"""
    try:
        monitor = get_monitor_instance()
        success = monitor.keepalive()
        if success:
            print(f"[保活] {datetime.now().strftime('%H:%M:%S')} 会话保活成功")
    except Exception as e:
        print(f"[保活错误] {e}")


def daily_report_task():
    """日报任务 - 发送前一天的完整数据"""
    try:
        cfg = config.get_config()
        reporter = ReporterService(cfg['pushme'])
        
        if reporter.enabled:
            # 发送前一天的日报
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            success = reporter.send_report(yesterday)
            print(f"[日报] {yesterday} 推送{'成功' if success else '失败'}")
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


def init_daily_stats():
    """初始化当日统计数据（启动时调用）"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 检查今天是否已有统计数据
        existing = storage.get_daily_stats(today)
        if existing:
            print(f"[统计初始化] {today} 已有统计数据，跳过")
            return
        
        # 尝试从今日记录计算
        records = storage.get_today_records()
        if records:
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
            print(f"[统计初始化] {today} 数据已从现有记录生成")
        else:
            # 没有记录时，创建空的初始数据
            storage.save_daily_stats(
                date=today,
                total_upload=0,
                total_download=0,
                device_count=0,
                max_connections=0,
                peak_device_count=0
            )
            print(f"[统计初始化] {today} 创建初始空数据")
    except Exception as e:
        print(f"[统计初始化错误] {e}")


def cleanup_traffic_history_task():
    """清理流量历史数据（保留7天）"""
    try:
        deleted = storage.cleanup_traffic_history(days=7)
        print(f"[清理] 流量历史数据已清理")
    except Exception as e:
        print(f"[清理错误] {e}")


def cleanup_all_task():
    """统一数据清理任务（每天凌晨3点执行）"""
    try:
        # 执行清理
        results = storage.cleanup_all({
            'online_records': 7,      # 在线记录保留7天
            'traffic_history': 7,     # 流量历史保留7天
            'device_events': 30,      # 设备事件保留30天
            'online_sessions': 30,    # 在线会话保留30天
            'alerts': 30,             # 已处理告警保留30天
            'daily_stats': 365        # 每日统计保留365天
        })
        
        # 打印清理结果
        total = sum(results.values())
        print(f"[数据清理] 共删除 {total} 条记录")
        for table, count in results.items():
            if count > 0:
                print(f"  - {table}: {count} 条")
        
        # 执行 VACUUM 回收空间
        storage.vacuum_database()
        
    except Exception as e:
        print(f"[数据清理错误] {e}")


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
    
    # 会话保活任务 - 在超时时间的50%间隔执行
    session_timeout = monitor_cfg.get('session_timeout', 120)  # 分钟
    keepalive_interval = int(session_timeout * 60 * 0.5)  # 转换为秒，取50%
    scheduler.add_job(keepalive_task, 'interval', seconds=keepalive_interval, id='keepalive')
    
    # 日报任务
    report_time = monitor_cfg.get('report_time', '07:00')
    hour, minute = map(int, report_time.split(':'))
    scheduler.add_job(daily_report_task, CronTrigger(hour=hour, minute=minute), id='daily_report')
    
    # 统计任务（每小时执行一次）
    scheduler.add_job(daily_stats_task, CronTrigger(minute=55), id='daily_stats')
    
    # 数据清理任务（每天凌晨3点）
    scheduler.add_job(cleanup_all_task, CronTrigger(hour=3, minute=0), id='cleanup_all')
    
    # 初始化当日统计数据
    init_daily_stats()
    
    scheduler.start()
    print(f"[调度] 采集间隔: {interval}秒, 保活间隔: {keepalive_interval}秒, 日报时间: {report_time}, 统计间隔: 每小时")