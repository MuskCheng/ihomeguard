"""PushMe 推送客户端"""
import requests
import hmac
import hashlib
import base64
import time
from datetime import datetime


class PushMeClient:
    """PushMe 推送客户端"""
    
    def __init__(self, push_key: str, api_url: str = "https://push.i-i.me"):
        self.push_key = push_key
        self.api_url = api_url
    
    def send(self, title: str, content: str, msg_type: str = "markdown") -> tuple:
        """发送推送消息
        
        Returns:
            (success: bool, message: str)
        """
        if not self.push_key:
            return False, "push_key 未配置"
        
        try:
            resp = requests.post(
                self.api_url,
                data={
                    "push_key": self.push_key,
                    "title": title,
                    "content": content,
                    "type": msg_type
                },
                timeout=10
            )
            if resp.text == "success":
                return True, "success"
            else:
                return False, resp.text
        except Exception as e:
            print(f"[PushMe] 发送失败: {e}")
            return False, str(e)


class WecomClient:
    """企业微信机器人推送"""
    
    def __init__(self, webhook: str):
        self.webhook = webhook
    
    def send(self, title: str, content: str, msg_type: str = "markdown") -> tuple:
        if not self.webhook:
            return False, "企业微信 webhook 未配置"
        
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title}\n\n{content}"
                }
            }
            resp = requests.post(self.webhook, json=data, timeout=10)
            result = resp.json()
            if result.get('errcode') == 0:
                return True, "success"
            return False, result.get('errmsg', '未知错误')
        except Exception as e:
            return False, str(e)


class DingTalkClient:
    """钉钉机器人推送"""
    
    def __init__(self, webhook: str, secret: str = ""):
        self.webhook = webhook
        self.secret = secret
    
    def _sign(self) -> tuple:
        """生成签名"""
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = base64.b64encode(hmac_code).decode('utf-8')
        return timestamp, sign
    
    def send(self, title: str, content: str, msg_type: str = "markdown") -> tuple:
        if not self.webhook:
            return False, "钉钉 webhook 未配置"
        
        try:
            url = self.webhook
            if self.secret:
                timestamp, sign = self._sign()
                url = f"{self.webhook}&timestamp={timestamp}&sign={sign}"
            
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"## {title}\n\n{content}"
                }
            }
            resp = requests.post(url, json=data, timeout=10)
            result = resp.json()
            if result.get('errcode') == 0:
                return True, "success"
            return False, result.get('errmsg', '未知错误')
        except Exception as e:
            return False, str(e)


class MultiPushClient:
    """多渠道推送客户端"""
    
    def __init__(self, pushme_config: dict):
        self.pushme = PushMeClient(
            push_key=pushme_config.get('push_key', ''),
            api_url=pushme_config.get('api_url', 'https://push.i-i.me')
        )
        self.wecom = WecomClient(webhook=pushme_config.get('wecom_webhook', ''))
        self.dingtalk = DingTalkClient(
            webhook=pushme_config.get('dingtalk_webhook', ''),
            secret=pushme_config.get('dingtalk_secret', '')
        )
        self.enabled = pushme_config.get('enabled', True)
    
    def send(self, title: str, content: str, msg_type: str = "markdown") -> tuple:
        """通过所有配置的渠道发送"""
        if not self.enabled:
            return False, "推送已禁用"
        
        results = []
        
        # PushMe
        if self.pushme.push_key:
            success, msg = self.pushme.send(title, content, msg_type)
            results.append(('PushMe', success, msg))
        
        # 企业微信
        if self.wecom.webhook:
            success, msg = self.wecom.send(title, content, msg_type)
            results.append(('企业微信', success, msg))
        
        # 钉钉
        if self.dingtalk.webhook:
            success, msg = self.dingtalk.send(title, content, msg_type)
            results.append(('钉钉', success, msg))
        
        if not results:
            return False, "未配置任何推送渠道"
        
        # 只要有一个成功就返回成功
        for name, success, msg in results:
            if success:
                return True, f"{name} 推送成功"
        
        return False, '; '.join([f"{n}: {m}" for n, s, m in results if not s])
    
    def test_push(self, channel: str) -> tuple:
        """测试指定渠道"""
        title = '[s][#iHomeGuard!✅]连接测试'
        content = '## ✅ 测试成功\n\niHomeGuard 推送功能正常'
        
        if channel == 'pushme':
            return self.pushme.send(title, content)
        elif channel == 'wecom':
            return self.wecom.send(title, content)
        elif channel == 'dingtalk':
            return self.dingtalk.send(title, content)
        else:
            return self.send(title, content)
    
    def send_daily_report(self, report_data: dict) -> tuple:
        """发送日报
        
        Returns:
            (success: bool, message: str)
        """
        date = report_data['date']
        
        title = f"[i][#iHomeGuard!📊] 网络日报 - {date}"
        
        # 流量统计
        upload_gb = report_data['total_upload'] / (1024 ** 3)
        download_gb = report_data['total_download'] / (1024 ** 3)
        total_gb = upload_gb + download_gb
        
        content = f"""## 📊 家庭网络日报 - {date}

### 📈 流量统计
| 指标 | 数值 |
|------|------|
| ⬆️ 今日上传 | **{upload_gb:.2f} GB** |
| ⬇️ 今日下载 | **{download_gb:.2f} GB** |
| 📡 总流量 | **{total_gb:.2f} GB** |

### 📱 设备概览
| 指标 | 数值 |
|------|------|
| 当前在线 | **{report_data['device_count']} 台** |
| 日峰值 | **{report_data['peak_device_count']} 台** |
| 最大连接数 | **{report_data['max_connections']}** |

"""
        
        # 设备详情
        if report_data.get('devices'):
            content += "### 🔌 设备流量排行 TOP5\n"
            content += "| 设备 | 上传 | 下载 | 总计 |\n"
            content += "|------|------|------|------|\n"
            
            sorted_devices = sorted(
                report_data['devices'],
                key=lambda x: (x.get('total_upload', 0) + x.get('total_download', 0)),
                reverse=True
            )[:5]
            
            for dev in sorted_devices:
                name = dev.get('alias') or dev.get('hostname') or dev['mac'][:8]
                up = dev.get('total_upload', 0) / (1024 ** 2)
                down = dev.get('total_download', 0) / (1024 ** 2)
                total = up + down
                content += f"| {name} | {up:.0f} MB | {down:.0f} MB | {total:.0f} MB |\n"
        
        # 上下线事件
        if report_data.get('events'):
            online_events = [e for e in report_data['events'] if e['event_type'] == 'online']
            offline_events = [e for e in report_data['events'] if e['event_type'] == 'offline']
            content += f"\n### 🔄 设备活动\n"
            content += f"- 新上线设备: **{len(online_events)} 台**\n"
            content += f"- 离线设备: **{len(offline_events)} 台**\n"
        
        # 告警信息
        if report_data.get('alerts'):
            content += "\n### ⚠️ 异常提醒\n"
            for alert in report_data['alerts'][:5]:
                content += f"- {alert['message']}\n"
        
        content += "\n---\n*iHomeGuard 家庭网络监控*"
        
        return self.send(title, content, "markdown")
    
    def send_alert(self, alert_type: str, message: str) -> tuple:
        """发送告警
        
        Returns:
            (success: bool, message: str)
        """
        from datetime import datetime
        
        # 根据告警类型设置图标
        icons = {
            'new_device': '🔐',
            'high_traffic': '📊',
            'long_online': '⏰',
            'high_connections': '🔗',
            'device_offline': '📴'
        }
        icon = icons.get(alert_type, '⚠️')
        
        title = f"[w][#iHomeGuard!{icon}] 网络告警 - {alert_type}"
        content = f"""## {icon} 网络告警

### 告警类型
**{alert_type}**

### 详情
{message}

### 时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*iHomeGuard 家庭网络监控*"""
        return self.send(title, content, "markdown")
