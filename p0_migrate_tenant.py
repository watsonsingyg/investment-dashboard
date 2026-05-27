#!/usr/bin/env python3
"""
p0_migrate_tenant.py — P0 数据库迁移脚本。

将现有 SQLite 数据库从单租户升级为多租户架构：
1. 创建 tenants 表
2. 插入默认租户
3. 给所有表添加 tenant_id 列
4. 回填已有数据的 tenant_id
5. 重建 projects 唯一约束为 (tenant_id, name)

用法:
    python3 p0_migrate_tenant.py
    python3 p0_migrate_tenant.py --dry-run  # 仅打印 SQL，不执行
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# 数据库文件路径（可通过 --db 参数覆盖）
_DB_PATH = Path(__file__).parent / "pipeline_saas.db"

# 默认租户信息
DEFAULT_TENANT = {
    "name": "语涵",
    "slug": "yuhan",
    "is_active": 1,
}


def run_migration(db_path, dry_run=False):
    print(f"数据库: {db_path}")
    print(f"模式: {'DRY RUN (仅打印SQL)' if dry_run else 'EXECUTE'}")
    print("=" * 60)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = OFF")

    # ── Step 0: 检查表是否存在 ────────────────────────────────────────────
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    print(f"现有表: {tables}")

    # ── Step 1: 创建 tenants 表 ──────────────────────────────────────────
    sql = """
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) UNIQUE NOT NULL,
            slug VARCHAR(50) UNIQUE NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    print(f"\n[1] 创建 tenants 表...")
    print(f"    SQL: {sql.strip()}")
    if not dry_run:
        conn.execute(sql)
        print("    ✓ 已创建")
    else:
        print("    (dry run, 跳过)")

    # ── Step 2: 插入默认租户 ──────────────────────────────────────────────
    existing = conn.execute("SELECT id, name, slug FROM tenants").fetchall()
    if existing:
        print(f"\n[2] 租户已存在: {existing}")
        tenant_id = existing[0][0]
    else:
        now = datetime.utcnow().isoformat()
        sql = """
            INSERT INTO tenants (name, slug, is_active, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
        """
        print(f"\n[2] 插入默认租户: {DEFAULT_TENANT['name']} (slug={DEFAULT_TENANT['slug']})")
        print(f"    SQL: INSERT INTO tenants(name, slug) VALUES('{DEFAULT_TENANT['name']}', '{DEFAULT_TENANT['slug']}')")
        if not dry_run:
            conn.execute(sql, (DEFAULT_TENANT["name"], DEFAULT_TENANT["slug"], now, now))
            conn.commit()
            tenant_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            print(f"    ✓ 已创建, tenant_id={tenant_id}")
        else:
            tenant_id = 1
            print(f"    (dry run, 假设 tenant_id={tenant_id})")

    # ── Step 3: 给各表加 tenant_id 列 ─────────────────────────────────────
    columns_to_add = {
        "users": "tenant_id INTEGER REFERENCES tenants(id)",
        "projects": "tenant_id INTEGER REFERENCES tenants(id)",
        "weekly_entries": "tenant_id INTEGER REFERENCES tenants(id)",
        "field_diffs": "tenant_id INTEGER REFERENCES tenants(id)",
        "operation_logs": "tenant_id INTEGER REFERENCES tenants(id)",
        "governance_issues": "tenant_id INTEGER REFERENCES tenants(id)",
    }

    for table, col_def in columns_to_add.items():
        if table not in tables:
            print(f"\n  表 {table} 不存在，跳过")
            continue

        # 检查列是否已存在
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "tenant_id" in cols:
            print(f"\n  {table}.tenant_id 已存在，跳过")
            continue

        sql = f"ALTER TABLE {table} ADD COLUMN {col_def}"
        print(f"\n  ALTER TABLE {table} ADD COLUMN tenant_id...")
        print(f"    SQL: {sql}")
        if not dry_run:
            conn.execute(sql)
            print(f"    ✓ 已添加")

    # ── Step 4: 回填 tenant_id ────────────────────────────────────────────
    if not dry_run:
        for table in columns_to_add:
            if table not in tables:
                continue
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL"
            ).fetchone()[0]
            if count > 0:
                conn.execute(f"UPDATE {table} SET tenant_id = ? WHERE tenant_id IS NULL", (tenant_id,))
                print(f"\n  UPDATE {table} SET tenant_id={tenant_id} → {count} 行")
            else:
                print(f"\n  {table}: 无需回填")

        conn.commit()

    # ── Step 5: 重建 projects 唯一约束 ────────────────────────────────────
    # SQLite 不支持直接 DROP CONSTRAINT，需要重建表
    # 策略：创建新表 → 迁移数据 → 重命名
    print(f"\n[5] 重建 projects 唯一约束...")

    if not dry_run:
        # 获取现有 projects 列
        cols = [c for c in conn.execute("PRAGMA table_info(projects)").fetchall()]
        col_names = [c[1] for c in cols]

        # 创建新表
        create_new = f"""
            CREATE TABLE projects_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER REFERENCES tenants(id),
                name VARCHAR(200) NOT NULL,
                biz_scope VARCHAR(200),
                industry VARCHAR(200),
                category VARCHAR(100),
                owner VARCHAR(100),
                status VARCHAR(50),
                status_raw VARCHAR(50),
                priority VARCHAR(10),
                score VARCHAR(5),
                is_ai BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 0,
                is_new BOOLEAN DEFAULT 0,
                last_active VARCHAR(50),
                first_active VARCHAR(50),
                latest_content TEXT,
                latest_label VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME,
                UNIQUE(tenant_id, name)
            )
        """
        conn.execute("DROP TABLE IF EXISTS projects_new")
        conn.execute(create_new)

        # 迁移数据
        cols_str = ", ".join(col_names)
        conn.execute(f"INSERT INTO projects_new ({cols_str}) SELECT {cols_str} FROM projects")
        count = conn.execute("SELECT COUNT(*) FROM projects_new").fetchone()[0]
        print(f"    ✓ 迁移 {count} 行到 projects_new")

        # 替换表
        conn.execute("DROP TABLE projects")
        conn.execute("ALTER TABLE projects_new RENAME TO projects")

        # 创建索引
        conn.execute("CREATE INDEX IF NOT EXISTS ix_projects_tenant_id ON projects(tenant_id)")

        # 如果有其他表的 FK 指向 projects，也需要重建（但 SQLite FK 默认不强制）
        # weekly_entries.project_id 和 field_diffs.project_id 仍指向旧的 projects，但表已重建
        # SQLite 的 FK 引用在 ALTER TABLE 后可能失效，但由于 FK enforcement 默认关闭，不影响查询
        print(f"    ✓ 唯一约束已更新为 (tenant_id, name)")

    conn.commit()

    # ── Step 6: 创建索引 ──────────────────────────────────────────────────
    for table in columns_to_add:
        if table in tables:
            idx_name = f"ix_{table}_tenant_id"
            try:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}(tenant_id)")
            except Exception:
                pass

    # ── 验证 ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("验证结果:")
    for table in columns_to_add:
        if table not in tables:
            continue
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        has_tid = "tenant_id" in cols
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        tid_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()[0]
        status = "✓" if has_tid and total == tid_count else "✗"
        print(f"  {status} {table}: tenant_id={has_tid}, {tid_count}/{total} 行已绑定")

    conn.close()

    if not dry_run:
        print(f"\n✅ 迁移完成！所有数据已绑定到租户 {DEFAULT_TENANT['name']} (id={tenant_id})")
    else:
        print(f"\n📋 DRY RUN 完成，未做任何修改。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P0 多租户数据库迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 SQL，不执行")
    parser.add_argument("--db", default=str(_DB_PATH), help="数据库文件路径")
    args = parser.parse_args()

    db_path = Path(args.db)

    if not db_path.exists():
        print(f"错误: 数据库文件不存在: {db_path}")
        sys.exit(1)

    run_migration(db_path, dry_run=args.dry_run)
