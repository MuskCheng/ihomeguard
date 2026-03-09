"""多渠道推送客户端模块

支持渠道：PushMe、企业微信、钉钉、Telegram、飞书、Bark、Server酱、PushPlus、SMTP、自定义Webhook

PushMe 消息类型：
- info (i): 信息 - 白色/默认
- success (s): 成功 - 绿色
- warning (w): 警告 - 黄色
- failure (f): 失败 - 红色
"""
import requests
import hmac
import hashlib
import base64
import time
import smtplib
import re
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, Optional, List
from datetime import datetime


# 消息类型枚举
class MsgType:
    """消息类型"""
    INFO = 'info'       # 信息 - 白色
    SUCCESS = 'success' # 成功 - 绿色
    WARNING = 'warning' # 警告 - 黄色
    FAILURE = 'failure' # 失败 - 红色


# 消息类型对应的图标
MSG_TYPE_ICONS = {
    MsgType.INFO: 'ℹ️',
    MsgType.SUCCESS: '✅',
    MsgType.WARNING: '⚠️',
    MsgType.FAILURE: '❌'
}


class BasePushClient(ABC):
    """推送客户端基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        """发送推送消息
        
        Args:
            title: 消息标题
            content: 消息内容
            msg_type: 消息类型
        
        Returns:
            (success: bool, message: str)
        """
        pass
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.config)


class PushMeClient(BasePushClient):
    """PushMe 推送客户端
    
    支持功能：
    - 消息主题（颜色）：[i]信息 [s]成功 [w]警告 [f]失败
    - 消息分组：[#分组名!头像]
    - 消息通道：[~通道名]
    """
    
    # 消息主题标识
    MSG_THEMES = {
        MsgType.INFO: '[i]',      # 白色
        MsgType.SUCCESS: '[s]',   # 绿色
        MsgType.WARNING: '[w]',   # 黄色
        MsgType.FAILURE: '[f]'    # 红色
    }
    
    def is_configured(self) -> bool:
        return bool(self.config.get('push_key'))
    
    def _format_title(self, title: str, msg_type: str) -> str:
        """格式化标题，添加主题和分组
        
        格式：[主题]标题[#分组!头像]
        """
        # 获取主题标识
        theme = self.MSG_THEMES.get(msg_type, '[i]')
        
        # 获取分组配置
        group = self.config.get('group', 'iHomeGuard')
        icon = self.config.get('icon', '🏠')
        
        # 构建标题：[s]标题[#iHomeGuard!🏠]
        if group:
            # 如果标题中已有分组标记，不再添加
            if '[#' not in title:
                title = f"{theme}{title}[#{group}!{icon}]"
            else:
                title = f"{theme}{title}"
        else:
            title = f"{theme}{title}"
        
        return title
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        push_key = self.config.get('push_key', '')
        if not push_key:
            return False, "push_key 未配置"
        
        api_url = self.config.get('api_url', 'https://push.i-i.me')
        
        # 格式化标题
        formatted_title = self._format_title(title, msg_type)
        
        try:
            resp = requests.post(
                api_url,
                data={
                    "push_key": push_key,
                    "title": formatted_title,
                    "content": content,
                    "type": "markdown"
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                if resp.text == "success" or resp.text.strip() == "success":
                    return True, "推送成功"
                else:
                    return False, resp.text.strip()
            else:
                return False, f"HTTP错误: {resp.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class WecomClient(BasePushClient):
    """企业微信机器人推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('webhook'))
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        webhook = self.config.get('webhook', '')
        if not webhook:
            return False, "企业微信 webhook 未配置"
        
        # 添加消息类型图标
        icon = MSG_TYPE_ICONS.get(msg_type, '')
        title_with_icon = f"{icon} {title}" if icon else title
        
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title_with_icon}\n\n{content}"
                }
            }
            resp = requests.post(webhook, json=data, timeout=30)
            result = resp.json()
            if result.get('errcode') == 0:
                return True, "推送成功"
            return False, result.get('errmsg', '未知错误')
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class DingTalkClient(BasePushClient):
    """钉钉机器人推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('webhook'))
    
    def _sign(self, secret: str) -> Tuple[str, str]:
        """生成签名"""
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = base64.b64encode(hmac_code).decode('utf-8')
        return timestamp, sign
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        webhook = self.config.get('webhook', '')
        if not webhook:
            return False, "钉钉 webhook 未配置"
        
        # 添加消息类型图标
        icon = MSG_TYPE_ICONS.get(msg_type, '')
        title_with_icon = f"{icon} {title}" if icon else title
        
        try:
            url = webhook
            secret = self.config.get('secret', '')
            if secret:
                timestamp, sign = self._sign(secret)
                url = f"{webhook}&timestamp={timestamp}&sign={sign}"
            
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"## {title_with_icon}\n\n{content}"
                }
            }
            resp = requests.post(url, json=data, timeout=30)
            result = resp.json()
            if result.get('errcode') == 0:
                return True, "推送成功"
            return False, result.get('errmsg', '未知错误')
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class TelegramClient(BasePushClient):
    """Telegram Bot 推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('bot_token')) and bool(self.config.get('user_id'))
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        bot_token = self.config.get('bot_token', '')
        user_id = self.config.get('user_id', '')
        
        if not bot_token or not user_id:
            return False, "Telegram bot_token 或 user_id 未配置"
        
        # 添加消息类型图标
        icon = MSG_TYPE_ICONS.get(msg_type, '')
        title_with_icon = f"{icon} *{title}*" if icon else f"*{title}*"
        
        try:
            api_host = self.config.get('api_host', 'https://api.telegram.org')
            url = f"{api_host}/bot{bot_token}/sendMessage"
            
            text = f"{title_with_icon}\n\n{content}"
            
            data = {
                "chat_id": user_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            
            resp = requests.post(url, json=data, timeout=30)
            result = resp.json()
            
            if result.get('ok'):
                return True, "推送成功"
            return False, result.get('description', '未知错误')
            
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class FeishuClient(BasePushClient):
    """飞书机器人推送"""
    
    def is_configured(self) -> bool:
        webhook = self.config.get('webhook', '')
        return bool(webhook)
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        webhook = self.config.get('webhook', '')
        if not webhook:
            return False, "飞书 webhook 未配置"
        
        # 如果只是 FSKEY，构建完整 webhook URL
        if not webhook.startswith('http'):
            webhook = f"https://open.feishu.cn/open-apis/bot/v2/hook/{webhook}"
        
        # 添加消息类型图标
        icon = MSG_TYPE_ICONS.get(msg_type, '')
        title_with_icon = f"{icon} {title}" if icon else title
        
        # 根据消息类型设置卡片颜色
        color_map = {
            MsgType.INFO: 'blue',
            MsgType.SUCCESS: 'green',
            MsgType.WARNING: 'yellow',
            MsgType.FAILURE: 'red'
        }
        card_color = color_map.get(msg_type, 'blue')
        
        try:
            data = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": title_with_icon
                        },
                        "template": card_color
                    },
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": content
                        }
                    ]
                }
            }
            resp = requests.post(webhook, json=data, timeout=30)
            result = resp.json()
            
            if result.get('StatusCode') == 0 or result.get('code') == 0:
                return True, "推送成功"
            return False, result.get('msg', '未知错误')
            
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class BarkClient(BasePushClient):
    """Bark iOS 推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('push_key'))
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        push_key = self.config.get('push_key', '')
        if not push_key:
            return False, "Bark push_key 未配置"
        
        try:
            # 构建URL
            if push_key.startswith('http'):
                url = push_key
            else:
                url = f"https://api.day.app/{push_key}"
            
            # 添加消息类型图标
            icon = MSG_TYPE_ICONS.get(msg_type, '')
            title_with_icon = f"{icon} {title}" if icon else title
            
            data = {
                "title": title_with_icon,
                "body": content
            }
            
            # 可选参数
            if self.config.get('sound'):
                data['sound'] = self.config['sound']
            if self.config.get('group'):
                data['group'] = self.config['group']
            
            resp = requests.post(url, json=data, timeout=30)
            result = resp.json()
            
            if result.get('code') == 200:
                return True, "推送成功"
            return False, result.get('message', '未知错误')
            
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class ServerChanClient(BasePushClient):
    """Server酱推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('push_key'))
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        push_key = self.config.get('push_key', '')
        if not push_key:
            return False, "Server酱 push_key 未配置"
        
        # 添加消息类型图标
        icon = MSG_TYPE_ICONS.get(msg_type, '')
        title_with_icon = f"{icon} {title}" if icon else title
        
        try:
            # 判断新旧版本
            match = re.match(r"sctp(\d+)t", push_key)
            if match:
                num = match.group(1)
                url = f"https://{num}.push.ft07.com/send/{push_key}.send"
            else:
                url = f"https://sctapi.ftqq.com/{push_key}.send"
            
            data = {
                "title": title_with_icon,
                "desp": content.replace("\n", "\n\n")
            }
            
            resp = requests.post(url, data=data, timeout=30)
            result = resp.json()
            
            if result.get('errno') == 0 or result.get('code') == 0:
                return True, "推送成功"
            return False, result.get('message', result.get('errmsg', '未知错误'))
            
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class PushPlusClient(BasePushClient):
    """PushPlus 推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('token'))
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        token = self.config.get('token', '')
        if not token:
            return False, "PushPlus token 未配置"
        
        # 添加消息类型图标
        icon = MSG_TYPE_ICONS.get(msg_type, '')
        title_with_icon = f"{icon} {title}" if icon else title
        
        try:
            url = "https://www.pushplus.plus/send"
            
            data = {
                "token": token,
                "title": title_with_icon,
                "content": content,
                "template": self.config.get('template', 'html'),
                "channel": self.config.get('channel', 'wechat')
            }
            
            resp = requests.post(url, json=data, timeout=30)
            result = resp.json()
            
            if result.get('code') == 200:
                return True, "推送成功"
            return False, result.get('msg', '未知错误')
            
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


class SMTPClient(BasePushClient):
    """SMTP 邮件推送"""
    
    def is_configured(self) -> bool:
        return all([
            self.config.get('server'),
            self.config.get('email'),
            self.config.get('password')
        ])
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        server = self.config.get('server', '')
        email = self.config.get('email', '')
        password = self.config.get('password', '')
        
        if not server or not email or not password:
            return False, "SMTP 配置不完整"
        
        # 添加消息类型前缀
        type_prefix = {
            MsgType.INFO: '[信息]',
            MsgType.SUCCESS: '[成功]',
            MsgType.WARNING: '[警告]',
            MsgType.FAILURE: '[失败]'
        }
        prefix = type_prefix.get(msg_type, '')
        title_with_prefix = f"{prefix} {title}" if prefix else title
        
        try:
            name = self.config.get('name', 'iHomeGuard')
            use_ssl = self.config.get('ssl', True)
            
            message = MIMEText(content, 'plain', 'utf-8')
            message['From'] = formataddr((Header(name, 'utf-8').encode(), email))
            message['To'] = formataddr((Header(name, 'utf-8').encode(), email))
            message['Subject'] = Header(title_with_prefix, 'utf-8')
            
            if use_ssl:
                smtp_server = smtplib.SMTP_SSL(server, timeout=30)
            else:
                smtp_server = smtplib.SMTP(server, timeout=30)
            
            smtp_server.login(email, password)
            smtp_server.sendmail(email, email, message.as_bytes())
            smtp_server.close()
            
            return True, "推送成功"
            
        except Exception as e:
            return False, str(e)


class WebhookClient(BasePushClient):
    """自定义 Webhook 推送"""
    
    def is_configured(self) -> bool:
        return bool(self.config.get('url'))
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO) -> Tuple[bool, str]:
        url = self.config.get('url', '')
        if not url:
            return False, "Webhook URL 未配置"
        
        try:
            method = self.config.get('method', 'POST').upper()
            headers = self.config.get('headers', {})
            content_type = self.config.get('content_type', 'application/json')
            
            if 'Content-Type' not in headers:
                headers['Content-Type'] = content_type
            
            # 替换模板变量
            body_template = self.config.get('body', '')
            if body_template:
                body = body_template.replace('{title}', title).replace('{content}', content)
            else:
                body = {"title": title, "content": content, "msg_type": msg_type}
            
            if method == 'GET':
                resp = requests.get(url, headers=headers, timeout=30)
            else:
                if isinstance(body, dict) and headers.get('Content-Type') == 'application/json':
                    resp = requests.post(url, json=body, headers=headers, timeout=30)
                else:
                    resp = requests.post(url, data=body, headers=headers, timeout=30)
            
            if 200 <= resp.status_code < 300:
                return True, "推送成功"
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
            
        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, str(e)


# 渠道映射
CHANNEL_CLIENTS = {
    'pushme': PushMeClient,
    'wecom': WecomClient,
    'dingtalk': DingTalkClient,
    'telegram': TelegramClient,
    'feishu': FeishuClient,
    'bark': BarkClient,
    'serverchan': ServerChanClient,
    'pushplus': PushPlusClient,
    'smtp': SMTPClient,
    'webhook': WebhookClient
}

# 渠道名称映射（用于显示）
CHANNEL_NAMES = {
    'pushme': 'PushMe',
    'wecom': '企业微信',
    'dingtalk': '钉钉',
    'telegram': 'Telegram',
    'feishu': '飞书',
    'bark': 'Bark (iOS)',
    'serverchan': 'Server酱',
    'pushplus': 'PushPlus',
    'smtp': '邮件 (SMTP)',
    'webhook': '自定义Webhook'
}


class PushDispatcher:
    """推送调度器 - 管理多渠道推送"""
    
    def __init__(self, push_config: Dict[str, Any]):
        """
        Args:
            push_config: 推送配置，包含 enabled 和 channels
        """
        self.enabled = push_config.get('enabled', True)
        self.clients: Dict[str, BasePushClient] = {}
        
        channels = push_config.get('channels', {})
        for channel_name, channel_config in channels.items():
            if channel_name in CHANNEL_CLIENTS:
                client_class = CHANNEL_CLIENTS[channel_name]
                self.clients[channel_name] = client_class(channel_config or {})
    
    def send(self, title: str, content: str, msg_type: str = MsgType.INFO, channels: List[str] = None) -> Tuple[bool, str]:
        """通过指定渠道发送消息
        
        Args:
            title: 消息标题
            content: 消息内容
            msg_type: 消息类型
            channels: 指定渠道列表，None 表示发送到所有已启用的渠道
        
        Returns:
            (success: bool, message: str)
        """
        if not self.enabled:
            return False, "推送已禁用"
        
        if channels is None:
            # 发送到所有已启用且已配置的渠道
            channels = [
                name for name, client in self.clients.items()
                if client.config.get('enabled', False) and client.is_configured()
            ]
        
        if not channels:
            return False, "未配置任何推送渠道"
        
        results = []
        for channel_name in channels:
            if channel_name not in self.clients:
                continue
            
            client = self.clients[channel_name]
            if not client.is_configured():
                continue
            
            success, msg = client.send(title, content, msg_type)
            channel_display = CHANNEL_NAMES.get(channel_name, channel_name)
            results.append((channel_display, success, msg))
            
            # 只要有一个成功就返回成功
            if success:
                return True, f"{channel_display} 推送成功"
        
        if not results:
            return False, "未找到有效的推送渠道"
        
        # 全部失败，返回错误信息
        errors = [f"{name}: {msg}" for name, success, msg in results if not success]
        return False, '; '.join(errors)
    
    def test_channel(self, channel_name: str) -> Tuple[bool, str]:
        """测试指定渠道"""
        if channel_name not in self.clients:
            return False, f"未知渠道: {channel_name}"
        
        client = self.clients[channel_name]
        if not client.is_configured():
            return False, f"{CHANNEL_NAMES.get(channel_name, channel_name)} 未配置"
        
        title = 'iHomeGuard 连接测试'
        content = '## ✅ 测试成功\n\niHomeGuard 推送功能正常\n\n---\n发送时间: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return client.send(title, content, MsgType.SUCCESS)
    
    def get_configured_channels(self) -> List[str]:
        """获取已配置的渠道列表"""
        return [
            name for name, client in self.clients.items()
            if client.is_configured()
        ]
    
    def get_enabled_channels(self) -> List[str]:
        """获取已启用的渠道列表"""
        return [
            name for name, client in self.clients.items()
            if client.config.get('enabled', False) and client.is_configured()
        ]


# 兼容旧接口
class MultiPushClient(PushDispatcher):
    """多渠道推送客户端（兼容旧接口）"""
    
    def __init__(self, pushme_config: Dict[str, Any]):
        # 兼容旧配置格式
        if 'channels' not in pushme_config and 'push_key' in pushme_config:
            # 旧格式，转换为新格式
            push_config = {
                'enabled': pushme_config.get('enabled', True),
                'channels': {
                    'pushme': {
                        'enabled': True,
                        'push_key': pushme_config.get('push_key', ''),
                        'api_url': pushme_config.get('api_url', 'https://push.i-i.me'),
                        'group': pushme_config.get('group', 'iHomeGuard'),
                        'icon': pushme_config.get('icon', '🏠')
                    },
                    'wecom': {
                        'enabled': bool(pushme_config.get('wecom_webhook')),
                        'webhook': pushme_config.get('wecom_webhook', '')
                    },
                    'dingtalk': {
                        'enabled': bool(pushme_config.get('dingtalk_webhook')),
                        'webhook': pushme_config.get('dingtalk_webhook', ''),
                        'secret': pushme_config.get('dingtalk_secret', '')
                    }
                }
            }
        else:
            push_config = pushme_config
        
        super().__init__(push_config)
        
        # 兼容旧属性
        self.pushme = self.clients.get('pushme')
        self.wecom = self.clients.get('wecom')
        self.dingtalk = self.clients.get('dingtalk')
    
    def test_push(self, channel: str) -> Tuple[bool, str]:
        """测试指定渠道（兼容旧接口）"""
        if channel == 'pushme':
            return self.test_channel('pushme')
        elif channel == 'wecom':
            return self.test_channel('wecom')
        elif channel == 'dingtalk':
            return self.test_channel('dingtalk')
        else:
            return self.test_channel(channel)
    
    def send_daily_report(self, report_data: dict) -> Tuple[bool, str]:
        """发送日报"""
        date = report_data['date']
        
        title = f"昨日网络日报 - {date}"
        
        # 流量统计
        upload_gb = report_data['total_upload'] / (1024 ** 3)
        download_gb = report_data['total_download'] / (1024 ** 3)
        total_gb = upload_gb + download_gb
        
        content = f"""## 📊 昨日网络日报 - {date}

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
        
        # 日报使用 INFO 类型
        return self.send(title, content, MsgType.INFO)
    
    def send_alert(self, alert_type: str, message: str) -> Tuple[bool, str]:
        """发送告警"""
        # 根据告警类型设置图标
        icons = {
            'new_device': '🔐',
            'high_traffic': '📊',
            'long_online': '⏰',
            'high_connections': '🔗',
            'device_offline': '📴'
        }
        icon = icons.get(alert_type, '⚠️')
        
        title = f"网络告警 - {alert_type}"
        content = f"""## {icon} 网络告警

### 告警类型
**{alert_type}**

### 详情
{message}

### 时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*iHomeGuard 家庭网络监控*"""
        
        # 告警使用 WARNING 类型
        return self.send(title, content, MsgType.WARNING)
    
    def send_startup_notification(self, status_info: dict) -> Tuple[bool, str]:
        """发送启动通知"""
        title = "系统启动通知"
        
        # 爱快连接状态
        ikuai_status = "✅ 连接正常" if status_info.get('ikuai_connected') else "⚠️ 未连接"
        ikuai_detail = status_info.get('ikuai_message', '')
        
        # 推送状态
        push_status = "✅ 已启用" if status_info.get('push_enabled') else "❌ 未配置"
        
        # 配置状态
        config_status = "✅ 完整" if status_info.get('config_complete') else "⚠️ 待完善"
        
        content = f"""## 🚀 iHomeGuard 系统已启动

### 📊 系统状态

| 检查项 | 状态 |
|--------|------|
| 🔌 爱快路由器 | **{ikuai_status}** |
| 🔔 消息推送 | **{push_status}** |
| ⚙️ 系统配置 | **{config_status}** |

"""
        
        # 添加爱快连接详情
        if ikuai_detail:
            content += f"### 💡 连接详情\n{ikuai_detail}\n\n"
        
        # 添加未连接时的提示
        if not status_info.get('ikuai_connected'):
            content += """### 📌 操作提示
请登录管理后台，前往【设置】页面完成爱快路由器连接配置：
1. 填写路由器地址、用户名和密码
2. 点击【测试连接】验证配置
3. 保存设置后系统将自动开始监控

"""
        
        content += f"""### ⏰ 启动时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 📦 版本
{status_info.get('version', 'v1.0.0')}

---
*iHomeGuard 家庭网络监控*"""
        
        # 启动通知使用 SUCCESS 类型
        return self.send(title, content, MsgType.SUCCESS)
