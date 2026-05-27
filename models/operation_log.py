"""
models/operation_log.py — 操作日志表。
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from .base import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    ts = Column(DateTime, default=datetime.utcnow)
    event = Column(String(50))
    project = Column(String(200))
    details = Column(Text)
