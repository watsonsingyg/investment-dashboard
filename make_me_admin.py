"""
make_me_admin.py — 将指定用户设为 admin。

用法（在 Railway Shell 或本地运行）：
    # 方式 1：通过环境变量指定邮箱（推荐）
    EMAIL=your@email.com python3 make_me_admin.py

    # 方式 2：修改脚本内的 TARGET_EMAIL 变量
"""
import os
import sys

# ── 要设为 admin 的用户邮箱 ──────────────────────────
# 优先读环境变量 EMAIL，否则修改下面这行：
TARGET_EMAIL = os.environ.get("EMAIL", "your@email.com")


def main():
    from dotenv import load_dotenv
    load_dotenv()

    from config import settings
    from models.user import User
    from models.base import SessionLocal, init_db

    # 确保表存在
    init_db()

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=TARGET_EMAIL).first()
        if not user:
            print(f"❌ 找不到用户：{TARGET_EMAIL}")
            print("已有用户：")
            for u in db.query(User).all():
                print(f"  - {u.email}  (role={u.role})")
            sys.exit(1)

        old_role = user.role
        user.role = "admin"
        db.commit()
        print(f"✅ 已将 {user.email} 角色从 '{old_role}' 改为 'admin'")
        print(f"   用户 ID: {user.id}, 启用状态: {user.is_active}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
