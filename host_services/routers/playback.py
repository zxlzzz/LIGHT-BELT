from fastapi import APIRouter, Request, Depends
from ..schemas import PlayRequest, SeekRequest
from ..deps import require_auth
from ..response import ok, error
from .. import engine_adapter

router = APIRouter(prefix="/api/v1/playback", tags=["Playback"],
                   dependencies=[Depends(require_auth)])


@router.post("/play")
async def play(body: PlayRequest, request: Request):
    data, err = engine_adapter.playback_play(body.show_id, body.start_position_ms)
    if err:
        if err == "NOT_FOUND":
            code = 404
        elif err == "INVALID_ARGUMENT":
            code = 400
        else:
            code = 409
        return error(request, err, f"Playback play failed: {err}", code)
    return ok(request, data)


@router.post("/pause")
async def pause(request: Request):
    data, err = engine_adapter.playback_pause()
    if err:
        return error(request, err, "Cannot pause: not playing", 409)
    return ok(request, data)


@router.post("/resume")
async def resume(request: Request):
    data, err = engine_adapter.playback_resume()
    if err:
        return error(request, err, "Cannot resume: not paused", 409)
    return ok(request, data)


@router.post("/stop")
async def stop(request: Request):
    data, _ = engine_adapter.playback_stop()
    return ok(request, data)


@router.post("/seek")
async def seek(body: SeekRequest, request: Request):
    data, err = engine_adapter.playback_seek(body.position_ms)
    if err:
        return error(request, err, "No show loaded", 409)
    return ok(request, data)
