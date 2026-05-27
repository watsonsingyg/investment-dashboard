#!/usr/bin/env python3
"""
server.py — Pipeline SaaS 启动入口。

用法:
    python3 server.py
    或
    ./start.sh
"""

from dotenv import load_dotenv
load_dotenv()

from reporter import create_app
from config import settings
from reporter.logger import get_logger

app = create_app()
log = get_logger("server")

if __name__ == "__main__":
    log.info("server_starting",
             host=settings.APP_HOST, port=settings.APP_PORT,
             model=settings.DEEPSEEK_MODEL,
             has_api_key=bool(settings.DEEPSEEK_API_KEY),
             has_skill_root=bool(settings.SKILL_ROOT))
    app.run(
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        debug=settings.APP_DEBUG,
        threaded=True,
    )
