from fastapi import APIRouter, Request, Depends
from ..schemas import PairRequest, RefreshRequest, WsTicketRequest, VALID_CLIENT_TYPES, VALID_WS_TYPES
from ..deps import require_auth
from ..response import ok, invalid_argument, error
from .. import auth_manager
from ..config import PAIRING_CODE

router = APIRouter(prefix="/api/v1", tags=["Auth"])


@router.post("/auth/pair")
async def pair(body: PairRequest, request: Request):
    if body.client_type not in VALID_CLIENT_TYPES:
        return invalid_argument(request, f"Invalid client_type: {body.client_type}")
    if body.pairing_code != PAIRING_CODE:
        return error(request, "PAIRING_CODE_INVALID", "Invalid pairing code", 400)
    tokens = auth_manager.issue_token_pair(body.client_id)
    return ok(request, tokens)


@router.post("/auth/refresh")
async def refresh(body: RefreshRequest, request: Request):
    info = auth_manager.consume_refresh_token(body.refresh_token)
    if info is None:
        return error(request, "UNAUTHORIZED", "Invalid or expired refresh token", 401)
    tokens = auth_manager.issue_token_pair(info["client_id"])
    return ok(request, tokens)


@router.post("/session/ws-ticket", dependencies=[Depends(require_auth)])
async def ws_ticket(body: WsTicketRequest, request: Request):
    for t in body.subscribe:
        if t not in VALID_WS_TYPES:
            return invalid_argument(request, f"Unknown message type: {t}")
    host = request.headers.get("host", "0.0.0.0:8443")
    data = auth_manager.create_ws_ticket(body.subscribe, host=host)
    return ok(request, data)
