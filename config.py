"""
集中配置管理 — 所有可配置项从环境变量读取，无硬编码路径。

用法：
    from config import settings
    print(settings.REPORT_DIR)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    """应用全局配置，所有字段有默认值，均可通过环境变量覆盖。"""

    # ── 路径 ────────────────────────────────────────────────────────────────
    # 项目根目录（包含 reporter/、周报 database.xlsx 等）
    REPORT_DIR: Path = field(default_factory=lambda: Path(os.environ.get(
        'REPORT_DIR',
        str(Path(__file__).parent)  # 默认 = config.py 所在目录
    )))

    # Skill 文件所在目录（AI 分析框架 .skill 压缩包）
    SKILL_ROOT: Optional[Path] = field(default_factory=lambda: (
        Path(p) if (p := os.environ.get('SKILL_ROOT', '')) else None
    ))

    # ── 服务 ────────────────────────────────────────────────────────────────
    APP_HOST: str = os.environ.get('APP_HOST', '127.0.0.1')
    APP_PORT: int = int(os.environ.get('PORT', '8766'))
    APP_DEBUG: bool = os.environ.get('APP_DEBUG', 'false').lower() == 'true'

    # ── 安全 ────────────────────────────────────────────────────────────────
    FLASK_SECRET: str = os.environ.get(
        'FLASK_SECRET',
        'change-me-in-production-' + os.urandom(8).hex()
    )
    PORTAL_PASSWORD: str = os.environ.get('PORTAL_PASSWORD', '')
    LOGIN_COOLDOWN_SECONDS: int = int(os.environ.get('LOGIN_COOLDOWN_SECONDS', '20'))
    MAX_CONTENT_LENGTH_MB: int = int(os.environ.get('MAX_CONTENT_LENGTH_MB', '25'))

    # ── AI ──────────────────────────────────────────────────────────────────
    DEEPSEEK_API_KEY: str = os.environ.get('DEEPSEEK_API_KEY', '')
    DEEPSEEK_MODEL: str = os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-pro')
    DEEPSEEK_BASE_URL: str = os.environ.get(
        'DEEPSEEK_BASE_URL', 'https://api.deepseek.com'
    )
    TAVILY_API_KEY: str = os.environ.get('TAVILY_API_KEY', '')
    TAVILY_BASE_URL: str = os.environ.get(
        'TAVILY_BASE_URL', 'https://api.tavily.com'
    )
    ANTHROPIC_API_KEY: str = os.environ.get('ANTHROPIC_API_KEY', '')

    # ── 备份 ────────────────────────────────────────────────────────────────
    MAX_BACKUPS: int = int(os.environ.get('MAX_BACKUPS', '30'))

    # ── 治理 ────────────────────────────────────────────────────────────────
    STALE_WEEKS_THRESHOLD: int = int(os.environ.get('STALE_WEEKS_THRESHOLD', '8'))

    # ── 数据库 ──────────────────────────────────────────────────────────────
    # 开发：SQLite（无需安装），生产：PostgreSQL（修改环境变量即可）
    # 生产示例: postgresql://pipeline:pipeline@localhost:5432/pipeline_saas
    DATABASE_URL: str = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + str(Path(os.environ.get('REPORT_DIR', str(Path(__file__).parent))) / 'pipeline_saas.db')
    )

    # ── JWT ─────────────────────────────────────────────────────────────────
    JWT_SECRET: str = os.environ.get('JWT_SECRET', os.urandom(32).hex())
    JWT_ALGORITHM: str = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.environ.get('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '60')
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(
        os.environ.get('JWT_REFRESH_TOKEN_EXPIRE_DAYS', '30')
    )

    # ── 速率限制 ─────────────────────────────────────────────────────────
    RATE_LIMIT_GLOBAL: str = os.environ.get('RATE_LIMIT_GLOBAL', '200 per minute')
    RATE_LIMIT_AUTH: str = os.environ.get('RATE_LIMIT_AUTH', '10 per minute')
    RATE_LIMIT_AI: str = os.environ.get('RATE_LIMIT_AI', '30 per minute')

    @property
    def LOG_DIR(self) -> Path:
        return self.REPORT_DIR / 'logs'

    @property
    def BACKUP_DIR(self) -> Path:
        return self.REPORT_DIR / 'backups'

    @property
    def DASHBOARD_FILE(self) -> Path:
        return self.REPORT_DIR / 'dashboard.html'

    @property
    def SHADOW_DB(self) -> Path:
        return self.REPORT_DIR / 'pipeline_shadow.db'

    @property
    def OPERATIONS_LOG(self) -> Path:
        return self.LOG_DIR / 'operations.jsonl'

    @property
    def SERVER_LOG(self) -> Path:
        return self.LOG_DIR / 'server.log'

    @property
    def GOVERNANCE_OVERRIDES(self) -> Path:
        return self.LOG_DIR / 'governance_overrides.json'

    @property
    def EXCEL_LOCK(self) -> Path:
        return self.REPORT_DIR / '.excel.lock'

    @property
    def SUMMARIES_CACHE(self) -> Path:
        return self.REPORT_DIR / '.summaries_cache.json'

    def ensure_dirs(self) -> None:
        """确保所有需要的目录存在。"""
        self.LOG_DIR.mkdir(exist_ok=True)
        self.BACKUP_DIR.mkdir(exist_ok=True)


# 单例
settings = Settings()
