"""
models/base.py — SQLAlchemy Base + Engine + Session 管理。

所有 ORM 模型都继承此 Base。init_db() 自动建表。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    """返回一个数据库会话（用于 FastAPI 依赖注入，Flask 用 g.db）。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表。"""
    Base.metadata.create_all(bind=engine)
