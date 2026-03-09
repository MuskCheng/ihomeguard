"""认证中间件模块"""
import os
import secrets
import hashlib
from functools import wraps
from flask import request, jsonify, g


def generate_token() -> str:
    """生成安全的随机 Token"""
    return secrets.token_hex(16)  # 32 字符


def hash_token(token: str) -> str:
    """对 Token 进行哈希存储（可选，增加安全性）"""
    return hashlib.sha256(token.encode()).hexdigest()


def is_auth_enabled() -> bool:
    """检查是否启用认证"""
    # 环境变量优先
    env_token = os.environ.get('AUTH_TOKEN')
    if env_token is not None:
        return True
    
    # 检查配置
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        return auth_cfg.get('enabled', False)
    except Exception:
        return False


def get_valid_token() -> str:
    """获取有效的 Token（从环境变量或配置）"""
    # 环境变量优先
    env_token = os.environ.get('AUTH_TOKEN')
    if env_token:
        return env_token
    
    # 从配置读取
    try:
        import config
        cfg = config.get_config()
        auth_cfg = cfg.get('auth', {})
        return auth_cfg.get('token', '')
    except Exception:
        return ''


def check_auth(token: str) -> bool:
    """验证 Token 是否有效
    
    Args:
        token: 客户端提供的 token
    
    Returns:
        是否验证通过
    """
    if not is_auth_enabled():
        return True  # 未启用认证，直接通过
    
    valid_token = get_valid_token()
    if not valid_token:
        return True  # 没有配置 token，直接通过
    
    # 时序安全比较，防止时序攻击
    return secrets.compare_digest(token, valid_token)


def get_token_from_request() -> str:
    """从请求中提取 Token
    
    支持三种方式：
    1. Authorization Header: Bearer <token>
    2. Query Parameter: ?token=<token>
    3. Cookie: auth_token=<token>
    """
    # 1. Authorization Header
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    # 2. Query Parameter
    token = request.args.get('token', '')
    if token:
        return token
    
    # 3. Cookie
    token = request.cookies.get('auth_token', '')
    if token:
        return token
    
    # 4. JSON Body（仅对 POST/PUT 请求）
    if request.is_json:
        try:
            data = request.get_json(silent=True)
            if data and 'token' in data:
                return data['token']
        except Exception:
            pass
    
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
                'error': '缺少认证 Token',
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
        return f(*args, **kwargs)
    
    return decorated_function


# 不需要认证的路由白名单
PUBLIC_ROUTES = {
    '/',           # 首页
    '/api/health', # 健康检查
    '/api/auth/login',  # 登录接口
    '/api/auth/status', # 认证状态
    '/static/',    # 静态资源
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
                    'error': '需要认证',
                    'auth_required': True
                }), 401
            # 页面请求重定向到首页（前端会显示登录）
            from flask import redirect
            return redirect('/?auth_required=1')
        
        g.authenticated = True
        return None
