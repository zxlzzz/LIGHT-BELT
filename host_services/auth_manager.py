"""
轻量认证模块：JWT 签发 / 校验 / 刷新，ws-ticket 管理。
相当于 Spring Security 的一个极简版。
"""

import time
import uuid
import jwt
from fastapi import Request
from .config import (
    JWT_SECRET, JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    WS_TICKET_EXPIRE_SECONDS,
)

# ── 内存存储（生产可换 Redis） ──
_refresh_tokens: dict[str, dict] = {}          # refresh_token -> {client_id, scope, ...}
_ws_tickets: dict[str, dict] = {}              # ticket -> {session_id, subscribe, expires_at}

DEFAULT_SCOPE = ["state:read", "playback:write", "lights:write",
                 "effects:write", "audio:write", "scenes:write"]


def _now() -> int:
    return int(time.time())


# ────────── Access Token ──────────

def create_access_token(client_id: str, scope: list[str]) -> tuple[str, int]:
    """返回 (token, expires_in)"""
    exp = _now() + ACCESS_TOKEN_EXPIRE_SECONDS
    payload = {"sub": client_id, "scope": scope, "exp": exp, "type": "access"}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, ACCESS_TOKEN_EXPIRE_SECONDS


def verify_access_token(token: str) -> dict | None:
    """校验成功返回 payload，失败返回 None"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def is_token_expired(token: str) -> bool:
    """区分 '过期' 和 '无效'"""
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return False
    except jwt.ExpiredSignatureError:
        return True
    except jwt.InvalidTokenError:
        return False


# ────────── Refresh Token ──────────

def create_refresh_token(client_id: str, scope: list[str]) -> str:
    token = f"rt_{uuid.uuid4().hex[:16]}"
    _refresh_tokens[token] = {
        "client_id": client_id,
        "scope": scope,
        "expires_at": _now() + REFRESH_TOKEN_EXPIRE_SECONDS,
    }
    return token


def consume_refresh_token(token: str) -> dict | None:
    """一次性消费，返回 {client_id, scope} 或 None"""
    info = _refresh_tokens.pop(token, None)
    if info is None:
        return None
    if _now() > info["expires_at"]:
        return None
    return info


# ────────── Token Pair 便捷方法 ──────────

def issue_token_pair(client_id: str) -> dict:
    scope = DEFAULT_SCOPE
    access, expires_in = create_access_token(client_id, scope)
    refresh = create_refresh_token(client_id, scope)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": scope,
    }


# ────────── WS Ticket ──────────

def create_ws_ticket(subscribe: list[str], host: str = "0.0.0.0:8443") -> dict:
    ticket = f"wst_{uuid.uuid4().hex[:16]}"
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    _ws_tickets[ticket] = {
        "session_id": session_id,
        "subscribe": subscribe,
        "expires_at": _now() + WS_TICKET_EXPIRE_SECONDS,
    }
    return {
        "ws_ticket": ticket,
        "session_id": session_id,
        "expires_in": WS_TICKET_EXPIRE_SECONDS,
        "ws_url": f"ws://{host}/ws?ticket={ticket}",
    }


def consume_ws_ticket(ticket: str) -> dict | None:
    info = _ws_tickets.pop(ticket, None)
    if info is None:
        return None
    if _now() > info["expires_at"]:
        return None
    return info


# ────────── 从 Request 提取并校验 token ──────────

def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", f"req-{uuid.uuid4().hex[:8]}")


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None
