"""配置管理模块"""
import json
import os
import hashlib
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from logger import get_logger

logger = get_logger('config')

# 加密密钥（基于机器特征生成）
def _get_encryption_key():
    """生成加密密钥"""
    # 使用固定盐值和机器信息生成密钥
    salt = b'ihomeguard_encryption_salt_v1'
    # 使用用户名作为密钥源（同一用户环境下稳定）
    key_source = os.environ.get('USERNAME', 'default') + 'ihomeguard_secret'
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(key_source.encode()))
    return Fernet(key)

_encryptor = None

def encrypt_value(value: str) -> str:
    """加密敏感数据"""
    if not value:
        return value
    global _encryptor
    if _encryptor is None:
        _encryptor = _get_encryption_key()
    return _encryptor.encrypt(value.encode()).decode()

def decrypt_value(value: str) -> str:
    """解密敏感数据"""
    if not value:
        return value
    global _encryptor
    if _encryptor is None:
        _encryptor = _get_encryption_key()
    try:
        return _encryptor.decrypt(value.encode()).decode()
    except Exception as e:
        # 如果解密失败，可能是未加密的旧数据
        logger.warning(f"解密失败: {e}")
        return value

# 智能检测运行环境，选择正确的配置路径
def _is_docker():
    """检测是否在 Docker 容器中"""
    # 检查 /.dockerenv 文件（Docker 容器特有）
    if os.path.exists('/.dockerenv'):
        return True
    # 检查 /proc/1/cgroup 是否包含 docker（Linux 容器特征）
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except Exception:
        pass
    # Windows 上肯定不是 Docker 容器
    if os.name == 'nt':
        return False
    return False

def _get_config_path():
    """获取配置文件路径"""
    # 优先使用环境变量
    env_path = os.environ.get('CONFIG_PATH')
    if env_path:
        return env_path
    
    # Docker 环境
    if _is_docker():
        return '/app/config/config.json'
    
    # 本地开发环境，使用项目目录
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')

def _get_data_dir():
    """获取数据目录路径"""
    env_dir = os.environ.get('DATA_DIR')
    if env_dir:
        return env_dir
    
    if _is_docker():
        return '/app/data'
    
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

CONFIG_PATH = _get_config_path()
DATA_DIR = _get_data_dir()

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
        _config = get_default_config()
        
        # 从配置文件加载
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                for key in file_config:
                    if isinstance(file_config[key], dict):
                        _config[key].update(file_config[key])
                    else:
                        _config[key] = file_config[key]
        
        # 解密敏感字段
        for field in SENSITIVE_FIELDS:
            for section in ['ikuai', 'pushme']:
                if section in _config and field in _config[section]:
                    encrypted = _config[section].get(field, '')
                    if encrypted and encrypted.startswith('enc:'):
                        _config[section][field] = decrypt_value(encrypted[4:])
        
        # 环境变量覆盖（优先级高于配置文件）
        if os.environ.get('IKUAI_URL'):
            _config['ikuai']['local_url'] = os.environ['IKUAI_URL']
        if os.environ.get('IKUAI_USER'):
            _config['ikuai']['username'] = os.environ['IKUAI_USER']
        if os.environ.get('IKUAI_PASS'):
            _config['ikuai']['password'] = os.environ['IKUAI_PASS']
        if os.environ.get('PUSHME_KEY'):
            _config['pushme']['push_key'] = os.environ['PUSHME_KEY']
        
        # 如果通过环境变量提供了完整配置，标记为已验证
        if (os.environ.get('IKUAI_URL') and os.environ.get('IKUAI_USER') and 
            os.environ.get('IKUAI_PASS')):
            _config['ikuai']['connection_validated'] = True
    
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
            "password": os.environ.get('IKUAI_PASS', ''),
            "connection_validated": False
        },
        "pushme": {
            "push_key": os.environ.get('PUSHME_KEY', ''),
            "api_url": "https://push.i-i.me",
            "enabled": True
        },
        "monitor": {
            "collect_interval": 5,
            "report_time": "07:00",
            "alert_new_device": True,
            "alert_startup": True,
            "alert_offline": True,
            "traffic_threshold_gb": 10,
            "long_online_hours": 24,
            "high_connection_threshold": 500,
            "total_connection_threshold": 1000,
            "session_timeout": 120,
            "upload_speed_threshold_kbps": 10240,
            "download_speed_threshold_kbps": 51200
        },
        "web": {
            "host": "0.0.0.0",
            "port": 8680
        },
        "auth": {
            "enabled": bool(os.environ.get('AUTH_TOKEN', '')),
            "token": os.environ.get('AUTH_TOKEN', '')
        }
    }


def save_config(config: dict):
    """保存配置到文件"""
    global _config
    _config = config
    
    config_dir = os.path.dirname(CONFIG_PATH)
    logger.debug(f"CONFIG_PATH={CONFIG_PATH}, config_dir={config_dir}")
    
    if config_dir:
        os.makedirs(config_dir, exist_ok=True)
        logger.debug(f"创建目录: {config_dir}")
    
    # 加密敏感字段后保存
    config_to_save = json.loads(json.dumps(config))  # 深拷贝
    for field in SENSITIVE_FIELDS:
        for section in ['ikuai', 'pushme']:
            if section in config_to_save and field in config_to_save[section]:
                value = config_to_save[section].get(field, '')
                if value and not value.startswith('enc:'):
                    config_to_save[section][field] = 'enc:' + encrypt_value(value)
    
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        logger.info(f"配置保存成功: {CONFIG_PATH}")
    except Exception as e:
        logger.error(f"配置保存失败: {e}")
        raise


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
    if not value:
        return ''
    if len(value) <= show_len:
        return '****'
    return value[:show_len] + '****'


# 敏感配置字段（push_key 不加密，方便调试和跨环境使用）
SENSITIVE_FIELDS = ['password']