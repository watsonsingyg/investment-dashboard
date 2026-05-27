"""Structured logging with file rotation and request tracking.

Usage:
    from reporter.logger import get_logger
    log = get_logger(__name__)
    log.info('server_started', port=8766, model='deepseek-v4-pro')
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings  # noqa: E402

# 全局 request ID（由 middleware 设置）
_request_id_ctx: dict = {}


def get_request_id() -> str:
    """获取当前请求的 trace ID。"""
    return _request_id_ctx.get("id", "")


def set_request_id(rid: Optional[str] = None) -> str:
    """设置当前请求的 trace ID，返回 ID。"""
    rid = rid or uuid.uuid4().hex[:12]
    _request_id_ctx["id"] = rid
    return rid


class StructuredLogger:
    """JSON-structured logger with file rotation and request tracking."""

    @staticmethod
    def _setup_file_handler(name: str, log_path: Path) -> logging.Handler:
        """配置 RotatingFileHandler：单文件 5MB，保留 5 个备份。"""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(log_path), maxBytes=5 * 1024 * 1024, backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(logging.INFO)
        fmt = logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",%(message)s}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(fmt)
        return handler

    def __init__(self, name: str):
        self._name = name
        self._py_logger = logging.getLogger(name)
        self._py_logger.setLevel(logging.DEBUG if settings.APP_DEBUG else logging.INFO)

        # 每个 logger 只添加一次 handler
        if not self._py_logger.handlers:
            # Console handler（开发用人类可读格式）
            console = logging.StreamHandler(sys.stdout)
            console.setLevel(logging.DEBUG)
            console_fmt = logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            console.setFormatter(console_fmt)
            self._py_logger.addHandler(console)

            # File handler（JSON 格式 + 轮转）
            main_log = settings.LOG_DIR / "app.log"
            error_log = settings.LOG_DIR / "error.log"

            fh = self._setup_file_handler(name, main_log)
            self._py_logger.addHandler(fh)

            # 错误日志单独一个文件
            eh = self._setup_file_handler(name, error_log)
            eh.setLevel(logging.ERROR)
            self._py_logger.addHandler(eh)

    def _emit(self, level: str, event: str, **kwargs: Any) -> None:
        rid = get_request_id()
        parts: list = [(f'"event":"{event}"')]
        if rid:
            parts.append(f'"req_id":"{rid}"')
        if kwargs:
            parts.append(
                ",".join(f'"{k}":{json.dumps(v, ensure_ascii=False, default=str)}' for k, v in kwargs.items())
            )
        message = ",".join(parts)
        getattr(self._py_logger, level)(message)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._emit("debug", event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._emit("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._emit("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._emit("error", event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        msg_parts = [f'"event":"{event}"']
        rid = get_request_id()
        if rid:
            msg_parts.append(f'"req_id":"{rid}"')
        if kwargs:
            msg_parts.append(
                ",".join(f'"{k}":{json.dumps(v, ensure_ascii=False, default=str)}' for k, v in kwargs.items())
            )
        self._py_logger.exception(",".join(msg_parts))


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)
