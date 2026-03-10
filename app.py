"""iHomeGuard 主入口"""
import os
import sys
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
import config
import storage
from scheduler import start_scheduler
from web.routes import app, init_app
from clients.ikuai_local import IKuaiLocalClient
from services.pusher import MultiPushClient
from logger import get_logger

logger = get_logger('app')

# 启动通知防重复标记文件
STARTUP_MARKER_FILE = os.path.join(os.path.dirname(__file__), 'data', '.startup_sent')


def is_startup_notification_sent_recently() -> bool:
    """检查是否最近已发送过启动通知（60秒内）"""
    try:
        if os.path.exists(STARTUP_MARKER_FILE):
            with open(STARTUP_MARKER_FILE, 'r') as f:
                last_time = float(f.read().strip())
                # 60秒内不重复发送
                if time.time() - last_time < 60:
                    return True
    except Exception:
        pass
    return False


def mark_startup_notification_sent():
    """标记启动通知已发送"""
    try:
        os.makedirs(os.path.dirname(STARTUP_MARKER_FILE), exist_ok=True)
        with open(STARTUP_MARKER_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        logger.warning(f"无法写入启动标记文件: {e}")


def check_ikuai_connection(cfg: dict) -> tuple:
    """检查爱快连接状态
    
    Returns:
        (connected: bool, message: str, router_name: str)
    """
    ikuai_cfg = cfg.get('ikuai', {})
    monitor_cfg = cfg.get('monitor', {})
    
    local_url = ikuai_cfg.get('local_url', '')
    username = ikuai_cfg.get('username', '')
    password = ikuai_cfg.get('password', '')
    
    if not password:
        return False, "未配置密码，请前往设置页面完成配置", ""
    
    try:
        client = IKuaiLocalClient(
            base_url=local_url,
            username=username,
            password=password,
            session_timeout=cfg['ikuai'].get('session_timeout', 120)
        )
        
        if client.login():
            info = client.get_router_info()
            router_name = info.get('name', 'iKuai Router') if info else 'iKuai Router'
            # 标记连接已验证
            cfg['ikuai']['connection_validated'] = True
            config.save_config(cfg)
            return True, f"路由器: {router_name}", router_name
        else:
            return False, "登录失败，请检查用户名和密码", ""
    except Exception as e:
        logger.error(f"爱快连接异常: {e}")
        return False, f"连接异常: {str(e)}", ""


def send_startup_notification(cfg: dict, ikuai_connected: bool, ikuai_message: str):
    """发送启动通知"""
    # 防重复检查：60秒内已发送过则跳过
    if is_startup_notification_sent_recently():
        logger.info("启动通知已发送过，跳过重复发送")
        return
    
    pushme_cfg = cfg.get('pushme', {})
    monitor_cfg = cfg.get('monitor', {})
    
    # 检查是否启用启动通知（默认启用）
    if not monitor_cfg.get('alert_startup', True):
        logger.debug("启动通知已禁用，跳过")
        return
    
    # 检查推送是否启用
    if not pushme_cfg.get('enabled', True):
        logger.debug("推送已禁用，跳过启动通知")
        return
    
    # 检查是否有推送配置
    has_push_config = (
        pushme_cfg.get('push_key') or 
        pushme_cfg.get('wecom_webhook') or 
        pushme_cfg.get('dingtalk_webhook')
    )
    
    if not has_push_config:
        logger.debug("未配置推送渠道，跳过启动通知")
        return
    
    pusher = MultiPushClient(pushme_cfg)
    
    # 读取版本
    version = "v1.0.0"
    version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            version = f.read().strip() or version
    
    status_info = {
        'ikuai_connected': ikuai_connected,
        'ikuai_message': ikuai_message,
        'push_enabled': pushme_cfg.get('enabled', True),
        'config_complete': ikuai_connected,  # 简化判断
        'version': version
    }
    
    success, msg = pusher.send_startup_notification(status_info)
    if success:
        # 标记已发送
        mark_startup_notification_sent()
        logger.info("启动通知已发送")
    else:
        logger.warning(f"启动通知发送失败: {msg}")


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("iHomeGuard - 爱快家庭网络卫士")
    logger.info("=" * 50)
    
    # 初始化数据库
    logger.info("初始化数据库...")
    storage.init_db()
    
    # 加载配置（首次运行会自动创建默认配置文件）
    cfg = config.get_config()
    
    # 确保配置文件存在（首次部署时创建）
    if not os.path.exists(config.CONFIG_PATH):
        logger.info("创建默认配置文件...")
        config.save_config(cfg)
    
    # 重置爱快客户端锁定状态（确保启动时是干净状态）
    IKuaiLocalClient.reset_lock_state()
    
    # 检查爱快连接（如果已配置密码则自动登录）
    logger.info("检查爱快连接...")
    ikuai_connected, ikuai_message, router_name = check_ikuai_connection(cfg)
    if ikuai_connected:
        logger.info(f"爱快连接成功 - {ikuai_message}")
    else:
        logger.info(f"爱快未连接 - {ikuai_message}")
    
    # 发送启动通知
    send_startup_notification(cfg, ikuai_connected, ikuai_message)
    
    # 启动定时任务
    logger.info("启动定时任务...")
    start_scheduler()
    
    # 启动 Web 服务
    host = cfg['web'].get('host', '0.0.0.0')
    port = cfg['web'].get('port', 8680)
    
    logger.info(f"Web 服务: http://{host}:{port}")
    logger.info("-" * 50)
    
    init_app()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
