#!/bin/bash
# ── Docker 入口脚本 ──────────────────────────────────────────────────
# 1. 等待数据库就绪
# 2. 运行 Alembic 迁移
# 3. 启动 Flask 应用
#
# Railway 会通过 PORT / DATABASE_URL 环境变量注入配置

set -e

echo "🚀 Pipeline SaaS — 容器启动中..."

# ── 等待数据库就绪 ──────────────────────────────────────────────────
if [ -n "$DATABASE_URL" ]; then
    echo "⏳ 等待数据库连接..."
    
    # 从 DATABASE_URL 解析 host 和 port
    # 支持格式: postgresql://user:pass@host:port/dbname
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_PORT=${DB_PORT:-5432}
    
    echo "   目标: ${DB_HOST}:${DB_PORT}"
    
    for i in $(seq 1 30); do
        if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$DB_HOST', $DB_PORT))
    s.close()
    print('OK')
except:
    pass
" 2>/dev/null | grep -q OK; then
            echo "✅ 数据库已就绪"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "❌ 数据库连接超时，继续启动（应用会重试）"
        fi
        sleep 2
    done
fi

# ── 运行数据库迁移 ──────────────────────────────────────────────────
echo "📦 运行数据库迁移..."
python3 -m alembic upgrade head || {
    echo "⚠️  迁移失败（可能是全新数据库），使用 create_all 兜底..."
    python3 -c "from models.base import init_db; init_db(); print('✅ 表创建完成')"
}

# ── 启动应用 ────────────────────────────────────────────────────────
echo "🌟 启动 Flask 应用..."
exec python3 -u server.py
