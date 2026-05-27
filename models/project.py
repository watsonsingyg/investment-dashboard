"""
models/project.py — 项目表（核心实体）。
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    biz_scope = Column(String(200))
    industry = Column(String(200))
    category = Column(String(100))
    owner = Column(String(100))
    status = Column(String(50))
    status_raw = Column(String(50))
    priority = Column(String(10))
    score = Column(String(5))
    is_ai = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)
    is_new = Column(Boolean, default=False)
    last_active = Column(String(50))
    first_active = Column(String(50))
    latest_content = Column(Text)
    latest_label = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_project"),
    )

    # 关系
    tenant = relationship("Tenant", back_populates="projects")
    weekly_entries = relationship("WeeklyEntry", back_populates="project")
