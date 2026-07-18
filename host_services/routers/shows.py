from fastapi import APIRouter, Request, Depends
from ..deps import require_auth
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Shows"],
                   dependencies=[Depends(require_auth)])


@router.get("/shows")
async def list_shows(request: Request):
    return ok(request, {"shows": engine_adapter.get_shows()})
