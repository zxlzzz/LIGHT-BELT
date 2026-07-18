from fastapi import APIRouter, Request, Depends
from ..schemas import SceneSaveRequest, SceneApplyRequest, SceneDeleteRequest
from ..deps import require_auth
from ..response import ok, error, invalid_argument, not_found
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Scenes"],
                   dependencies=[Depends(require_auth)])


@router.get("/scenes")
async def list_scenes(request: Request):
    return ok(request, {"scenes": engine_adapter.get_scenes()})


@router.post("/scenes/save")
async def scene_save(body: SceneSaveRequest, request: Request):
    entries_raw = [e.model_dump(exclude_none=True) for e in body.entries] if body.entries else None
    audio_raw = body.audio.model_dump(exclude_none=True) if body.audio else None
    data, err = engine_adapter.scene_save(
        body.scene_id, body.name, audio_raw, entries_raw,
    )
    if err == "INVALID_ARGUMENT":
        details = data.get("error_detail") if data else None
        return invalid_argument(request, "Scene validation failed", details)
    if err == "SCENE_LIMIT_EXCEEDED":
        return error(request, err, "Scene limit reached (max 32)", 409)
    return ok(request, data)


@router.post("/scenes/apply")
async def scene_apply(body: SceneApplyRequest, request: Request):
    data, err = engine_adapter.scene_apply(body.scene_id, body.transition_ms)
    if err == "NOT_FOUND":
        return not_found(request, f"Scene not found: {body.scene_id}")
    return ok(request, data)


@router.post("/scenes/delete")
async def scene_delete(body: SceneDeleteRequest, request: Request):
    data, err = engine_adapter.scene_delete(body.scene_id)
    if err == "NOT_FOUND":
        return not_found(request, f"Scene not found: {body.scene_id}")
    return ok(request, data)
