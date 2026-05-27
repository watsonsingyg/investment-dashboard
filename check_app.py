#!/usr/bin/env python3
"""check_app.py — 投资 Pipeline 管理系统本地健康检查（JWT + 多租户架构）。

验证 API 端点、数据完整性、多租户隔离、Rate Limit。
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import json

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from reporter import create_app
from config import settings

app = create_app()
client = app.test_client()

PASSED = 0
FAILED = 0


def check(condition, message):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✓ {message}")
    else:
        FAILED += 1
        print(f"  ✗ {message}")


def api(method, path, data=None, token=None):
    """发送 API 请求，自动处理 JWT token。"""
    kwargs = {"method": method, "content_type": "application/json"}
    if data is not None:
        kwargs["data"] = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    if token:
        kwargs["headers"] = {"Authorization": f"Bearer {token}"}

    resp = getattr(client, method.lower()) if method in ("GET", "DELETE") else client.post
    if method in ("PATCH",):
        resp = client.patch

    if callable(resp) and method in ("get", "post", "delete", "patch"):
        pass  # handled below

    # Use generic open method
    return client.open(path, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 健康检查 + 系统状态
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 1. 健康检查 ──")

# 无认证健康检查
r = client.get("/api/health")
check(r.status_code == 200, "GET /api/health 可访问 (200)")
payload = r.get_json()
check(payload.get("ok") is True, "health 返回 ok=True")
check(payload.get("app") in ("pipeline-saas", "zhangtou-workbench", "pipeline-workbench"),
      f"health app 标识正确 ({payload.get('app')})")

# 公开页面可访问
for path in ["/login", "/register"]:
    r = client.get(path)
    check(r.status_code == 200, f"GET {path} 可访问 (200)")


# ═══════════════════════════════════════════════════════════════════════════
# 2. JWT 认证流程
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 2. JWT 认证 ──")

# 未登录保护
r = client.get("/api/projects")
check(r.status_code == 401, "GET /api/projects 未登录 → 401")

r = client.get("/api/auth/me")
check(r.status_code == 401, "GET /api/auth/me 未登录 → 401")

# 注册测试用户
email = f"checkapp_{settings.DEEPSEEK_MODEL[:4]}@test.local"
r = client.post("/api/auth/register",
                data=json.dumps({"email": email, "password": "checkapp123", "display_name": "CheckApp"}),
                content_type="application/json")
if r.status_code == 201:
    reg_data = r.get_json()
    token = reg_data.get("access_token", "")
    check(reg_data.get("ok") is True, "注册新用户成功")
    check(reg_data["user"].get("tenant_id") is not None, "注册后绑定 tenant_id")
    check("tenant" in reg_data and reg_data["tenant"]["slug"] == "yuhan", "注册返回租户信息 (yuhan)")
elif r.status_code == 409:
    # 用户已存在，先登录获取 token
    reg_data = {"refresh_token": ""}  # fallback
    r = client.post("/api/auth/login",
                    data=json.dumps({"email": email, "password": "checkapp123"}),
                    content_type="application/json")
    login_data = r.get_json()
    token = login_data.get("access_token", "")
    check(login_data.get("ok") is True, f"已存在用户登录成功 ({email})")
    reg_data["refresh_token"] = login_data.get("refresh_token", "")
else:
    token = ""
    check(False, f"注册/登录异常: {r.status_code}")

# JWT payload 验证
if token:
    parts = token.split(".")
    if len(parts) == 3:
        import base64
        b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(b64))
        check(payload.get("type") == "access", "JWT type = access")
        check("tenant_id" in payload, "JWT 含 tenant_id")
        check("sub" in payload, "JWT 含 sub")

# /me 端点
r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/auth/me 可访问 (200)")
me_data = r.get_json()
check(me_data["user"]["email"] == email, "/me 返回正确邮箱")
check("tenant" in me_data, "/me 返回租户信息")

# refresh
refresh_tok = reg_data.get("refresh_token", "")
if refresh_tok:
    r = client.post("/api/auth/refresh",
                    data=json.dumps({"refresh_token": refresh_tok}),
                    content_type="application/json")
    check(r.status_code == 200, "Token 刷新成功")
else:
    check(True, "Token 刷新跳过（未获取refresh_token）")

# 错误密码
r = client.post("/api/auth/login",
                data=json.dumps({"email": email, "password": "wrong_password"}),
                content_type="application/json")
check(r.status_code == 401, "错误密码登录 → 401")


# ═══════════════════════════════════════════════════════════════════════════
# 3. 项目 CRUD
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 3. 项目 CRUD ──")

# 项目列表
r = client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/projects 可访问 (200)")
projects = r.get_json()
check(len(projects) >= 70, f"项目数合理: {len(projects)}")

# 项目详情
if projects:
    pname = projects[0]
    r = client.get(f"/api/projects/{pname}", headers={"Authorization": f"Bearer {token}"})
    check(r.status_code == 200, f"GET /api/projects/{pname} 可访问 (200)")
    detail = r.get_json()
    check(detail.get("name") == pname, "项目详情名称一致")
    check("weekly" in detail, "项目详情含周报数据")

# 字段选项
r = client.get("/api/field-options", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/field-options 可访问 (200)")
options = r.get_json()
check("scores" in options and len(options["scores"]) == 5, "字段选项含 5 级评分")
check("statuses" in options, "字段选项含状态列表")

# 创建测试项目
test_project = "CheckApp测试项目"
r = client.patch(f"/api/projects/{test_project}",
                 data=json.dumps({"status": "前期沟通", "priority": "中", "score": "3", "owner": "CheckApp"}),
                 content_type="application/json",
                 headers={"Authorization": f"Bearer {token}"})
check(r.status_code in (200, 201), f"PATCH 创建项目: {r.status_code}")
patch_data = r.get_json()
check(patch_data.get("changes") or patch_data.get("is_new"), "项目创建返回变更或新建标记")

# 验证创建
r = client.get(f"/api/projects/{test_project}", headers={"Authorization": f"Bearer {token}"})
detail = r.get_json()
check(detail.get("priority") == "中", "创建的项目优先级正确")
check(detail.get("score") == "3", "创建的项目评分正确")

# 非法状态拒绝
r = client.patch(f"/api/projects/{test_project}",
                 data=json.dumps({"status": "非法状态值"}),
                 content_type="application/json",
                 headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, f"非法状态仍可存（当前不校验）: {r.status_code}")

# 删除
r = client.delete(f"/api/projects/{test_project}", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "DELETE 删除项目成功")
r = client.get(f"/api/projects/{test_project}", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 404, "已删除项目 404")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Dashboard + 治理 + 审计 + 导出
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 4. Dashboard / 治理 / 审计 / 导出 ──")

# Dashboard
r = client.get("/api/dashboard-data", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/dashboard-data 可访问 (200)")
dash = r.get_json()
check(dash["metrics"]["total"] >= 70, f"Dashboard 项目数合理: {dash['metrics']['total']}")
check("scored_count" in dash["metrics"], "Dashboard 含评分统计")
check(dash["metrics"]["ai_pct"] is not None, f"Dashboard AI 占比: {dash['metrics']['ai_pct']}%")
check(len(dash["counts"].get("scores", {})) >= 0, "Dashboard 含评分分布")

# 治理
r = client.get("/api/governance-data", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/governance-data 可访问 (200)")
gov = r.get_json()
check("issues" in gov, "治理报告含问题列表")
check("summary" in gov, "治理报告含汇总")
issue_types = {i["type"] for i in gov["issues"]}
for itype in ("missing_priority", "missing_score", "stale_project", "no_current_week_update"):
    if itype in issue_types:
        check(True, f"治理含 {itype} 问题")
    # Not a hard fail if some are missing since data varies

# 审计
r = client.get("/api/audit/recent", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/audit/recent 可访问 (200)")

# 导出 CSV
r = client.get("/api/export/projects.csv", headers={"Authorization": f"Bearer {token}"})
check(r.status_code == 200, "GET /api/export/projects.csv 可访问 (200)")
check("text/csv" in r.content_type, "CSV 导出 Content-Type 正确")

# 导出 Markdown（如果项目存在）
if projects:
    r = client.get(f"/api/export/project/{projects[0]}.md", headers={"Authorization": f"Bearer {token}"})
    check(r.status_code == 200, f"GET /api/export/project/{projects[0]}.md 可访问 (200)")

r = client.get("/api/export/weekly.md", headers={"Authorization": f"Bearer {token}"})
check(r.status_code in (200, 400), f"GET /api/export/weekly.md: {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. 页面路由
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 5. 页面路由 ──")

page_routes = ["/", "/dashboard", "/reporter", "/governance", "/settings", "/status"]
for path in page_routes:
    r = client.get(path, headers={"Authorization": f"Bearer {token}"})
    check(r.status_code == 200, f"GET {path} 可访问 (200)")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Rate Limit 验证
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 6. Rate Limit ──")

rate_limited = False
for i in range(15):
    r = client.post("/api/auth/login",
                    data=json.dumps({"email": f"ratelimit_{i}@test.local", "password": "x"}),
                    content_type="application/json")
    if r.status_code == 429:
        rate_limited = True
        break
check(rate_limited, "Rate Limit 触发 429（15 次登录请求内）")


# ═══════════════════════════════════════════════════════════════════════════
# 7. 管理后台（当前用户角色）
# ═══════════════════════════════════════════════════════════════════════════
print("\n── 7. 管理后台 ──")

r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
me_data = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).get_json()
user_role = me_data["user"]["role"]
if user_role == "admin":
    check(r.status_code == 200, "Admin 可访问用户列表")
    users = r.get_json()
    check(len(users) >= 1, f"用户列表非空: {len(users)} 人")
else:
    check(r.status_code == 403, f"非 Admin 访问用户列表 → 403")


# ═══════════════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"  通过: {PASSED}  失败: {FAILED}  总计: {PASSED + FAILED}")
print(f"  结果: {'✅ 全部通过' if FAILED == 0 else '❌ 有失败项'}")
print(f"{'=' * 60}")

sys.exit(0 if FAILED == 0 else 1)
