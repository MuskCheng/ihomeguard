"""iHomeGuard 主入口"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
import config
import storage
from scheduler import start_scheduler
from web.routes import app, init_app
from clients.ikuai_local import IKuaiLocalClient
from services.pusher import MultiPushClient


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
            session_timeout=monitor_cfg.get('session_timeout', 120)
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
        return False, f"连接异常: {str(e)}", ""


def send_startup_notification(cfg: dict, ikuai_connected: bool, ikuai_message: str):
    """发送启动通知"""
    pushme_cfg = cfg.get('pushme', {})
    
    # 检查是否有推送配置
    has_push_config = (
        pushme_cfg.get('push_key') or 
        pushme_cfg.get('wecom_webhook') or 
        pushme_cfg.get('dingtalk_webhook')
    )
    
    if not has_push_config:
        print("[启动] 未配置推送渠道，跳过启动通知")
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
        print(f"[启动] 启动通知已发送")
    else:
        print(f"[启动] 启动通知发送失败: {msg}")


def main():
    """主函数"""
    print("=" * 50)
    print("🏠 iHomeGuard - 爱快家庭网络卫士")
    print("=" * 50)
    
    # 初始化数据库
    print("[启动] 初始化数据库...")
    storage.init_db()
    
    # 加载配置
    cfg = config.get_config()
    
    # 重置爱快客户端锁定状态（确保启动时是干净状态）
    IKuaiLocalClient.reset_lock_state()
    
    # 检查爱快连接（如果已配置密码则自动登录）
    print("[启动] 检查爱快连接...")
    ikuai_connected, ikuai_message, router_name = check_ikuai_connection(cfg)
    if ikuai_connected:
        print(f"[启动] 爱快连接成功 - {ikuai_message}")
    else:
        print(f"[启动] 爱快未连接 - {ikuai_message}")
    
    # 发送启动通知
    send_startup_notification(cfg, ikuai_connected, ikuai_message)
    
    # 启动定时任务
    print("[启动] 启动定时任务...")
    start_scheduler()
    
    # 启动 Web 服务
    host = cfg['web'].get('host', '0.0.0.0')
    port = cfg['web'].get('port', 8680)
    
    print(f"[启动] Web 服务: http://{host}:{port}")
    print("-" * 50)
    
    init_app()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()