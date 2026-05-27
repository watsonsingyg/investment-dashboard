# ── Stage 1: 构建依赖 ─────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: 运行时 ───────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# 从 builder 复制全局安装的 Python 包（所有用户都能访问）
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY . .

# 入口脚本
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# 健康检查（使用环境变量 PORT，默认 8766）
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python3 -c "import os,urllib.request; port=os.environ.get('PORT','8766'); urllib.request.urlopen(f'http://localhost:{port}/api/health')" || exit 1

# 云部署：绑定所有网络接口（Railway/Render 等需要 0.0.0.0）
ENV APP_HOST=0.0.0.0

# 暴露端口（Railway 会通过 PORT 环境变量动态分配，这里仅作文档用途）
EXPOSE 8766

# 入口脚本（等待数据库 → 迁移 → 启动服务）
ENTRYPOINT ["/app/docker-entrypoint.sh"]
