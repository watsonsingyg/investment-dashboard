"""
reporter/ — 投资 Pipeline 管理系统。

用法:
    from reporter import create_app
    app = create_app()
"""

from flask import Flask, g
from flask_cors import CORS  # 新增 CORS 支持
from config import settings
from models.base import init_db, SessionLocal
from reporter.middleware.tenant import resolve_tenant
from reporter.middleware.rate_limit import limiter, register_rate_limit_handlers


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = settings.FLASK_SECRET
    app.config.update(
        MAX_CONTENT_LENGTH=settings.MAX_CONTENT_LENGTH_MB * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    # ── CORS 配置 ──────────────────────────────────────────────────────
    # 允许前端域名访问 API（根据需要调整）
    # 生产环境建议明确指定允许的域名
    CORS(app, 
         supports_credentials=True,  # 允许携带 cookie/token
         origins="*",  # 允许所有来源访问
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    # 初始化数据库
    init_db()

    # ── 中间件 ────────────────────────────────────────────────────────────
    # 全局错误处理器（JSON 格式 — 仅处理真正的 500）
    from reporter.errors import server_error

    @app.errorhandler(500)
    def _handle_500(e):
        return server_error()

    # 速率限制
    limiter.init_app(app)
    register_rate_limit_handlers(app)

    # 租户解析（在 auth 之前，以便公开端点也能有默认租户）
    app.before_request(resolve_tenant)

    # Request ID 追踪（每个请求一个唯一 ID）
    from reporter.logger import set_request_id

    @app.before_request
    def _assign_request_id():
        set_request_id()

    # 数据库会话管理
    @app.before_request
    def _open_db():
        g.db = SessionLocal()

    @app.teardown_appcontext
    def _close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # ── 注册蓝图 ──────────────────────────────────────────────────────────
    from reporter.blueprints.auth import auth_bp
    from reporter.blueprints.projects import projects_bp
    from reporter.blueprints.dashboard import dashboard_bp
    from reporter.blueprints.governance import governance_bp
    from reporter.blueprints.audit import audit_bp
    from reporter.blueprints.export import export_bp
    from reporter.blueprints.ai import ai_bp
    from reporter.blueprints.system import system_bp
    from reporter.blueprints.pages import pages_bp
    from reporter.blueprints.settings import settings_bp
    from reporter.blueprints.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(governance_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_bp)

    # ── Swagger API 文档（可选）────────────────────────────────────────
    try:
        from flasgger import Swagger
        Swagger(app, config={
            "headers": [],
            "specs": [{
                "endpoint": "apispec",
                "route": "/apispec.json",
            }],
            "static_url_path": "/flasgger_static",
            "swagger_ui": True,
            "specs_route": "/api/docs/",
            "title": "Pipeline SaaS API",
            "description": "投资 Pipeline 管理系统 — REST API 文档",
            "version": "1.0.0",
            "securityDefinitions": {
                "Bearer": {
                    "type": "apiKey",
                    "name": "Authorization",
                    "in": "header",
                    "description": "JWT token: Bearer <token>"
                }
            },
        })
    except ImportError:
        app.logger.info("flasgger not installed, skipping Swagger docs")

    return app
