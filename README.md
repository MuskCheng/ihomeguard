# iHomeGuard - 爱快家庭网络卫士

基于爱快路由器的家庭网络监控工具，为个人家庭用户提供网络设备管理、流量统计、异常告警等功能。

## 功能特性

- 📱 **设备监控** - 实时查看在线设备、流量、连接数
- 📊 **流量统计** - 每日/每周流量统计与趋势图表
- 🚨 **异常告警** - 新设备检测、高流量、长在线告警
- 📰 **日报推送** - 每日网络报告推送到手机
- 🏷️ **设备管理** - 设备备注、分组、踢下线

## 快速开始

### Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/EddyCheng/ihomeguard.git
cd ihomeguard

# 2. 配置环境变量
cp .env.example .env
nano .env

# 3. 启动服务
docker compose up -d

# 4. 访问 Web 界面
# http://localhost:8680
```

### 环境变量配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `IKUAI_URL` | 爱快路由器地址 | `http://192.168.1.1` |
| `IKUAI_USER` | 登录用户名 | `monitor` |
| `IKUAI_PASS` | 登录密码 | `your_password` |
| `PUSHME_KEY` | PushMe 推送密钥 | `xxx` |
| `WEB_PORT` | Web 端口 | `8680` |

## 安全建议

⚠️ **请勿使用管理员账户！**

建议在爱快路由器中创建只读账户：
1. 登录爱快路由器管理后台
2. 进入【系统设置】→【账户管理】
3. 点击【添加账户】
4. 权限选择：**只读权限**

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.12 + Flask |
| 前端 | Vue.js 3 + Chart.js |
| 数据库 | SQLite |
| 定时任务 | APScheduler |
| 容器化 | Docker |

## 目录结构

```
ihomeguard/
├── app.py              # 主入口
├── config.py           # 配置管理
├── storage.py          # 数据存储
├── scheduler.py        # 定时任务
├── clients/            # API 客户端
│   └── ikuai_local.py  # 爱快 API
├── services/           # 业务服务
│   ├── monitor.py      # 监控服务
│   ├── alerter.py      # 告警检测
│   ├── reporter.py     # 日报生成
│   └── pusher.py       # 推送服务
└── web/                # Web 层
    ├── routes.py       # API 路由
    └── templates/      # 前端页面
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/devices` | GET | 获取在线设备 |
| `/api/stats/today` | GET | 今日统计 |
| `/api/stats/week` | GET | 近7天统计 |
| `/api/alerts` | GET | 告警列表 |
| `/api/config` | GET/POST | 配置管理 |
| `/api/health` | GET | 健康检查 |

## 更新日志

### v1.0.0 (2026-03-04)
- 初始版本发布
- 设备监控、流量统计、日报推送、异常告警

## License

MIT
