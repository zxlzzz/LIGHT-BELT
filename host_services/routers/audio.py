from fastapi import APIRouter, Request, Depends
from ..schemas import AudioSetRequest
from ..deps import require_auth
from ..response import ok, invalid_argument, error
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Audio"],
                   dependencies=[Depends(require_auth)])


@router.get("/audio")
async def get_audio(request: Request):
    return ok(request, engine_adapter.get_audio())


@router.post("/audio/set")
async def audio_set(body: AudioSetRequest, request: Request):
    data, err = engine_adapter.audio_set(
        body.volume, body.muted, body.transition_ms or 0,
    )
    if err == "INVALID_ARGUMENT":
        return invalid_argument(request, "at least one of volume or muted is required")
    if err:
        return error(request, err, f"audio_set failed: {err}")
    return ok(request, data)
