"""
models/weekly_entry.py — 周报条目表。
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base


class WeeklyEntry(Base):
    __tablename__ = "weekly_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    week = Column(String(50), nullable=False)
    content = Column(Text)
    short = Column(String(100))
    medium = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "week", name="uq_project_week"),
    )

    project = relationship("Project", back_populates="weekly_entries")
