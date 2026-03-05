"""PushMe 推送客户端"""
import requests


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
    
    def send_daily_report(self, report_data: dict) -> tuple:
        """发送日报
        
        Returns:
            (success: bool, message: str)
        """
        date = report_data['date']
        
        title = f"[i][#NetMonitor!📊] 网络日报 - {date}"
        
        # 流量统计
        upload_gb = report_data['total_upload'] / (1024 ** 3)
        download_gb = report_data['total_download'] / (1024 ** 3)
        total_gb = upload_gb + download_gb
        
        content = f"""## 📊 家庭网络日报 - {date}

### 📈 流量统计
| 指标 | 数值 |
|------|------|
| ⬆️ 总上传 | **{upload_gb:.2f} GB** |
| ⬇️ 总下载 | **{download_gb:.2f} GB** |
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
            content += "### 🔌 设备流量排行\n"
            content += "| 设备 | 上传 | 下载 |\n"
            content += "|------|------|------|\n"
            
            sorted_devices = sorted(
                report_data['devices'],
                key=lambda x: x.get('total_download', 0),
                reverse=True
            )[:5]
            
            for dev in sorted_devices:
                name = dev.get('alias') or dev.get('hostname') or dev['mac'][:8]
                up = dev.get('total_upload', 0) / (1024 ** 2)
                down = dev.get('total_download', 0) / (1024 ** 2)
                content += f"| {name} | {up:.0f} MB | {down:.0f} MB |\n"
        
        # 告警信息
        if report_data.get('alerts'):
            content += "\n### ⚠️ 异常提醒\n"
            for alert in report_data['alerts'][:5]:
                content += f"- {alert['message']}\n"
        
        content += "\n---\n*NetMonitor 家庭网络监控*"
        
        return self.send(title, content, "markdown")
    
    def send_alert(self, alert_type: str, message: str) -> tuple:
        """发送告警
        
        Returns:
            (success: bool, message: str)
        """
        title = f"[w][#NetMonitor!⚠️] 网络告警"
        content = f"## ⚠️ 网络告警\n\n**类型**: {alert_type}\n\n**详情**: {message}\n"
        return self.send(title, content, "markdown")
