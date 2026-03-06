"""Web 路由 - RESTful API"""
from flask import Flask, render_template, jsonify, request
import sys
sys.path.insert(0, '..')
import config
import storage
from clients.ikuai_local import IKuaiLocalClient
from services.monitor import MonitorService
from services.reporter import ReporterService
from services.vendor import get_vendor_cached

app = Flask(__name__, template_folder='templates', static_folder='static')

# 修改 Jinja2 定界符，避免与 Vue.js 冲突
app.jinja_env.variable_start_string = '{['
app.jinja_env.variable_end_string = ']}'

# 全局服务实例
_monitor = None
_pusher = None


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
        monitor = get_monitor()
        status = monitor.get_current_status()
        devices = status.get('devices', [])
        
        # 添加厂商信息
        for d in devices:
            d['vendor'] = get_vendor_cached(d['mac'])
            # 格式化在线时长
            minutes = d.get('today_online_minutes', 0)
            hours = minutes // 60
            mins = minutes % 60
            d['today_online_formatted'] = f"{hours}h{mins}m" if hours > 0 else f"{mins}m"
        
        return jsonify({'success': True, 'devices': devices, 'count': len(devices)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/devices/all')
def get_all_devices():
    """获取所有设备（含离线）"""
    try:
        devices = storage.get_all_devices()
        for d in devices:
            d['vendor'] = get_vendor_cached(d['mac'])
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


@app.route('/api/stats/prediction')
def get_traffic_prediction():
    """流量趋势预测"""
    from datetime import datetime, timedelta
    
    try:
        # 获取本月已过天数
        now = datetime.now()
        day_of_month = now.day
        days_in_month = 31  # 简化处理
        
        # 获取本月统计数据
        start_date = now.replace(day=1).strftime('%Y-%m-%d')
        stats = storage.get_stats_range(start_date, now.strftime('%Y-%m-%d'))
        
        if not stats:
            # 使用实时数据
            status = get_monitor().get_current_status()
            current_upload = sum(d.get('total_upload', 0) for d in status['devices'])
            current_download = sum(d.get('total_download', 0) for d in status['devices'])
        else:
            current_upload = sum(s.get('total_upload', 0) for s in stats)
            current_download = sum(s.get('total_download', 0) for s in stats)
        
        # 计算日均流量
        daily_upload = current_upload / max(day_of_month, 1)
        daily_download = current_download / max(day_of_month, 1)
        daily_total = daily_upload + daily_download
        
        # 预测本月总量
        remaining_days = days_in_month - day_of_month
        predicted_upload = current_upload + (daily_upload * remaining_days)
        predicted_download = current_download + (daily_download * remaining_days)
        predicted_total = predicted_upload + predicted_download
        
        return jsonify({
            'success': True,
            'prediction': {
                'upload': predicted_upload,
                'download': predicted_download,
                'total': predicted_total,
                'daily_avg': daily_total
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 流量历史 API ==========

@app.route('/api/traffic/history')
def get_traffic_history():
    """获取流量历史数据"""
    try:
        # 支持的时间范围: 5m, 1h, 6h, 12h, 1d, 3d, 7d
        range_param = request.args.get('range', '5m')
        
        # 转换为小时数（支持分钟）
        hours_map = {
            '5m': 5/60,   # 5分钟
            '1h': 1,
            '6h': 6,
            '12h': 12,
            '1d': 24,
            '3d': 72,
            '7d': 168
        }
        hours = hours_map.get(range_param, 5/60)
        
        history = storage.get_traffic_history(hours)
        
        # 格式化返回数据
        times = []
        upload_speeds = []
        download_speeds = []
        device_counts = []
        
        for record in history:
            times.append(record['time'])
            upload_speeds.append(record['upload_speed'])
            download_speeds.append(record['download_speed'])
            device_counts.append(record['device_count'])
        
        return jsonify({
            'success': True,
            'range': range_param,
            'times': times,
            'upload_speeds': upload_speeds,
            'download_speeds': download_speeds,
            'device_counts': device_counts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 数据库维护 API ==========

@app.route('/api/database/stats')
def get_database_stats():
    """获取数据库统计信息"""
    try:
        stats = storage.get_database_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/database/cleanup', methods=['POST'])
def manual_cleanup():
    """手动触发数据清理"""
    try:
        data = request.get_json() or {}
        retention = data.get('retention', {})
        
        results = storage.cleanup_all(retention)
        total = sum(results.values())
        
        # 执行 VACUUM
        storage.vacuum_database()
        
        return jsonify({
            'success': True,
            'deleted': results,
            'total_deleted': total,
            'message': f'清理完成，共删除 {total} 条记录'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/database/vacuum', methods=['POST'])
def manual_vacuum():
    """手动触发数据库 VACUUM"""
    try:
        storage.vacuum_database()
        return jsonify({'success': True, 'message': 'VACUUM 完成'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 配置管理 API ==========

@app.route('/api/config')
def get_config():
    """获取配置"""
    try:
        cfg = config.get_config()
        
        # 密码脱敏，push_key 明文显示
        result = {
            'ikuai': {
                'local_url': cfg['ikuai'].get('local_url', ''),
                'username': cfg['ikuai'].get('username', ''),
                'password': '****' if cfg['ikuai'].get('password') else '',
                'connection_validated': cfg['ikuai'].get('connection_validated', False)
            },
            'pushme': {
                'push_key': cfg['pushme'].get('push_key', ''),  # 明文显示
                'wecom_webhook': cfg['pushme'].get('wecom_webhook', ''),
                'dingtalk_webhook': cfg['pushme'].get('dingtalk_webhook', ''),
                'dingtalk_secret': cfg['pushme'].get('dingtalk_secret', ''),
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
            # 如果密码为空或脱敏值，保持原值
            ikuai_data = data['ikuai']
            pwd = ikuai_data.get('password', '')
            if not pwd or pwd == '****' or pwd.endswith('****'):
                ikuai_data['password'] = cfg['ikuai'].get('password', '')
            cfg['ikuai'].update(ikuai_data)
        if 'pushme' in data:
            # push_key 直接保存，其他webhook检测空值
            pushme_data = data['pushme']
            cfg['pushme'].update(pushme_data)
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
        print(f"[调试] 测试爱快连接: {data}")
        
        # 检查密码是否存在
        password = data.get('password', '')
        cfg = config.get_config()
        
        # 如果密码是****，使用已保存的密码
        if password == '****' or not password:
            password = cfg['ikuai'].get('password', '')
            if not password:
                return jsonify({'success': False, 'message': '请输入密码'})
        
        client = IKuaiLocalClient(
            base_url=data.get('local_url', ''),
            username=data.get('username', ''),
            password=password,
            session_timeout=cfg.get('monitor', {}).get('session_timeout', 120)
        )
        
        if client.login():
            info = client.get_router_info()
            
            # 测试成功后自动保存配置
            cfg['ikuai']['local_url'] = data.get('local_url', '')
            cfg['ikuai']['username'] = data.get('username', '')
            if data.get('password') and data.get('password') != '****':
                cfg['ikuai']['password'] = data.get('password')
            cfg['ikuai']['connection_validated'] = True
            config.save_config(cfg)
            print(f"[调试] 配置已保存")
            
            # 重新初始化服务
            global _monitor
            _monitor = None
            
            router_name = info.get('name', 'iKuai Router') if info else 'iKuai Router'
            return jsonify({
                'success': True,
                'message': f"连接成功！路由器: {router_name}"
            })
        else:
            return jsonify({'success': False, 'message': '登录失败，请检查用户名密码'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/test/pushme', methods=['POST'])
def test_pushme():
    """测试 PushMe 推送"""
    try:
        data = request.get_json()
        from services.pusher import PushMeClient
        
        push_key = data.get('push_key', '')
        client = PushMeClient(push_key=push_key)
        success, msg = client.send(
            title='[s][#iHomeGuard!✅]连接测试',
            content='## ✅ 测试成功\n\niHomeGuard 推送功能正常',
            msg_type='markdown'
        )
        
        if success:
            cfg = config.get_config()
            if push_key:
                cfg['pushme']['push_key'] = push_key
            config.save_config(cfg)
        
        return jsonify({'success': success, 'message': '推送成功，配置已保存' if success else msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/test/push', methods=['POST'])
def test_push():
    """测试推送（支持多渠道）"""
    try:
        data = request.get_json()
        channel = data.get('channel', 'pushme')
        
        # 先保存推送配置
        cfg = config.get_config()
        if 'push_key' in data and data['push_key']:
            cfg['pushme']['push_key'] = data['push_key']
        if 'wecom_webhook' in data and data['wecom_webhook']:
            cfg['pushme']['wecom_webhook'] = data['wecom_webhook']
        if 'dingtalk_webhook' in data and data['dingtalk_webhook']:
            cfg['pushme']['dingtalk_webhook'] = data['dingtalk_webhook']
        if 'dingtalk_secret' in data and data['dingtalk_secret']:
            cfg['pushme']['dingtalk_secret'] = data['dingtalk_secret']
        config.save_config(cfg)
        print(f"[推送] 配置已保存，测试渠道: {channel}")
        
        from services.pusher import MultiPushClient
        
        client = MultiPushClient(config.get_config()['pushme'])
        success, msg = client.test_push(channel)
        
        return jsonify({'success': success, 'message': msg})
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