"""数据存储层 - SQLite 数据库操作"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.environ.get('DB_PATH', 'data/ihomeguard.db')


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
            
            -- 索引
            CREATE INDEX IF NOT EXISTS idx_devices_mac ON devices(mac);
            CREATE INDEX IF NOT EXISTS idx_online_records_mac ON online_records(mac);
            CREATE INDEX IF NOT EXISTS idx_online_records_time ON online_records(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date);
            CREATE INDEX IF NOT EXISTS idx_device_events_mac ON device_events(mac);
        ''')


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