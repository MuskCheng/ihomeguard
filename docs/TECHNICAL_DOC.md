# iHomeGuard 技术文档

## 一、项目概述

### 1.1 项目名称
**iHomeGuard** - 爱快家庭网络卫士

### 1.2 项目定位
基于爱快路由器的家庭网络监控工具，为个人家庭用户提供网络设备管理、流量统计、异常告警等功能。

### 1.3 技术栈

| 组件 | 技术选型 | 版本 |
|------|----------|------|
| 后端语言 | Python | 3.12 |
| Web 框架 | Flask | 2.3+ |
| 前端框架 | Vue.js 3 (CDN) | 3.x |
| 图表库 | Chart.js | 4.x |
| 数据库 | SQLite | 3 |
| 定时任务 | APScheduler | 3.10+ |
| HTTP 客户端 | requests | 2.28+ |
| 容器化 | Docker | - |

---

## 二、系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      iHomeGuard 系统                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐                      ┌──────────────┐    │
│  │  爱快路由器   │◄──── API 采集 ──────│  Web 后台    │    │
│  │  (数据源)    │                      │  (Flask)    │    │
│  └──────────────┘                      └──────┬───────┘    │
│         │                                     │            │
│         │                                     ▼            │
│         │           ┌─────────────────────────────┐       │
│         │           │     Vue.js + Chart.js       │       │
│         │           │     (响应式前端)             │       │
│         │           └─────────────────────────────┘       │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │ 监控服务     │───▶│ 存储层       │───▶│ 推送服务     │ │
│  │ MonitorService│    │ SQLite      │    │ PushMe      │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                                     ▲            │
│         │                                     │            │
│         ▼                                     │            │
│  ┌──────────────┐    ┌──────────────┐        │            │
│  │ 告警服务     │───▶│ 日报服务     │────────┘            │
│  │ AlerterService│    │ ReporterService│                  │
│  └──────────────┘    └──────────────┘                     │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │                 APScheduler (定时任务)                │ │
│  │  • 数据采集 (可配置间隔)                              │ │
│  │  • 日报推送 (可配置时间)                              │ │
│  │  • 统计汇总 (每日 23:55)                              │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
ihomeguard/
├── app.py                    # 主入口
├── config.py                 # 配置管理
├── scheduler.py              # 定时任务调度
├── storage.py                # 数据存储层
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 镜像构建
├── docker-compose.yml        # Docker 编排
├── .env.example              # 环境变量示例
│
├── clients/                  # API 客户端
│   ├── __init__.py
│   └── ikuai_local.py        # 爱快本地 API 客户端
│
├── services/                 # 业务服务
│   ├── __init__.py
│   ├── monitor.py            # 监控服务
│   ├── alerter.py            # 告警检测
│   ├── reporter.py           # 日报生成
│   ├── pusher.py             # PushMe 推送
│   └── vendor.py             # 设备厂商识别
│
├── web/                      # Web 层
│   ├── routes.py             # API 路由
│   ├── templates/
│   │   └── index.html        # 单页应用
│   └── static/               # 静态资源
│
├── config/                   # 配置目录
│   └── config.json           # 运行时配置
│
└── data/                     # 数据目录
    └── ihomeguard.db         # SQLite 数据库
```

---

## 三、核心模块设计

### 3.1 爱快本地 API 客户端 (`clients/ikuai_local.py`)

#### 认证方式
```python
# 登录接口
POST /Action/login
参数:
  - username: 用户名明文
  - passwd: 密码 MD5 值
  - pass: 固定值 "true"
  - remember_password: "true" 或 "false"

# 返回 Cookie: sess_key
```

#### 主要方法

| 方法 | 功能 | API 端点 |
|------|------|----------|
| `login()` | 登录获取会话 | `/Action/login` |
| `get_online_devices()` | 获取在线设备 | `func_name=online, action=show` |
| `get_terminal_list()` | 获取终端列表 | `func_name=terminal, action=show` |
| `get_flow_stat()` | 获取流量统计 | `func_name=flow_stat, action=show` |
| `kick_device(mac)` | 踢设备下线 | `func_name=online, action=offline` |
| `set_terminal_alias(mac, alias)` | 设置设备备注 | `func_name=terminal, action=edit` |

#### 在线设备数据结构
```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "ip": "192.168.1.100",
  "hostname": "device-name",
  "upload": 1048576,
  "download": 10485760,
  "upload_speed": 1024,
  "download_speed": 10240,
  "connections": 15
}
```

### 3.2 监控服务 (`services/monitor.py`)

#### 核心流程
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 获取在线设备 │───▶│ 更新设备信息 │───▶│ 记录流量数据 │
└─────────────┘    └─────────────┘    └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │ 检测上下线  │
                   └─────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ 新设备检测│   │ 告警检测 │   │ 事件记录 │
    └──────────┘   └──────────┘   └──────────┘
```

### 3.3 告警服务 (`services/alerter.py`)

#### 告警类型

| 类型 | 触发条件 | 严重级别 |
|------|----------|----------|
| `new_device` | 新 MAC 地址首次出现 | warning |
| `high_traffic` | 设备流量超过阈值 | warning |
| `long_online` | 设备在线超过 N 小时 | info |
| `high_connections` | 连接数超过阈值 | warning |

#### 告警去重策略
- 同一设备、同一类型、同一日期只产生一条告警
- 使用 `get_alerts_by_type_date()` 检查

### 3.4 日报服务 (`services/reporter.py`)

#### 日报内容
```markdown
## 📊 家庭网络日报 - YYYY-MM-DD

### 📈 流量统计
| 指标 | 数值 |
|------|------|
| ⬆️ 总上传 | X.X GB |
| ⬇️ 总下载 | X.X GB |

### 📱 设备概览
| 指标 | 数值 |
|------|------|
| 当前在线 | X 台 |
| 日峰值 | X 台 |

### 🔌 设备详情
...

### ⚠️ 异常提醒
...
```

### 3.5 存储层 (`storage.py`)

#### 数据库表设计

**devices (设备信息表)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| mac | TEXT | MAC 地址 (唯一) |
| ip | TEXT | IP 地址 |
| hostname | TEXT | 主机名 |
| alias | TEXT | 用户备注 |
| vendor | TEXT | 设备厂商 |
| is_trusted | INTEGER | 是否信任设备 |
| first_seen | DATETIME | 首次发现时间 |
| last_seen | DATETIME | 最后在线时间 |

**online_records (在线记录表)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| mac | TEXT | 设备 MAC |
| upload_bytes | INTEGER | 上传流量 |
| download_bytes | INTEGER | 下载流量 |
| upload_speed | INTEGER | 上传速率 |
| download_speed | INTEGER | 下载速率 |
| connections | INTEGER | 连接数 |
| recorded_at | DATETIME | 记录时间 |

**daily_stats (每日统计表)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| date | TEXT | 日期 (YYYY-MM-DD) |
| total_upload | INTEGER | 总上传 |
| total_download | INTEGER | 总下载 |
| device_count | INTEGER | 设备数 |
| max_connections | INTEGER | 最大连接数 |
| peak_device_count | INTEGER | 峰值设备数 |

**alerts (告警表)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| alert_type | TEXT | 告警类型 |
| severity | TEXT | 严重级别 |
| mac | TEXT | 相关设备 |
| message | TEXT | 告警消息 |
| is_resolved | INTEGER | 是否已处理 |
| created_at | DATETIME | 创建时间 |

**device_events (设备事件表)**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| mac | TEXT | 设备 MAC |
| event_type | TEXT | 事件类型 (online/offline) |
| ip | TEXT | IP 地址 |
| happened_at | DATETIME | 发生时间 |

---

## 四、Web API 接口

### 4.1 设备相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/devices` | GET | 获取在线设备列表 |
| `/api/devices/all` | GET | 获取所有设备 |
| `/api/device/<mac>/alias` | POST | 设置设备备注 |
| `/api/device/<mac>/kick` | POST | 踢设备下线 |
| `/api/device/<mac>/events` | GET | 获取设备事件历史 |

### 4.2 统计相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stats/today` | GET | 获取今日统计 |
| `/api/stats/week` | GET | 获取最近7天统计 |

### 4.3 告警相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/alerts` | GET | 获取告警列表 |
| `/api/alert/<id>/resolve` | POST | 处理告警 |

### 4.4 配置相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 获取配置 |
| `/api/config` | POST | 保存配置 |
| `/api/test/ikuai` | POST | 测试爱快连接 |
| `/api/test/pushme` | POST | 测试推送 |

### 4.5 系统相关

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |

---

## 五、配置管理

### 5.1 配置来源优先级

1. **环境变量** (最高优先级，适合 Docker 部署)
2. **配置文件** `config/config.json`
3. **默认值** (最低优先级)

### 5.2 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `IKUAI_URL` | 爱快路由器地址 | `http://192.168.1.1` |
| `IKUAI_USER` | 登录用户名 | `admin` |
| `IKUAI_PASS` | 登录密码 | `your_password` |
| `PUSHME_KEY` | PushMe 推送密钥 | `xxx` |
| `WEB_PORT` | Web 端口 | `8680` |

### 5.3 配置文件结构

```json
{
  "app": {
    "name": "iHomeGuard",
    "version": "1.0.0"
  },
  "ikuai": {
    "local_url": "http://192.168.1.1",
    "username": "admin",
    "password": "your_password"
  },
  "pushme": {
    "push_key": "your_pushme_key",
    "api_url": "https://push.i-i.me",
    "enabled": true
  },
  "monitor": {
    "collect_interval": 300,
    "report_time": "21:00",
    "alert_new_device": true,
    "traffic_threshold_gb": 10,
    "long_online_hours": 24,
    "high_connection_threshold": 500
  },
  "web": {
    "host": "0.0.0.0",
    "port": 8680
  }
}
```

---

## 六、部署方案

### 6.1 Docker 部署 (推荐)

```bash
# 1. 克隆项目
git clone https://github.com/xxx/ihomeguard.git
cd ihomeguard

# 2. 配置环境变量
cp .env.example .env
nano .env

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

### 6.2 PVE LXC 容器部署

```bash
# 1. 创建容器
pct create 104 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst \
  --hostname ihomeguard \
  --memory 1024 \
  --cores 1 \
  --rootfs local:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 0 \
  --features nesting=1,keyctl=1 \
  --start 1

# 2. 进入容器
pct enter 104

# 3. 安装 Docker
curl -fsSL https://get.docker.com | sh

# 4. 部署项目
mkdir -p /opt/ihomeguard
cd /opt/ihomeguard
# 上传项目文件或 git clone

# 5. 启动
docker-compose up -d
```

### 6.3 直接运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp config/config.example.json config/config.json
nano config/config.json

# 3. 运行
python app.py
```

---

## 七、后续开发计划

### 7.1 阶段三：功能增强

| 优先级 | 功能 | 说明 | 预估工作量 |
|--------|------|------|------------|
| 🔴 高 | 设备分组管理 | 按家庭成员/设备类型分组 | 2h |
| 🔴 高 | 实时告警推送 | 告警产生时立即推送 | 1h |
| 🟡 中 | 设备在线时长统计 | 每日/每周设备在线时长排行 | 1.5h |
| 🟡 中 | 网络质量监控 | 延迟、丢包率监控 | 2h |
| 🟢 低 | 数据导出 | 导出 CSV/Excel | 1h |

### 7.2 阶段四：高级功能

| 功能 | 说明 | 预估工作量 |
|------|------|------------|
| 设备自动识别 | 根据流量特征识别设备类型 | 4h |
| 异常行为检测 | 检测异常流量模式 | 6h |
| 家庭网络拓扑 | 可视化网络拓扑图 | 4h |
| 移动端适配优化 | PWA 支持 | 3h |
| 语音播报 | PushMe 语音播报重要告警 | 1h |

### 7.3 技术优化方向

| 项目 | 当前方案 | 优化方向 |
|------|----------|----------|
| 数据库 | SQLite | 保持现状（个人使用足够） |
| 前端 | Vue.js CDN | 保持现状（简单部署） |
| 缓存 | 无 | 可选 Redis（性能优化） |
| 日志 | print | 可选 logging 模块 |

---

## 八、注意事项

### 8.1 安全建议

1. **密码保护**: 建议在爱快路由器中创建只读用户
2. **网络隔离**: Web 服务不要直接暴露到公网
3. **HTTPS**: 通过 Lucky 反代配置 HTTPS

### 8.2 性能建议

1. **采集间隔**: 建议 300 秒（5分钟），避免频繁请求
2. **数据清理**: 定期清理超过 30 天的历史数据
3. **数据库**: 定期执行 `VACUUM` 压缩数据库

### 8.3 常见问题

| 问题 | 解决方案 |
|------|----------|
| 登录失败 | 检查用户名密码、路由器地址 |
| 推送失败 | 检查 push_key 是否正确 |
| 数据为空 | 检查采集任务是否正常运行 |
| 设备不显示 | 检查爱快终端管理是否开启 |

---

## 九、版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.0.0 | 2026-03-04 | 初始版本，MVP 功能 |

---

*文档最后更新: 2026-03-04*
