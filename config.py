"""配置管理模块"""
import json
import os
import hashlib

CONFIG_PATH = os.environ.get('CONFIG_PATH', 'config/config.json')
DATA_DIR = os.environ.get('DATA_DIR', 'data')

# 版本号从 VERSION 文件读取
def get_version():
    """获取版本号"""
    version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return 'unknown'

VERSION = get_version()

_config = None


def get_config():
    global _config
    if _config is None:
        # 优先从环境变量读取敏感信息
        _config = get_default_config()
        
        # 环境变量覆盖
        if os.environ.get('IKUAI_URL'):
            _config['ikuai']['local_url'] = os.environ['IKUAI_URL']
        if os.environ.get('IKUAI_USER'):
            _config['ikuai']['username'] = os.environ['IKUAI_USER']
        if os.environ.get('IKUAI_PASS'):
            _config['ikuai']['password'] = os.environ['IKUAI_PASS']
        if os.environ.get('PUSHME_KEY'):
            _config['pushme']['push_key'] = os.environ['PUSHME_KEY']
        
        # 从配置文件加载（覆盖默认值，但不覆盖环境变量）
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                for key in file_config:
                    if key not in ['ikuai', 'pushme'] or not os.environ.get(f'{key.upper()}_URL') and not os.environ.get(f'{key.upper()}_KEY'):
                        if isinstance(file_config[key], dict):
                            _config[key].update(file_config[key])
                        else:
                            _config[key] = file_config[key]
    
    return _config


def get_default_config():
    return {
        "app": {
            "name": "iHomeGuard",
            "version": VERSION
        },
        "ikuai": {
            "local_url": os.environ.get('IKUAI_URL', 'http://192.168.1.1'),
            "username": os.environ.get('IKUAI_USER', 'admin'),
            "password": os.environ.get('IKUAI_PASS', '')
        },
        "pushme": {
            "push_key": os.environ.get('PUSHME_KEY', ''),
            "api_url": "https://push.i-i.me",
            "enabled": True
        },
        "monitor": {
            "collect_interval": 300,
            "report_time": "21:00",
            "alert_new_device": True,
            "traffic_threshold_gb": 10,
            "long_online_hours": 24,
            "high_connection_threshold": 500
        },
        "web": {
            "host": "0.0.0.0",
            "port": 8680
        }
    }


def save_config(config: dict):
    """保存配置到文件"""
    global _config
    _config = config
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    
    # 保存时排除敏感信息（如果环境变量已设置）
    save_data = config.copy()
    if os.environ.get('IKUAI_PASS'):
        save_data['ikuai']['password'] = '***'
    if os.environ.get('PUSHME_KEY'):
        save_data['pushme']['push_key'] = '***'
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)


def update_config(section: str, key: str, value):
    """更新单个配置项"""
    config = get_config()
    if section in config and isinstance(config[section], dict):
        config[section][key] = value
        save_config(config)
        return True
    return False


def validate_config() -> tuple:
    """验证配置是否完整
    
    Returns:
        (is_valid, missing_fields)
    """
    config = get_config()
    missing = []
    
    if not config['ikuai'].get('local_url'):
        missing.append('ikuai.local_url')
    if not config['ikuai'].get('username'):
        missing.append('ikuai.username')
    if not config['ikuai'].get('password'):
        missing.append('ikuai.password')
    
    return len(missing) == 0, missing


def mask_sensitive(value: str, show_len: int = 4) -> str:
    """脱敏显示敏感信息"""
    if not value or len(value) <= show_len:
        return '****'
    return value[:show_len] + '****'


# 敏感配置字段
SENSITIVE_FIELDS = ['password', 'push_key']