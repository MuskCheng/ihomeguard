<div align="center">

  <img src="docs/iHG.png" alt="iHomeGuard Logo" width="120" height="120">

  # iHomeGuard

  **爱快家庭网络卫士**

  <i>一个现代化的家庭网络监控与管理工具</i>

  [![Version](https://img.shields.io/badge/Version-1.2.6-blue?logo=semver&logoColor=white)](https://github.com/MuskCheng/ihomeguard/releases)
  [![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Flask-3.1-green?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker&logoColor=white)](https://www.docker.com/)
  [![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
  [![GitHub Stars](https://img.shields.io/github/stars/MuskCheng/ihomeguard?style=social)](https://github.com/MuskCheng/ihomeguard/stargazers)

  [功能特性](#-功能特性) • [快速开始](#-快速开始) • [截图预览](#-截图预览) • [配置说明](#-配置说明) • [API文档](#-api-文档)

</div>

---

## 📖 简介

**iHomeGuard** 是一个基于 [爱快路由器](https://www.ikuai8.com/) 的家庭网络监控工具，专为个人家庭用户设计。通过现代化的 Web 界面，帮助您实时掌握家庭网络状态，智能检测异常设备，并在重要事件发生时及时推送通知。

### ✨ 核心亮点

- 🎨 **现代化 UI** - 炫酷的深色/浅色主题，响应式设计适配各种设备
- 📱 **实时监控** - 实时查看在线设备、流量速度、连接数
- 📊 **数据可视化** - 流量趋势图表、设备统计、流量预测
- 🚨 **智能告警** - 新设备检测、设备离线、流量异常告警
- 📬 **多渠道推送** - 支持 PushMe、企业微信、钉钉
- 🔐 **安全存储** - 敏感数据加密存储，保护隐私安全
- 🔑 **用户认证** - 用户名/密码登录，bcrypt 密码哈希，JWT Token（v1.2.5+）
- 👤 **账户管理** - 修改密码、用户管理、权限控制（v1.2.6+）
- 💾 **配置备份** - 支持配置导出导入（v1.2.3+）

---

## 🚀 功能特性

<table>
<tr>
<td width="50%">

### 📱 设备监控
- 实时在线设备列表
- 设备流量速度监控
- 设备连接数统计
- 设备厂商识别
- 智能设备图标
- 信任设备标记
- 在线时长统计

</td>
<td width="50%">

### 📊 流量统计
- 实时流量图表
- 14天流量趋势
- 设备在线统计
- 月度流量预测
- 今日流量汇总
- 历史数据查询

</td>
</tr>
<tr>
<td width="50%">

### 🚨 智能告警
- 新设备接入告警
- 信任设备离线告警
- 流量异常告警
- 长时间在线告警
- 告警记录管理
- 一键处理告警

</td>
<td width="50%">

### 📬 消息推送
- PushMe 推送
- 企业微信机器人
- 钉钉机器人
- 每日网络日报
- 实时告警通知
- 推送测试功能

</td>
</tr>
<tr>
<td width="50%">

### 🔐 安全特性
- 用户名/密码认证
- bcrypt 密码哈希存储
- JWT Token 认证（24小时有效）
- 登录失败锁定（5次锁定5分钟）
- 首次启动注册管理员
- 管理员权限控制
- 敏感字段脱敏显示

</td>
<td width="50%">

### ⚙️ 系统功能
- 配置备份/恢复
- 版本更新检查
- 数据库维护
- 日志级别控制

</td>
</tr>
</table>

---

## 📸 截图预览

### 桌面端

<div align="center">

| 设备监控 | 流量统计 |
|:---:|:---:|
| ![Desktop Home](docs/screenshots/desktop-home-1440px.jpg) | ![Stats](docs/screenshots/stats.png) |

| 告警管理 | 系统设置 |
|:---:|:---:|
| ![Alerts](docs/screenshots/alerts.png) | ![Settings](docs/screenshots/settings.png) |

| 深色模式 | 浅色模式 |
|:---:|:---:|
| ![Dark Mode](docs/screenshots/dark-mode.png) | ![Light Mode](docs/screenshots/light-mode.png) |

</div>

### 移动端

<div align="center">

| 设备列表 | 流量统计 | 告警管理 |
|:---:|:---:|:---:|
| ![Mobile Home](docs/screenshots/mobile-home-375px.jpg) | ![Mobile Stats](docs/screenshots/mobile-stats-375px.jpg) | ![Mobile Alerts](docs/screenshots/mobile-alerts-375px.jpg) |

| 系统设置 | 菜单导航 |
|:---:|:---:|
| ![Mobile Settings](docs/screenshots/mobile-settings-375px.jpg) | ![Mobile Menu](docs/screenshots/mobile-menu-open-375px.jpg) |

</div>

---

## 🛠️ 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/MuskCheng/ihomeguard.git
cd ihomeguard

# 2. 使用 Docker Compose 启动
docker compose up -d

# 3. 访问 Web 界面
# http://localhost:8680
```

### 方式二：本地运行

```bash
# 1. 克隆项目
git clone https://github.com/MuskCheng/ihomeguard.git
cd ihomeguard

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python app.py

# 4. 访问 Web 界面
# http://localhost:8680
```

### 首次配置

1. 打开浏览器访问 `http://localhost:8680`
2. 如果是首次运行且启用了认证，会显示注册界面
3. 创建管理员账户（用户名 + 密码）
4. 使用创建的账户登录
5. 点击右上角「设置」进入配置页面
6. 填写爱快路由器地址和只读账户信息
7. 点击「测试连接」验证配置
8. 配置推送渠道（可选）
9. 点击「保存设置」

---

## ⚙️ 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `AUTH_TOKEN` | 认证 Token（旧版兼容，启用后需验证） | 无（不启用认证） |
| `JWT_SECRET` | JWT 密钥 | 自动生成 |
| `LOG_LEVEL` | 日志级别 | INFO |
| `IKUAI_URL` | 爱快路由器地址 | 配置文件 |
| `IKUAI_USER` | 爱快用户名 | 配置文件 |
| `IKUAI_PASS` | 爱快密码 | 配置文件 |

### 爱快路由器配置

| 配置项 | 说明 | 示例 |
|--------|------|------|
| 路由器地址 | 爱快路由器管理地址 | `http://192.168.1.1` |
| 用户名 | 只读账户用户名 | `monitor` |
| 密码 | 只读账户密码 | `your_password` |
| 会话超时 | 会话保活时间（分钟），需与爱快系统账号配置保持一致 | `120` |

> ⚠️ **安全建议**：请勿使用管理员账户！建议创建只读账户用于数据采集。

### 推送渠道配置

| 渠道 | 配置项 | 获取方式 |
|------|--------|----------|
| PushMe | Push Key | [PushMe 官网](https://push.i-i.me/) |
| 企业微信 | Webhook 地址 | 企业微信群机器人设置 |
| 钉钉 | Webhook + 密钥 | 钉钉群机器人设置 |

### 监控参数配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 采集间隔 | 10秒 | 数据采集频率，建议 10-60 秒 |
| 日报时间 | 07:00 | 每日推送时间（推送前一天数据） |
| 流量告警阈值 | 10GB | 单设备日流量告警 |
| 长在线阈值 | 24小时 | 设备连续在线告警 |
| 上传速度告警 | 10MB/s | 单设备上传速度告警 |
| 下载速度告警 | 50MB/s | 单设备下载速度告警 |
| 单设备连接数阈值 | 500 | 单设备连接数告警 |
| 总连接数阈值 | 1000 | 全网连接数告警 |

---

## 📁 项目结构

```
ihomeguard/
├── 📄 app.py                 # 应用入口
├── 📄 config.py              # 配置管理
├── 📄 storage.py             # 数据存储层
├── 📄 scheduler.py           # 定时任务调度
├── 📄 logger.py              # 统一日志模块
├── 📄 requirements.txt       # Python 依赖
├── 📄 Dockerfile             # Docker 构建文件
├── 📄 docker-compose.yml     # Docker Compose 配置
├── 📂 clients/               # API 客户端
│   └── 📄 ikuai_local.py     # 爱快路由器 API
├── 📂 services/              # 业务服务层
│   ├── 📄 monitor.py         # 监控服务
│   ├── 📄 alerter.py         # 告警检测
│   ├── 📄 reporter.py        # 日报生成
│   ├── 📄 pusher.py          # 推送服务
│   ├── 📄 vendor.py          # 设备厂商查询
│   ├── 📄 auth.py            # 认证中间件
│   ├── 📄 backup.py          # 备份恢复服务
│   └── 📄 updater.py         # 版本检查服务
├── 📂 web/                   # Web 层
│   ├── 📄 routes.py          # API 路由
│   ├── 📂 static/            # 静态资源
│   └── 📂 templates/         # HTML 模板
├── 📂 docs/                  # 文档
│   └── 📂 screenshots/       # 截图
├── 📂 data/                  # 数据目录
└── 📂 config/                # 配置目录
```

---

## 🔌 API 文档

### 设备相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/devices` | GET | 获取在线设备列表 |
| `/api/devices/all` | GET | 获取所有设备（含离线） |
| `/api/device/<mac>/alias` | POST | 设置设备备注/信任 |
| `/api/device/<mac>/kick` | POST | 踢设备下线 |
| `/api/device/<mac>/events` | GET | 获取设备事件历史 |

### 统计相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stats/today` | GET | 获取今日统计 |
| `/api/stats/week` | GET | 获取近7天统计 |
| `/api/stats/prediction` | GET | 获取流量预测 |

### 告警相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/alerts` | GET | 获取未处理告警 |
| `/api/alert/<id>/resolve` | POST | 处理告警 |

### 系统相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 获取配置 |
| `/api/config` | POST | 保存配置 |
| `/api/test/ikuai` | POST | 测试爱快连接 |
| `/api/test/push` | POST | 测试推送 |
| `/api/health` | GET | 健康检查 |
| `/api/system/info` | GET | 获取系统信息 |
| `/api/system/update/check` | GET | 检查版本更新 |
| `/api/backup/export` | POST | 导出备份 |
| `/api/backup/import` | POST | 导入备份 |

### 认证相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/auth/status` | GET | 获取认证状态 |
| `/api/auth/login` | POST | 用户名/密码登录 |
| `/api/auth/init` | POST | 首次启动注册管理员 |
| `/api/auth/change-password` | POST | 修改密码 |
| `/api/auth/users` | GET | 获取用户列表（管理员） |
| `/api/auth/users` | POST | 创建用户（管理员） |
| `/api/auth/users/<username>` | DELETE | 删除用户（管理员） |

---

## 🔧 技术栈

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vue.js&logoColor=white" alt="Vue.js">
  <img src="https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chart.js&logoColor=white" alt="Chart.js">
  <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
</p>

---

## 📝 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 获取完整的更新日志。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 开源协议

本项目基于 [MIT](LICENSE) 协议开源。

---

## 🙏 致谢

- [爱快路由器](https://www.ikuai8.com/) - 提供强大的路由器 API
- [Vue.js](https://vuejs.org/) - 渐进式 JavaScript 框架
- [Chart.js](https://www.chartjs.org/) - 灵活的图表库
- [Flask](https://flask.palletsprojects.com/) - 轻量级 Web 框架

---

<div align="center">

  **⭐ 如果这个项目对你有帮助，请给一个 Star ⭐**

  Made with ❤️ by [MuskCheng](https://github.com/MuskCheng)

</div>