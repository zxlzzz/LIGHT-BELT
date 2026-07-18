from fastapi import APIRouter, Request, Depends
from ..deps import require_auth
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Capabilities"],
                   dependencies=[Depends(require_auth)])


@router.get("/capabilities")
async def get_capabilities(request: Request):
    return ok(request, engine_adapter.get_capabilities())
