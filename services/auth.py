"""认证中间件模块 - 支持挑战-响应认证、登录限制、JWT Token"""
import os
import secrets
import hashlib
import time
from functools import wraps
from datetime import datetime, timedelta
from flask import request, jsonify, g

# 日志
def _get_logger():
    try:
        from logger import get_logger
        return get_logger('auth')
    except Exception:
        import logging
        return logging.getLogger('auth')

logger = _get_logger()

# 延迟导入，避免循环依赖
def _import_bcrypt():
    try:
        import bcrypt
        return bcrypt
    except ImportError:
        return None

def _import_jwt():
    try:
        import jwt
        return jwt
    except ImportError:
        return None


# ========== 配置常量 ==========
MAX_FAILED_ATTEMPTS = 5          # 最大失败次数
LOCKOUT_DURATION = 300           # 锁定时长（秒）
CHALLENGE_EXPIRE = 60            # 挑战码有效期（秒）
JWT_EXPIRE_HOURS = 2             # JWT Token 有效期（小时）
JWT_ALGORITHM = 'HS256'


# ========== 内存缓存（单实例足够） ==========
# 生产环境建议使用 Redis
_challenge_cache = {}    # session_id -> {challenge, expire}
_lockout_cache = {}      # username -> {failed_count, lockout_until}


def _get_jwt_secret() -> str:
    """获取 JWT 密钥"""
    # 优先从环境变量
    secret = os.environ.get('JWT_SECRET')
    if secret:
        return secret
    
    # 从配置文件获取
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        secret = auth_cfg.get('jwt_secret')
        if secret:
            return secret
    except Exception:
        pass
    
    # 生成默认密钥（基于机器特征）
    machine_id = os.environ.get('USERNAME', 'default') + 'ihomeguard_jwt_secret'
    return hashlib.sha256(machine_id.encode()).hexdigest()


# ========== 密码哈希函数 ==========

def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码
    
    Returns:
        bcrypt 哈希后的密码字符串
    """
    bcrypt = _import_bcrypt()
    if bcrypt:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    else:
        # 降级方案：SHA256 + 随机盐
        salt = secrets.token_hex(16)
        hash_val = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"sha256:{salt}:{hash_val}"


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码
    
    Args:
        password: 用户输入的密码
        password_hash: 存储的密码哈希
    
    Returns:
        是否验证通过
    """
    if not password or not password_hash:
        return False
    
    bcrypt = _import_bcrypt()
    
    # bcrypt 格式
    if password_hash.startswith('$2b$') or password_hash.startswith('$2a$'):
        if bcrypt:
            try:
                return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
            except Exception:
                return False
        return False
    
    # 降级格式 sha256:salt:hash
    if password_hash.startswith('sha256:'):
        parts = password_hash.split(':')
        if len(parts) == 3:
            _, salt, stored_hash = parts
            computed = hashlib.sha256((password + salt).encode()).hexdigest()
            return secrets.compare_digest(computed, stored_hash)
    
    # 旧的明文 Token 格式（向后兼容）
    return secrets.compare_digest(password, password_hash)


# ========== 挑战-响应认证 ==========

def generate_challenge(session_id: str = None) -> dict:
    """生成挑战码
    
    Args:
        session_id: 可选的会话ID，不提供则自动生成
    
    Returns:
        {'session_id': str, 'challenge': str, 'expire': int}
    """
    if not session_id:
        session_id = secrets.token_hex(16)
    
    challenge = secrets.token_hex(32)
    expire = int(time.time()) + CHALLENGE_EXPIRE
    
    _challenge_cache[session_id] = {
        'challenge': challenge,
        'expire': expire
    }
    
    # 清理过期挑战码
    _cleanup_challenges()
    
    return {
        'session_id': session_id,
        'challenge': challenge,
        'expire': CHALLENGE_EXPIRE
    }


def get_challenge(session_id: str) -> str:
    """获取挑战码"""
    data = _challenge_cache.get(session_id)
    if not data:
        return None
    if time.time() > data['expire']:
        del _challenge_cache[session_id]
        return None
    return data['challenge']


def clear_challenge(session_id: str):
    """清除挑战码"""
    _challenge_cache.pop(session_id, None)


def _cleanup_challenges():
    """清理过期挑战码"""
    now = time.time()
    expired = [sid for sid, data in _challenge_cache.items() if now > data['expire']]
    for sid in expired:
        del _challenge_cache[sid]


def compute_challenge_response(password: str, challenge: str) -> str:
    """计算挑战响应签名
    
    客户端使用此函数计算签名：
    signature = SHA256(password + challenge)
    
    Args:
        password: 用户密码
        challenge: 服务器返回的挑战码
    
    Returns:
        签名字符串
    """
    return hashlib.sha256((password + challenge).encode()).hexdigest()


# ========== 登录限制 ==========

def check_lockout(username: str) -> tuple:
    """检查账户是否被锁定
    
    Returns:
        (is_locked: bool, message: str)
    """
    data = _lockout_cache.get(username)
    if not data:
        return False, None
    
    lockout_until = data.get('lockout_until')
    if lockout_until and time.time() < lockout_until:
        remaining = int(lockout_until - time.time())
        return True, f'账户已锁定，请 {remaining} 秒后重试'
    
    return False, None


def record_failed_attempt(username: str):
    """记录登录失败"""
    data = _lockout_cache.get(username, {'failed_count': 0, 'lockout_until': None})
    data['failed_count'] = data.get('failed_count', 0) + 1
    
    if data['failed_count'] >= MAX_FAILED_ATTEMPTS:
        data['lockout_until'] = time.time() + LOCKOUT_DURATION
        data['failed_count'] = 0
    
    _lockout_cache[username] = data


def clear_failed_attempts(username: str):
    """清除登录失败记录"""
    _lockout_cache.pop(username, None)


def get_remaining_attempts(username: str) -> int:
    """获取剩余尝试次数"""
    data = _lockout_cache.get(username)
    if not data:
        return MAX_FAILED_ATTEMPTS
    return max(0, MAX_FAILED_ATTEMPTS - data.get('failed_count', 0))


# ========== JWT Token ==========

def create_jwt_token(username: str, **extra_claims) -> str:
    """创建 JWT Token
    
    Args:
        username: 用户名
        **extra_claims: 额外的 claims
    
    Returns:
        JWT Token 字符串
    """
    jwt = _import_jwt()
    if not jwt:
        # 降级：返回简单 token
        return secrets.token_hex(32)
    
    payload = {
        'username': username,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        **extra_claims
    }
    
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> dict:
    """验证 JWT Token
    
    Args:
        token: JWT Token 字符串
    
    Returns:
        解码后的 payload，验证失败返回 None
    """
    if not token:
        return None
    
    jwt = _import_jwt()
    if not jwt:
        # 降级：简单 token 验证
        return {'username': 'user'} if len(token) >= 32 else None
    
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ========== 用户管理 ==========

def get_user(username: str) -> dict:
    """获取用户信息
    
    Returns:
        {'username': str, 'password_hash': str, 'role': str} 或 None
    """
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        
        # 新格式：用户列表
        users = auth_cfg.get('users', [])
        for user in users:
            if user.get('username') == username:
                return user
        
        # 旧格式：单一 token（向后兼容）
        if auth_cfg.get('token') and username == 'admin':
            return {
                'username': 'admin',
                'password_hash': auth_cfg.get('token'),
                'role': 'admin'
            }
        
        return None
    except Exception:
        return None


def get_all_users() -> list:
    """获取所有用户（不含密码）"""
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        users = auth_cfg.get('users', [])
        
        # 返回不含密码的用户列表
        return [{k: v for k, v in u.items() if k != 'password_hash'} for u in users]
    except Exception:
        return []


def create_user(username: str, password: str, role: str = 'user') -> bool:
    """创建用户
    
    Returns:
        是否创建成功
    """
    try:
        import config
        cfg = config.get_config()
        
        if 'auth' not in cfg:
            cfg['auth'] = {}
        if 'users' not in cfg['auth']:
            cfg['auth']['users'] = []
        
        # 检查用户是否已存在
        for user in cfg['auth']['users']:
            if user.get('username') == username:
                return False
        
        # 添加新用户
        cfg['auth']['users'].append({
            'username': username,
            'password_hash': hash_password(password),
            'role': role,
            'created_at': datetime.now().isoformat()
        })
        
        config.save_config(cfg)
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def update_user_password(username: str, new_password: str) -> bool:
    """更新用户密码"""
    try:
        import config
        cfg = config.get_config()
        users = cfg.get('auth', {}).get('users', [])
        
        for user in users:
            if user.get('username') == username:
                user['password_hash'] = hash_password(new_password)
                config.save_config(cfg)
                return True
        
        return False
    except Exception:
        return False


def delete_user(username: str) -> bool:
    """删除用户"""
    try:
        import config
        cfg = config.get_config()
        users = cfg.get('auth', {}).get('users', [])
        
        for i, user in enumerate(users):
            if user.get('username') == username:
                users.pop(i)
                config.save_config(cfg)
                return True
        
        return False
    except Exception:
        return False


# ========== 认证检查 ==========

def is_auth_enabled() -> bool:
    """检查是否启用认证
    
    只要 auth.enabled 为 True 就返回 True
    不管是否有用户（没有用户时会显示注册页面）
    """
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        
        # 检查是否启用
        return auth_cfg.get('enabled', False)
        
    except Exception:
        return False


def check_auth(token: str) -> bool:
    """验证 Token 是否有效
    
    Args:
        token: 客户端提供的 token (JWT 或旧格式)
    
    Returns:
        是否验证通过
    """
    if not is_auth_enabled():
        return True  # 未启用认证，直接通过
    
    # 尝试 JWT 验证
    payload = verify_jwt_token(token)
    if payload:
        username = payload.get('username')
        if username:
            return get_user(username) is not None
    
    # 向后兼容：旧 token 格式
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        old_token = auth_cfg.get('token', '')
        if old_token and secrets.compare_digest(token, old_token):
            return True
    except Exception:
        pass
    
    return False


def get_token_from_request() -> str:
    """从请求中提取 Token
    
    支持三种方式：
    1. Authorization Header: Bearer <token>
    2. Cookie: auth_token=<token>
    3. Query Parameter: ?token=<token> (仅用于特殊场景)
    """
    # 1. Authorization Header
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    # 2. Cookie
    token = request.cookies.get('auth_token', '')
    if token:
        return token
    
    # 3. Query Parameter (仅用于 WebSocket 等特殊场景)
    token = request.args.get('token', '')
    if token:
        return token
    
    return ''


def require_auth(f):
    """认证装饰器，保护需要认证的路由"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_auth_enabled():
            return f(*args, **kwargs)
        
        token = get_token_from_request()
        
        if not token:
            return jsonify({
                'success': False,
                'error': '未登录或登录已过期',
                'auth_required': True
            }), 401
        
        if not check_auth(token):
            return jsonify({
                'success': False,
                'error': 'Token 无效或已过期',
                'auth_required': True
            }), 401
        
        # 标记已认证
        g.authenticated = True
        g.token = token
        
        # 解析用户信息
        payload = verify_jwt_token(token)
        if payload:
            g.username = payload.get('username')
        
        return f(*args, **kwargs)
    
    return decorated_function


# ========== 公开路由白名单 ==========

PUBLIC_ROUTES = {
    '/',               # 首页
    '/api/health',     # 健康检查
    '/api/auth/challenge',  # 获取挑战码
    '/api/auth/login',      # 登录接口
    '/api/auth/status',     # 认证状态
    '/static/',        # 静态资源
}


def is_public_route(path: str) -> bool:
    """检查是否为公开路由"""
    for route in PUBLIC_ROUTES:
        if path.startswith(route):
            return True
    return False


def init_auth_middleware(app):
    """初始化认证中间件
    
    Args:
        app: Flask 应用实例
    """
    @app.before_request
    def check_authentication():
        # 静态资源和公开路由跳过
        if is_public_route(request.path):
            return None
        
        # 未启用认证则跳过
        if not is_auth_enabled():
            return None
        
        token = get_token_from_request()
        
        if not token or not check_auth(token):
            # API 请求返回 JSON 错误
            if request.path.startswith('/api/'):
                return jsonify({
                    'success': False,
                    'error': '需要登录',
                    'auth_required': True
                }), 401
            # 页面请求重定向到首页（前端会显示登录）
            from flask import redirect
            return redirect('/?auth_required=1')
        
        g.authenticated = True
        g.token = token
        
        # 解析用户信息
        payload = verify_jwt_token(token)
        if payload:
            g.username = payload.get('username')
        
        return None


# ========== 初始化检查 ==========

def needs_initialization() -> bool:
    """检查是否需要初始化（首次运行且无管理员）
    
    Returns:
        True 表示需要初始化，显示注册界面
    """
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        
        # 如果未启用认证，不需要初始化
        if not auth_cfg.get('enabled', False):
            return False
        
        # 检查是否有用户
        users = auth_cfg.get('users', [])
        return len(users) == 0
        
    except Exception:
        return False


def initialize_admin(username: str, password: str) -> tuple:
    """初始化管理员账户（仅首次运行时可用）
    
    Args:
        username: 管理员用户名
        password: 管理员密码
    
    Returns:
        (success: bool, message: str)
    """
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        
        # 检查是否已启用认证
        if not auth_cfg.get('enabled', False):
            return False, '认证未启用'
        
        # 检查是否已有用户
        users = auth_cfg.get('users', [])
        if len(users) > 0:
            return False, '系统已初始化，无法重复注册'
        
        # 验证用户名
        if not username or len(username) < 3:
            return False, '用户名至少 3 个字符'
        
        if not username.isalnum():
            return False, '用户名只能包含字母和数字'
        
        # 验证密码
        if not password or len(password) < 6:
            return False, '密码至少 6 个字符'
        
        # 创建管理员
        if 'auth' not in cfg:
            cfg['auth'] = {}
        
        cfg['auth']['users'] = [{
            'username': username,
            'password_hash': hash_password(password),
            'role': 'admin',
            'created_at': datetime.now().isoformat()
        }]
        
        # 生成 JWT 密钥
        if not cfg['auth'].get('jwt_secret'):
            cfg['auth']['jwt_secret'] = secrets.token_hex(32)
        
        config.save_config(cfg)
        
        logger.info(f"管理员初始化成功: {username}")
        return True, '管理员账户创建成功'
        
    except Exception as e:
        logger.error(f"初始化管理员失败: {e}")
        return False, str(e)


def ensure_default_user():
    """确保认证配置正确（不再自动创建用户）
    
    保留此函数以兼容现有代码
    """
    # 不再自动创建用户，改为前端引导注册
    pass