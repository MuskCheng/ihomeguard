"""数据存储层 - SQLite 数据库操作"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
from logger import get_logger

logger = get_logger('storage')

# 使用 config 模块中的 DATA_DIR
def _get_db_path():
    """获取数据库路径"""
    env_path = os.environ.get('DB_PATH')
    if env_path:
        return env_path
    
    # 延迟导入避免循环依赖
    try:
        import config
        return os.path.join(config.DATA_DIR, 'ihomeguard.db')
    except:
        return 'data/ihomeguard.db'

DB_PATH = _get_db_path()


@contextmanager
def get_db():
    """获取数据库连接上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with get_db() as conn:
        conn.executescript('''
            -- 设备信息表
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac TEXT UNIQUE NOT NULL,
                ip TEXT,
                hostname TEXT,
                alias TEXT,
                vendor TEXT,
                device_type TEXT DEFAULT 'unknown',
                is_trusted INTEGER DEFAULT 0,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME,
                total_online_minutes INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 在线记录表
            CREATE TABLE IF NOT EXISTS online_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac TEXT NOT NULL,
                ip TEXT,
                upload_bytes INTEGER DEFAULT 0,
                download_bytes INTEGER DEFAULT 0,
                upload_speed INTEGER DEFAULT 0,
                download_speed INTEGER DEFAULT 0,
                connections INTEGER DEFAULT 0,
                recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mac) REFERENCES devices(mac)
            );
            
            -- 每日统计表
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                total_upload INTEGER DEFAULT 0,
                total_download INTEGER DEFAULT 0,
                device_count INTEGER DEFAULT 0,
                max_connections INTEGER DEFAULT 0,
                peak_device_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 告警记录表
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                mac TEXT,
                message TEXT,
                is_resolved INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME
            );
            
            -- 设备上下线事件表
            CREATE TABLE IF NOT EXISTS device_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ip TEXT,
                happened_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 在线会话表（精确追踪在线时长）
            CREATE TABLE IF NOT EXISTS online_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac TEXT NOT NULL,
                ip TEXT,
                online_at DATETIME NOT NULL,
                offline_at DATETIME,
                duration_minutes INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 流量历史表（实时监控数据）
            CREATE TABLE IF NOT EXISTS traffic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                upload_speed INTEGER DEFAULT 0,
                download_speed INTEGER DEFAULT 0,
                device_count INTEGER DEFAULT 0
            );
            
            -- 索引
            CREATE INDEX IF NOT EXISTS idx_devices_mac ON devices(mac);
            CREATE INDEX IF NOT EXISTS idx_online_records_mac ON online_records(mac);
            CREATE INDEX IF NOT EXISTS idx_online_records_time ON online_records(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date);
            CREATE INDEX IF NOT EXISTS idx_device_events_mac ON device_events(mac);
            CREATE INDEX IF NOT EXISTS idx_online_sessions_mac ON online_sessions(mac);
            CREATE INDEX IF NOT EXISTS idx_online_sessions_online ON online_sessions(online_at);
            CREATE INDEX IF NOT EXISTS idx_traffic_history_time ON traffic_history(timestamp);
        ''')
        
        # 数据库迁移：检查并添加缺失的列
        _migrate_database(conn)


def _migrate_database(conn):
    """数据库迁移：添加缺失的列"""
    migrations = [
        # (表名, 列名, 列定义)
        ('devices', 'total_online_minutes', 'INTEGER DEFAULT 0'),
        ('devices', 'device_type', "TEXT DEFAULT 'unknown'"),
        ('traffic_history', 'connection_count', 'INTEGER DEFAULT 0'),
    ]

    for table, column, definition in migrations:
        try:
            # 检查列是否存在
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            if column not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                logger.info(f"数据库迁移: {table}.{column} 列已添加")
        except Exception as e:
            logger.warning(f"数据库迁移: {table}.{column}: {e}")


# ========== 设备操作 ==========

def upsert_device(mac: str, ip: str = None, hostname: str = None):
    """插入或更新设备"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute('''
            INSERT INTO devices (mac, ip, hostname, first_seen, last_seen, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip = excluded.ip,
                hostname = COALESCE(excluded.hostname, hostname),
                last_seen = excluded.last_seen,
                updated_at = excluded.updated_at
        ''', (mac.upper(), ip, hostname, now, now, now))


def update_device_alias(mac: str, alias: str, is_trusted: bool = None):
    """更新设备备注"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        if is_trusted is not None:
            conn.execute('''
                UPDATE devices SET alias = ?, is_trusted = ?, updated_at = ? WHERE mac = ?
            ''', (alias, 1 if is_trusted else 0, now, mac.upper()))
        else:
            conn.execute('''
                UPDATE devices SET alias = ?, updated_at = ? WHERE mac = ?
            ''', (alias, now, mac.upper()))


def get_device(mac: str) -> dict:
    """获取单个设备信息"""
    with get_db() as conn:
        row = conn.execute('SELECT * FROM devices WHERE mac = ?', (mac.upper(),)).fetchone()
        return dict(row) if row else None


def get_devices_by_macs(macs: list) -> dict:
    """批量获取设备信息，返回 {mac: device_info} 字典"""
    if not macs:
        return {}
    
    # 统一转大写
    macs_upper = [mac.upper() for mac in macs]
    placeholders = ','.join('?' * len(macs_upper))
    
    with get_db() as conn:
        rows = conn.execute(f'SELECT * FROM devices WHERE mac IN ({placeholders})', macs_upper).fetchall()
        return {row['mac']: dict(row) for row in rows}


def get_all_devices() -> list:
    """获取所有设备"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('SELECT * FROM devices ORDER BY last_seen DESC')]


# ========== 在线记录操作 ==========

def add_online_record(mac: str, ip: str, upload: int, download: int, 
                      upload_speed: int, download_speed: int, connections: int):
    """添加在线记录"""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO online_records 
            (mac, ip, upload_bytes, download_bytes, upload_speed, download_speed, connections)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (mac.upper(), ip, upload, download, upload_speed, download_speed, connections))


def get_today_records() -> list:
    """获取今日记录"""
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM online_records 
            WHERE date(recorded_at) = ?
            ORDER BY recorded_at DESC
        ''', (today,))]


def get_records_by_date(date: str) -> list:
    """获取指定日期的记录"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM online_records 
            WHERE date(recorded_at) = ?
            ORDER BY recorded_at ASC
        ''', (date,))]


# ========== 统计操作 ==========

def save_daily_stats(date: str, total_upload: int, total_download: int,
                     device_count: int, max_connections: int, peak_device_count: int):
    """保存每日统计"""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO daily_stats 
            (date, total_upload, total_download, device_count, max_connections, peak_device_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_upload = excluded.total_upload,
                total_download = excluded.total_download,
                device_count = excluded.device_count,
                max_connections = excluded.max_connections,
                peak_device_count = excluded.peak_device_count
        ''', (date, total_upload, total_download, device_count, max_connections, peak_device_count))


def get_daily_stats(date: str) -> dict:
    """获取指定日期统计"""
    with get_db() as conn:
        row = conn.execute('SELECT * FROM daily_stats WHERE date = ?', (date,)).fetchone()
        return dict(row) if row else None


def get_stats_range(start_date: str, end_date: str) -> list:
    """获取日期范围统计"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM daily_stats 
            WHERE date BETWEEN ? AND ?
            ORDER BY date
        ''', (start_date, end_date))]


# ========== 流量历史操作 ==========

def save_traffic_snapshot(upload_speed: int, download_speed: int, device_count: int, connection_count: int = 0):
    """保存流量快照"""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO traffic_history (timestamp, upload_speed, download_speed, device_count, connection_count)
            VALUES (datetime('now', 'localtime'), ?, ?, ?, ?)
        ''', (upload_speed, download_speed, device_count, connection_count))


def get_traffic_history(hours: float = 1) -> list:
    """获取指定小时范围内的流量历史（支持小数，如 0.5 表示 30 分钟）
    
    每分钟只取该分钟内最后一条记录，确保数据点唯一且准确
    """
    with get_db() as conn:
        # 使用子查询获取每分钟最后一条记录的 rowid
        return [dict(row) for row in conn.execute('''
            SELECT
                strftime('%Y-%m-%d %H:%M', t.timestamp) as time,
                t.upload_speed,
                t.download_speed,
                t.device_count,
                t.connection_count
            FROM traffic_history t
            INNER JOIN (
                SELECT 
                    strftime('%Y-%m-%d %H:%M', timestamp) as minute,
                    MAX(rowid) as max_rowid
                FROM traffic_history
                WHERE timestamp >= datetime('now', 'localtime', ?)
                GROUP BY strftime('%Y-%m-%d %H:%M', timestamp)
            ) latest ON t.rowid = latest.max_rowid
            WHERE t.timestamp >= datetime('now', 'localtime', ?)
            ORDER BY t.timestamp ASC
        ''', (f'-{hours} hours', f'-{hours} hours'))]


def cleanup_traffic_history(days: int = 1):
    """清理超过指定天数的流量历史数据（默认保留24小时）"""
    with get_db() as conn:
        conn.execute('''
            DELETE FROM traffic_history 
            WHERE timestamp < datetime('now', 'localtime', ?)
        ''', (f'-{days} days',))


# ========== 告警操作 ==========

def add_alert(alert_type: str, severity: str, mac: str, message: str) -> int:
    """添加告警"""
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO alerts (alert_type, severity, mac, message)
            VALUES (?, ?, ?, ?)
        ''', (alert_type, severity, mac, message))
        return cursor.lastrowid


def get_unresolved_alerts() -> list:
    """获取未处理告警"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM alerts WHERE is_resolved = 0 ORDER BY created_at DESC
        ''')]


def get_alerts_by_type_date(alert_type: str, mac: str, date: str) -> dict:
    """检查指定类型、设备、日期是否已有告警"""
    with get_db() as conn:
        row = conn.execute('''
            SELECT * FROM alerts
            WHERE alert_type = ? AND mac = ? AND date(created_at) = ?
            LIMIT 1
        ''', (alert_type, mac.upper(), date)).fetchone()
        return dict(row) if row else None


def get_recent_alerts_by_type(alert_type: str, mac: str, minutes: int = 10) -> list:
    """检查指定类型、设备在最近N分钟内是否已有告警"""
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM alerts
            WHERE alert_type = ? AND mac = ? AND created_at >= datetime('now', ?)
        ''', (alert_type, mac.upper(), f'-{minutes} minutes')).fetchall()
        return [dict(row) for row in rows]


def get_recent_alerts_by_type_all(alert_type: str, minutes: int = 10) -> list:
    """检查指定类型在最近N分钟内是否已有告警（不限定设备）"""
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM alerts
            WHERE alert_type = ? AND created_at >= datetime('now', ?)
        ''', (alert_type, f'-{minutes} minutes')).fetchall()
        return [dict(row) for row in rows]


def resolve_alert(alert_id: int):
    """处理告警"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        conn.execute('''
            UPDATE alerts SET is_resolved = 1, resolved_at = ? WHERE id = ?
        ''', (now, alert_id))


def get_recent_alerts(limit: int = 20) -> list:
    """获取最近告警"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?
        ''', (limit,))]


# ========== 事件操作 ==========

def add_device_event(mac: str, event_type: str, ip: str = None):
    """添加设备事件"""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO device_events (mac, event_type, ip)
            VALUES (?, ?, ?)
        ''', (mac.upper(), event_type, ip))


def get_device_events(mac: str, limit: int = 50) -> list:
    """获取设备事件历史"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM device_events WHERE mac = ?
            ORDER BY happened_at DESC LIMIT ?
        ''', (mac.upper(), limit))]


def get_events_by_date(date: str, limit: int = 100) -> list:
    """获取指定日期的所有事件"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM device_events 
            WHERE date(happened_at) = ?
            ORDER BY happened_at DESC LIMIT ?
        ''', (date, limit))]


# ========== 在线会话操作 ==========

def start_online_session(mac: str, ip: str):
    """开始在线会话"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        # 检查是否有未关闭的会话
        existing = conn.execute('''
            SELECT id FROM online_sessions 
            WHERE mac = ? AND offline_at IS NULL
        ''', (mac.upper(),)).fetchone()
        
        if not existing:
            conn.execute('''
                INSERT INTO online_sessions (mac, ip, online_at)
                VALUES (?, ?, ?)
            ''', (mac.upper(), ip, now))


def end_online_session(mac: str):
    """结束在线会话"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        # 找到未关闭的会话
        session = conn.execute('''
            SELECT id, online_at FROM online_sessions 
            WHERE mac = ? AND offline_at IS NULL
        ''', (mac.upper(),)).fetchone()
        
        if session:
            online_at = datetime.fromisoformat(session['online_at'])
            offline_at = datetime.now()
            duration_minutes = int((offline_at - online_at).total_seconds() / 60)
            
            conn.execute('''
                UPDATE online_sessions 
                SET offline_at = ?, duration_minutes = ?
                WHERE id = ?
            ''', (now, duration_minutes, session['id']))
            
            # 更新设备累计在线时长
            conn.execute('''
                UPDATE devices 
                SET total_online_minutes = total_online_minutes + ?
                WHERE mac = ?
            ''', (duration_minutes, mac.upper()))


def get_device_online_sessions(mac: str, limit: int = 50) -> list:
    """获取设备在线会话历史"""
    with get_db() as conn:
        return [dict(row) for row in conn.execute('''
            SELECT * FROM online_sessions 
            WHERE mac = ?
            ORDER BY online_at DESC LIMIT ?
        ''', (mac.upper(), limit))]


def get_device_total_online_time(mac: str) -> int:
    """获取设备累计在线时长（分钟）"""
    with get_db() as conn:
        row = conn.execute('''
            SELECT total_online_minutes FROM devices WHERE mac = ?
        ''', (mac.upper(),)).fetchone()
        return row['total_online_minutes'] if row else 0


def get_today_online_time(mac: str) -> int:
    """获取设备今日在线时长（分钟）"""
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as conn:
        result = conn.execute('''
            SELECT COALESCE(SUM(duration_minutes), 0) as total
            FROM online_sessions 
            WHERE mac = ? AND date(online_at) = ?
        ''', (mac.upper(), today)).fetchone()
        
        total = result['total'] if result else 0
        
        # 加上当前在线时间
        session = conn.execute('''
            SELECT online_at FROM online_sessions 
            WHERE mac = ? AND offline_at IS NULL
        ''', (mac.upper(),)).fetchone()
        
        if session:
            online_at = datetime.fromisoformat(session['online_at'])
            current_minutes = int((datetime.now() - online_at).total_seconds() / 60)
            total += current_minutes
        
        return total


def get_all_today_online_time() -> dict:
    """批量获取所有设备今日在线时长（分钟），返回 {mac: minutes} 字典"""
    today = datetime.now().strftime('%Y-%m-%d')
    result = {}
    
    with get_db() as conn:
        # 一次性查询所有设备今日已完成的在线时长
        rows = conn.execute('''
            SELECT mac, COALESCE(SUM(duration_minutes), 0) as total
            FROM online_sessions 
            WHERE date(online_at) = ?
            GROUP BY mac
        ''', (today,)).fetchall()
        
        for row in rows:
            result[row['mac']] = row['total']
        
        # 查询所有当前在线的设备，加上当前在线时间
        active_sessions = conn.execute('''
            SELECT mac, online_at FROM online_sessions 
            WHERE offline_at IS NULL
        ''').fetchall()
        
        for session in active_sessions:
            mac = session['mac']
            online_at = datetime.fromisoformat(session['online_at'])
            current_minutes = int((datetime.now() - online_at).total_seconds() / 60)
            result[mac] = result.get(mac, 0) + current_minutes
    
    return result


# ========== 设备在线时长统计 ==========

def get_device_online_time(mac: str, date: str = None) -> int:
    """获取设备指定日期在线时长（分钟）"""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    with get_db() as conn:
        # 计算在线事件到离线事件的时间差
        events = conn.execute('''
            SELECT event_type, happened_at FROM device_events 
            WHERE mac = ? AND date(happened_at) = ?
            ORDER BY happened_at
        ''', (mac.upper(), date)).fetchall()
        
        total_minutes = 0
        last_online = None
        
        for event in events:
            if event['event_type'] == 'online':
                last_online = datetime.fromisoformat(event['happened_at'])
            elif event['event_type'] == 'offline' and last_online:
                offline_time = datetime.fromisoformat(event['happened_at'])
                total_minutes += (offline_time - last_online).total_seconds() / 60
                last_online = None
        
        # 如果最后是在线状态，计算到当前时间
        if last_online:
            total_minutes += (datetime.now() - last_online).total_seconds() / 60
        
        return int(total_minutes)


# ========== 数据清理操作 ==========

def cleanup_online_records(days: int = 7):
    """清理超过指定天数的在线记录"""
    with get_db() as conn:
        result = conn.execute('''
            DELETE FROM online_records 
            WHERE recorded_at < datetime('now', 'localtime', ?)
        ''', (f'-{days} days',))
        return result.rowcount


def cleanup_device_events(days: int = 30):
    """清理超过指定天数的设备事件"""
    with get_db() as conn:
        result = conn.execute('''
            DELETE FROM device_events 
            WHERE happened_at < datetime('now', 'localtime', ?)
        ''', (f'-{days} days',))
        return result.rowcount


def cleanup_online_sessions(days: int = 30):
    """清理超过指定天数的在线会话"""
    with get_db() as conn:
        result = conn.execute('''
            DELETE FROM online_sessions 
            WHERE online_at < datetime('now', 'localtime', ?)
        ''', (f'-{days} days',))
        return result.rowcount


def cleanup_resolved_alerts(days: int = 30):
    """清理超过指定天数的已处理告警"""
    with get_db() as conn:
        result = conn.execute('''
            DELETE FROM alerts 
            WHERE is_resolved = 1 AND created_at < datetime('now', 'localtime', ?)
        ''', (f'-{days} days',))
        return result.rowcount


def cleanup_old_daily_stats(days: int = 365):
    """清理超过指定天数的每日统计"""
    with get_db() as conn:
        result = conn.execute('''
            DELETE FROM daily_stats 
            WHERE date < date('now', 'localtime', ?)
        ''', (f'-{days} days',))
        return result.rowcount


def vacuum_database():
    """执行数据库 VACUUM 操作，回收空间"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('VACUUM')
        logger.info("数据库 VACUUM 完成，空间已回收")
    except Exception as e:
        logger.error(f"数据库 VACUUM 失败: {e}")
        raise
    finally:
        conn.close()


def get_database_stats() -> dict:
    """获取数据库统计信息"""
    with get_db() as conn:
        stats = {
            'devices': conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0],
            'online_records': conn.execute('SELECT COUNT(*) FROM online_records').fetchone()[0],
            'traffic_history': conn.execute('SELECT COUNT(*) FROM traffic_history').fetchone()[0],
            'daily_stats': conn.execute('SELECT COUNT(*) FROM daily_stats').fetchone()[0],
            'alerts': conn.execute('SELECT COUNT(*) FROM alerts').fetchone()[0],
            'device_events': conn.execute('SELECT COUNT(*) FROM device_events').fetchone()[0],
            'online_sessions': conn.execute('SELECT COUNT(*) FROM online_sessions').fetchone()[0],
        }
        
        # 获取数据库文件大小
        if os.path.exists(DB_PATH):
            stats['db_size_mb'] = round(os.path.getsize(DB_PATH) / 1024 / 1024, 2)
        else:
            stats['db_size_mb'] = 0
        
        return stats


def cleanup_all(retention_config: dict = None):
    """执行所有数据清理
    
    retention_config: {
        'online_records': 7,      # 在线记录保留天数
        'traffic_history': 7,     # 流量历史保留天数
        'device_events': 30,      # 设备事件保留天数
        'online_sessions': 30,    # 在线会话保留天数
        'alerts': 30,             # 已处理告警保留天数
        'daily_stats': 365        # 每日统计保留天数
    }
    """
    if retention_config is None:
        retention_config = {}
    
    results = {}
    
    # 在线记录
    days = retention_config.get('online_records', 7)
    results['online_records'] = cleanup_online_records(days)
    
    # 流量历史
    days = retention_config.get('traffic_history', 7)
    results['traffic_history'] = cleanup_traffic_history(days)
    
    # 设备事件
    days = retention_config.get('device_events', 30)
    results['device_events'] = cleanup_device_events(days)
    
    # 在线会话
    days = retention_config.get('online_sessions', 30)
    results['online_sessions'] = cleanup_online_sessions(days)
    
    # 已处理告警
    days = retention_config.get('alerts', 30)
    results['alerts'] = cleanup_resolved_alerts(days)
    
    # 每日统计
    days = retention_config.get('daily_stats', 365)
    results['daily_stats'] = cleanup_old_daily_stats(days)
    
    return results