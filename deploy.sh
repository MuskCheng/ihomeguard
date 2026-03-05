#!/bin/bash
# iHomeGuard PVE 部署脚本
# 用于在 PVE LXC 容器中部署 iHomeGuard

set -e

echo "=========================================="
echo "  iHomeGuard - 爱快家庭网络卫士 部署脚本"
echo "=========================================="

# 配置
PROJECT_DIR="/opt/ihomeguard"
REGISTRY="registry.cn-hangzhou.aliyuncs.com"
NAMESPACE="eddycheng"
IMAGE_NAME="${REGISTRY}/${NAMESPACE}/ihomeguard:dev"

# 创建目录
mkdir -p $PROJECT_DIR/data $PROJECT_DIR/config
cd $PROJECT_DIR

# 检查配置文件
if [ ! -f ".env" ]; then
    echo ""
    echo "🔒 安全提示：请创建只读账户！"
    echo "   请勿使用管理员账户，建议在爱快路由器中创建只读账户："
    echo "   系统设置 → 账户管理 → 添加账户 → 权限选择【只读】"
    echo ""
    echo "[配置] 创建 .env 文件..."
    cat > .env << 'EOF'
# ========================================
#  爱快路由器配置（请使用只读账户！）
# ========================================
IKUAI_URL=http://192.168.1.1
IKUAI_USER=monitor
IKUAI_PASS=your_password

# PushMe 推送配置
PUSHME_KEY=your_pushme_key

# Web 端口
WEB_PORT=8680
EOF
    echo ""
    echo "[提示] 请编辑 $PROJECT_DIR/.env 配置爱快和推送信息"
    echo "       nano $PROJECT_DIR/.env"
    echo ""
    echo "⚠️  重要：请使用只读账户，勿使用管理员账户！"
    echo "       配置完成后，重新运行此脚本"
    exit 0
fi

# 创建 docker-compose.yml
echo "[配置] 创建 docker-compose.yml..."
cat > docker-compose.yml << EOF
version: '3.8'

services:
  ihomeguard:
    image: ${IMAGE_NAME}
    container_name: ihomeguard
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    ports:
      - "\${WEB_PORT:-8680}:8680"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8680/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
EOF

# 登录阿里云镜像仓库
echo ""
echo "[登录] 阿里云镜像仓库..."
echo "请输入阿里云镜像仓库密码："
docker login --username=EddyCheng ${REGISTRY}

# 拉取镜像并启动
echo ""
echo "[部署] 拉取镜像..."
docker compose pull

echo ""
echo "[部署] 启动服务..."
docker compose up -d

# 检查状态
echo ""
echo "=========================================="
echo "[完成] 部署成功!"
echo ""
echo "  访问地址: http://<服务器IP>:8680"
echo "  查看日志: cd $PROJECT_DIR && docker compose logs -f"
echo "  重启服务: cd $PROJECT_DIR && docker compose restart"
echo "  停止服务: cd $PROJECT_DIR && docker compose down"
echo "=========================================="
