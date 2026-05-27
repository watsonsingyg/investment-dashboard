# ── Stage 1: 构建依赖 ─────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（分层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: 运行时 ───────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 安装运行时系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# 从 builder 复制 Python 包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY . .

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash pipeline && \
    chown -R pipeline:pipeline /app
USER pipeline

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8766/api/health')" || exit 1

# 暴露端口
EXPOSE 8766

# 启动命令
CMD ["python3", "-u", "server.py"]
