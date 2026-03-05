"""Web 路由 - RESTful API"""
from flask import Flask, render_template, jsonify, request
import sys
sys.path.insert(0, '..')
import config
import storage
from clients.ikuai_local import IKuaiLocalClient
from services.monitor import MonitorService
from services.reporter import ReporterService
from services.vendor import VendorLookup

app = Flask(__name__, template_folder='templates', static_folder='static')

# 全局服务实例
_monitor = None
_pusher = None
_vendor = VendorLookup()


def get_monitor():
    global _monitor
    if _monitor is None:
        cfg = config.get_config()
        _monitor = MonitorService(cfg['ikuai'], cfg['monitor'])
    return _monitor


def get_pusher():
    global _pusher
    if _pusher is None:
        cfg = config.get_config()
        _pusher = ReporterService(cfg['pushme'])
    return _pusher


# ========== 页面路由 ==========

@app.route('/')
def index():
    return render_template('index.html')


# ========== API 路由 ==========

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'version': '1.0.0'})


@app.route('/api/devices')
def get_devices():
    """获取在线设备列表"""
    try:
        status = get_monitor().get_current_status()
        devices = status.get('devices', [])
        
        # 添加厂商信息
        for d in devices:
            d['vendor'] = _vendor.lookup(d['mac'])
        
        return jsonify({'success': True, 'devices': devices, 'count': len(devices)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/devices/all')
def get_all_devices():
    """获取所有设备（含离线）"""
    try:
        devices = storage.get_all_devices()
        for d in devices:
            d['vendor'] = _vendor.lookup(d['mac'])
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device/<mac>/alias', methods=['POST'])
def set_device_alias(mac):
    """设置设备备注名"""
    try:
        data = request.get_json()
        alias = data.get('alias', '')
        is_trusted = data.get('is_trusted')
        
        storage.update_device_alias(mac, alias, is_trusted)
        get_monitor().set_device_alias(mac, alias)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device/<mac>/kick', methods=['POST'])
def kick_device(mac):
    """踢设备下线"""
    try:
        result = get_monitor().kick_device(mac)
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/device/<mac>/events')
def get_device_events(mac):
    """获取设备事件历史"""
    try:
        events = storage.get_device_events(mac)
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alerts')
def get_alerts():
    """获取告警列表"""
    try:
        alerts = storage.get_unresolved_alerts()
        return jsonify({'success': True, 'alerts': alerts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alert/<int:alert_id>/resolve', methods=['POST'])
def resolve_alert(alert_id):
    """处理告警"""
    try:
        storage.resolve_alert(alert_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats/week')
def get_week_stats():
    """获取最近7天统计"""
    from datetime import datetime, timedelta
    
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d')
        
        stats = storage.get_stats_range(start_date, end_date)
        
        dates = []
        upload = []
        download = []
        device_counts = []
        
        for i in range(7):
            d = (datetime.now() - timedelta(days=6-i)).strftime('%Y-%m-%d')
            dates.append(d[5:])  # MM-DD
            
            day_stat = next((s for s in stats if s['date'] == d), None)
            upload.append(day_stat['total_upload'] if day_stat else 0)
            download.append(day_stat['total_download'] if day_stat else 0)
            device_counts.append(day_stat['device_count'] if day_stat else 0)
        
        return jsonify({
            'success': True,
            'dates': dates,
            'upload': upload,
            'download': download,
            'device_counts': device_counts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats/today')
def get_today_stats():
    """获取今日统计"""
    from datetime import datetime
    
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        stats = storage.get_daily_stats(today)
        
        if not stats:
            # 实时计算
            status = get_monitor().get_current_status()
            stats = {
                'total_upload': sum(d.get('total_upload', 0) for d in status['devices']),
                'total_download': sum(d.get('total_download', 0) for d in status['devices']),
                'device_count': status['online_count']
            }
        
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 配置管理 API ==========

@app.route('/api/config')
def get_config():
    """获取配置"""
    try:
        cfg = config.get_config()
        
        # 敏感信息脱敏
        result = {
            'ikuai': {
                'local_url': cfg['ikuai'].get('local_url', ''),
                'username': cfg['ikuai'].get('username', ''),
                'password': ''  # 不返回密码
            },
            'pushme': {
                'push_key': config.mask_sensitive(cfg['pushme'].get('push_key', '')),
                'enabled': cfg['pushme'].get('enabled', True)
            },
            'monitor': cfg.get('monitor', {}),
            'web': cfg.get('web', {})
        }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def save_config():
    """保存配置"""
    try:
        data = request.get_json()
        
        # 更新配置
        cfg = config.get_config()
        
        if 'ikuai' in data:
            cfg['ikuai'].update(data['ikuai'])
        if 'pushme' in data:
            # 如果密码/push_key是****则保持原值
            if data['pushme'].get('push_key') == '****':
                data['pushme']['push_key'] = cfg['pushme'].get('push_key', '')
            if data['pushme'].get('push_key'):  # 只更新非空值
                cfg['pushme'].update(data['pushme'])
        if 'monitor' in data:
            cfg['monitor'].update(data['monitor'])
        
        config.save_config(cfg)
        
        # 重新初始化服务
        global _monitor, _pusher
        _monitor = None
        _pusher = None
        
        return jsonify({'success': True, 'message': '配置已保存'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/test/ikuai', methods=['POST'])
def test_ikuai():
    """测试爱快连接"""
    try:
        data = request.get_json()
        client = IKuaiLocalClient(
            base_url=data.get('local_url', ''),
            username=data.get('username', ''),
            password=data.get('password', '')
        )
        
        if client.login():
            info = client.get_router_info()
            return jsonify({
                'success': True,
                'message': f"连接成功: {info.get('name', 'iKuai Router')}"
            })
        else:
            return jsonify({'success': False, 'message': '登录失败，请检查用户名密码'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/test/pushme', methods=['POST'])
def test_pushme():
    """测试 PushMe 推送"""
    try:
        data = request.get_json()
        from services.pusher import PushMeClient
        
        client = PushMeClient(push_key=data.get('push_key', ''))
        success, msg = client.send(
            title='[s][#iHomeGuard!✅]连接测试',
            content='## ✅ 测试成功\n\niHomeGuard 推送功能正常',
            msg_type='markdown'
        )
        
        return jsonify({'success': success, 'message': '推送成功' if success else msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ========== 初始化 ==========

def init_app():
    """初始化应用"""
    storage.init_db()
    
    # 检查配置
    is_valid, missing = config.validate_config()
    if not is_valid:
        print(f"[警告] 配置不完整，缺少: {', '.join(missing)}")
        print("[提示] 请在设置页面完成配置")


if __name__ == '__main__':
    init_app()
    cfg = config.get_config()
    app.run(host=cfg['web']['host'], port=cfg['web']['port'], debug=False)