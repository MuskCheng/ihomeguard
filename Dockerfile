FROM python:3.12-slim

# 版本信息（默认读取 VERSION 文件，构建时可通过 --build-arg 覆盖）
ARG VERSION=dev
ARG BUILD_DATE

LABEL maintainer="CXF"
LABEL description="iHomeGuard - 爱快家庭网络卫士"
LABEL version=${VERSION}
LABEL build-date=${BUILD_DATE}

WORKDIR /app

# 安装 curl（用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目文件
COPY . .

# 创建数据目录
RUN mkdir -p /app/data /app/config

# 暴露端口
EXPOSE 8680

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8680/api/health || exit 1

# 启动命令（-u 禁用缓冲，确保日志实时输出）
CMD ["python", "-u", "app.py"]