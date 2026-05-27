"""
reporter/errors.py — 统一 API 错误响应工具。

所有 Blueprint 通过此模块返回一致的错误格式：

    {"error": "人类可读的错误描述"}

HTTP 状态码：400（请求错误）、401（未认证）、403（权限不足）、
404（不存在）、409（冲突）、429（限流）、500（服务端错误）。
"""

from flask import jsonify


def bad_request(msg: str):
    """400 — 请求参数或数据不合法。"""
    return jsonify({"error": msg}), 400


def unauthorized(msg: str = "未提供认证令牌"):
    """401 — 未认证或 token 无效。"""
    return jsonify({"error": msg}), 401


def forbidden(msg: str = "权限不足"):
    """403 — 已认证但无权限。"""
    return jsonify({"error": msg}), 403


def not_found(msg: str = "资源不存在"):
    """404 — 请求的资源不存在。"""
    return jsonify({"error": msg}), 404


def conflict(msg: str):
    """409 — 资源冲突（如重复创建）。"""
    return jsonify({"error": msg}), 409


def too_many_requests(msg: str = "请求过于频繁，请稍后再试"):
    """429 — 速率限制。"""
    return jsonify({"error": msg}), 429


def server_error(msg: str = "服务器内部错误"):
    """500 — 服务端异常。"""
    return jsonify({"error": msg}), 500
