#!/usr/bin/env python3
"""
migrate_to_postgres.py — Excel → 数据库数据迁移脚本。

将现有 周报 database.xlsx 中的 74 个项目、146 周数据迁移到数据库。

用法:
    python migrate_to_postgres.py
    python migrate_to_postgres.py --excel "周报 database.xlsx" --tenant-name "语涵"

注意: DB backend 由 config.py 的 DATABASE_URL 决定（开发: SQLite, 生产: PostgreSQL）。
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from config import settings
from models.base import init_db, SessionLocal
from models.tenant import Tenant
from models.user import User
from models.project import Project
from models.weekly_entry import WeeklyEntry
from models.field_diff import FieldDiff
from models.operation_log import OperationLog
from reporter.dashboard_data import parse_excel
from reporter.excel_store import find_excel
from reporter.jwt_utils import hash_password
from reporter.summary_cache import clean_text


def migrate(args):
    """主迁移流程。"""
    report_dir = settings.REPORT_DIR
    excel_path = args.excel or str(find_excel(report_dir))
    tenant_name = args.tenant_name or "default"
    admin_email = args.admin_email or os.environ.get("MIGRATE_ADMIN_EMAIL", "admin@example.com")
    admin_password = args.admin_password or os.environ.get("MIGRATE_ADMIN_PASSWORD", "admin123")

    print(f"数据源: {excel_path}")
    print(f"租户名称: {tenant_name}")
    print(f"管理员: {admin_email}")
    print("=" * 60)

    # 1. 解析 Excel
    print("1. 解析 Excel 文件...")
    data = parse_excel(excel_path)
    projects_raw = data.get("projects", [])
    print(f"   解析到 {len(projects_raw)} 个项目")

    # 2. 初始化数据库
    print("2. 初始化数据库...")
    init_db()
    db = SessionLocal()

    try:
        # 3. 创建租户
        print("3. 创建租户...")
        import re

        # 生成 slug：英文/数字直接保留，中文保持原样（转拼音太复杂，直接用输入的前几个字符）
        slug_raw = tenant_name.lower().strip()
        slug = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '-', slug_raw).strip('-')
        if not slug or slug == slug_raw:
            # 中文名：用拼音首字母或者直接用 "team-{hash}"
            import hashlib
            slug = f"team-{hashlib.md5(tenant_name.encode()).hexdigest()[:8]}"

        # 确保 slug 唯一
        base_slug = slug
        counter = 1
        while db.query(Tenant).filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        tenant = Tenant(name=tenant_name, slug=slug)
        db.add(tenant)
        db.flush()
        print(f"   已创建租户: {tenant.name} (slug={tenant.slug}, id={tenant.id})")

        # 4. 创建管理员用户
        print("4. 创建管理员用户...")
        user = db.query(User).filter_by(email=admin_email).first()
        if not user:
            user = User(
                email=admin_email,
                password_hash=hash_password(admin_password),
                display_name="管理员",
                role="admin",
                tenant_id=tenant.id,
            )
            db.add(user)
            db.flush()
            print(f"   已创建管理员: {user.email} (id={user.id})")
        else:
            print(f"   管理员已存在: {user.email} (id={user.id})")

        db.commit()

        # 5. 迁移项目
        print("5. 迁移项目数据...")
        project_count = 0
        entry_count = 0
        skip_count = 0

        for p_data in projects_raw:
            name = p_data.get("name", "").strip()
            if not name or name == "-":
                skip_count += 1
                continue

            # 检查是否已存在
            existing = db.query(Project).filter(
                Project.tenant_id == tenant.id,
                Project.name == name,
            ).first()

            if existing and not args.overwrite:
                skip_count += 1
                continue

            if existing and args.overwrite:
                # 删除已有周报
                db.query(WeeklyEntry).filter(WeeklyEntry.project_id == existing.id).delete()
                db.flush()
            else:
                existing = Project(tenant_id=tenant.id, name=name)
                db.add(existing)
                db.flush()

            # 更新字段
            existing.biz_scope = p_data.get("biz_scope", "")
            existing.industry = p_data.get("industry", "")
            existing.category = p_data.get("category", "")
            existing.owner = p_data.get("owner", "")
            existing.status = p_data.get("status", "")
            existing.status_raw = p_data.get("status_raw", "")
            existing.priority = p_data.get("priority", "")
            existing.score = str(p_data.get("score", "") or "")
            existing.is_ai = p_data.get("is_ai", False)
            existing.last_active = p_data.get("last_active", "")
            existing.first_active = p_data.get("first_active", "")
            existing.latest_content = p_data.get("latest_content", "")
            existing.latest_label = p_data.get("latest_label", "")

            # 迁移周报
            weekly = p_data.get("weekly", {})
            for week, content in weekly.items():
                content_val = (content or "").strip()
                if content_val:
                    short = clean_text(content_val)[:80] if callable(clean_text) else ""
                    entry = WeeklyEntry(
                        tenant_id=tenant.id,
                        project_id=existing.id,
                        week=week,
                        content=content_val,
                        short=short[:100],
                    )
                    db.add(entry)
                    entry_count += 1

            db.flush()
            project_count += 1

            if project_count % 20 == 0:
                db.commit()
                print(f"   已迁移 {project_count}/{len(projects_raw)} 个项目...")

        db.commit()
        print(f"   完成: {project_count} 个项目, {entry_count} 条周报记录, {skip_count} 个跳过")

        # 6. 迁移变更审计（可选）
        if args.migrate_diffs:
            print("6. 迁移变更审计...")
            try:
                _migrate_shadow_diffs(db, tenant.id, report_dir)
            except Exception as e:
                print(f"   警告: 迁移变更审计失败 - {e}")

        # 7. 迁移操作日志（可选）
        if args.migrate_logs:
            print("7. 迁移操作日志...")
            try:
                _migrate_operation_logs(db, tenant.id, report_dir)
            except Exception as e:
                print(f"   警告: 迁移操作日志失败 - {e}")

        # 8. 汇总
        print("=" * 60)
        final_count = db.query(Project).filter(
            Project.tenant_id == tenant.id,
            Project.deleted_at.is_(None),
        ).count()
        entry_count = db.query(WeeklyEntry).filter(
            WeeklyEntry.tenant_id == tenant.id,
        ).count()
        print(f"迁移完成!")
        print(f"  租户: {tenant.name} ({tenant.slug})")
        print(f"  项目: {final_count}")
        print(f"  周报: {entry_count}")
        print(f"  管理员: {admin_email}")
        print(f"  DB: {settings.DATABASE_URL.split('://')[0]}")

    except Exception as e:
        db.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        db.close()


def _migrate_shadow_diffs(db, tenant_id, report_dir):
    """从 SQLite 影子库迁移 field_diffs。"""
    import sqlite3
    shadow_db = report_dir / "pipeline_shadow.db"
    if not shadow_db.exists():
        print("   影子库不存在，跳过")
        return

    conn = sqlite3.connect(str(shadow_db))
    rows = conn.execute("SELECT ts, project, week, field, old_value, new_value FROM field_diffs").fetchall()
    conn.close()

    count = 0
    for ts, project, week, field, old_val, new_val in rows:
        diff = FieldDiff(
            tenant_id=tenant_id,
            field=field,
            old_value=old_val,
            new_value=new_val,
            week=week,
            ts=datetime.fromisoformat(ts) if ts else datetime.utcnow(),
        )
        db.add(diff)
        count += 1

    db.commit()
    print(f"   迁移了 {count} 条变更记录")


def _migrate_operation_logs(db, tenant_id, report_dir):
    """从 JSONL 文件迁移操作日志。"""
    import json
    log_path = report_dir / "logs" / "operations.jsonl"
    if not log_path.exists():
        print("   操作日志文件不存在，跳过")
        return

    count = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            log = OperationLog(
                tenant_id=tenant_id,
                ts=datetime.fromisoformat(record.get("ts")) if record.get("ts") else datetime.utcnow(),
                event=record.get("event", ""),
                project=record.get("project", ""),
                details=json.dumps(record, ensure_ascii=False),
            )
            db.add(log)
            count += 1
        except Exception:
            pass

    db.commit()
    print(f"   迁移了 {count} 条操作日志")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Excel → DB 数据迁移")
    parser.add_argument("--excel", help="Excel 文件路径（默认自动查找）")
    parser.add_argument("--tenant-name", default="default", help="租户名称")
    parser.add_argument("--admin-email", help="管理员邮箱")
    parser.add_argument("--admin-password", help="管理员密码")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有项目")
    parser.add_argument("--migrate-diffs", action="store_true", help="迁移变更审计记录")
    parser.add_argument("--migrate-logs", action="store_true", help="迁移操作日志")

    args = parser.parse_args()
    migrate(args)
