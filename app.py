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


def main():
    """主函数"""
    print("=" * 50)
    print("🏠 iHomeGuard - 爱快家庭网络卫士")
    print("=" * 50)
    
    # 初始化数据库
    print("[启动] 初始化数据库...")
    storage.init_db()
    
    # 检查配置
    is_valid, missing = config.validate_config()
    if not is_valid:
        print(f"[警告] 配置不完整，缺少: {', '.join(missing)}")
        print("[提示] 请访问设置页面完成配置: http://localhost:8680 (设置)")
    else:
        print("[启动] 配置检查通过")
    
    # 启动定时任务
    print("[启动] 启动定时任务...")
    start_scheduler()
    
    # 启动 Web 服务
    cfg = config.get_config()
    host = cfg['web'].get('host', '0.0.0.0')
    port = cfg['web'].get('port', 8680)
    
    print(f"[启动] Web 服务: http://{host}:{port}")
    print("-" * 50)
    
    init_app()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()