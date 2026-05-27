# Pipeline SaaS — Railway 云部署 Dockerfile
# 单阶段精简构建，避免 OOM
# Build: 2026-05-27-15-12 (force rebuild)

FROM python:3.11-slim

WORKDIR /app

# 强制重新构建（Railway Docker 缓存）
ARG CACHEBUST=2

# 安装运行时依赖（libpq5 用于 PostgreSQL）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# 复制依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# 复制应用代码
COPY . .

# 入口脚本
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python3 -c "import os,urllib.request; port=os.environ.get('PORT','8766'); urllib.request.urlopen(f'http://localhost:{port}/api/health')" || exit 1

# 云部署：绑定所有网络接口
ENV APP_HOST=0.0.0.0

# 暴露端口
EXPOSE 8766

ENTRYPOINT ["/app/docker-entrypoint.sh"]
