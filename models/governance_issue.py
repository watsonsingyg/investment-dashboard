"""
models/governance_issue.py — 治理问题表。
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from .base import Base


class GovernanceIssue(Base):
    __tablename__ = "governance_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    issue_key = Column(String(200), unique=True)
    project_name = Column(String(200))
    issue_type = Column(String(50))
    severity = Column(String(20))
    reason = Column(Text)
    suggestion = Column(Text)
    fixable = Column(Boolean, default=False)
    field = Column(String(50))
    issue_state = Column(String(20), default="active")
    ignore_note = Column(Text)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
