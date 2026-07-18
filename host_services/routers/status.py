from fastapi import APIRouter, Request
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Status"])


@router.get("/status")
async def status(request: Request):
    return ok(request, engine_adapter.get_status())
