"""
models/field_diff.py — 字段变更审计表。
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from .base import Base


class FieldDiff(Base):
    __tablename__ = "field_diffs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    changed_by = Column(Integer, ForeignKey("users.id"))
    ts = Column(DateTime, default=datetime.utcnow)
    field = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    week = Column(String(50))
    backup_path = Column(String(500))
