"""Alembic 环境配置 — 使用项目 config.py 的 DATABASE_URL 和 models 元数据。"""

import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 将项目根目录加入 sys.path，确保可以导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config import settings
from models.base import Base

# 导入所有模型以注册到 Base.metadata（autogenerate 需要）
import models  # noqa: F401

# Alembic Config 对象
config = context.config

# 从项目配置设置数据库 URL（代替 alembic.ini 硬编码）
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 所有模型的元数据，autogenerate 用
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而非直接执行。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
