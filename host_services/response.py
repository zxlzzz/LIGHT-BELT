"""
统一响应包装，对应文档第 4 节的 JSON envelope。
所有 router 通过这里返回，保证格式一致。
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from .auth_manager import get_request_id


def ok(request: Request, data: dict) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "request_id": get_request_id(request),
        "data": data,
    })


def error(request: Request, code: str, message: str,
          status_code: int = 400, details: dict | None = None) -> JSONResponse:
    body: dict = {
        "ok": False,
        "request_id": get_request_id(request),
        "error": {"code": code, "message": message},
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status_code)


# ── 常用错误快捷方法 ──

def unauthorized(request: Request, expired: bool = False) -> JSONResponse:
    if expired:
        return error(request, "TOKEN_EXPIRED",
                     "Access token has expired", status_code=401)
    return error(request, "UNAUTHORIZED",
                 "Missing or invalid token", status_code=401)


def invalid_argument(request: Request, message: str,
                     details: dict | None = None) -> JSONResponse:
    return error(request, "INVALID_ARGUMENT", message,
                 status_code=400, details=details)


def not_found(request: Request, message: str) -> JSONResponse:
    return error(request, "NOT_FOUND", message, status_code=404)
