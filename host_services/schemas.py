"""
请求/响应模型，相当于 Java 的 DTO / VO。
字段名、类型、范围严格对齐 host_api_v1.md。
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

# ────────────────── 枚举常量 ──────────────────

VALID_CLIENT_TYPES = {"tablet", "phone", "debug"}

VALID_EFFECT_TYPES = {
    "static", "breath", "color_wave", "chase", "comet",
    "audio_pulse", "bass_pulse", "spectrum",
    "video_ambient", "video_audio_fusion", "calm", "demo",
}

VALID_WS_TYPES = {
    "session.connected", "runtime.state", "playback.progress",
    "device.status", "error.event", "heartbeat",
    "scene.applied",  # V1.1
}

# ────────────────── Auth ──────────────────

class PairRequest(BaseModel):
    pairing_code: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    client_type: str
    app_version: str = Field(min_length=1)

class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)

class WsTicketRequest(BaseModel):
    subscribe: list[str] = Field(min_length=1)

# ────────────────── Playback ──────────────────

class PlayRequest(BaseModel):
    show_id: str = Field(min_length=1)
    start_position_ms: Optional[float] = Field(default=None, ge=0)

class SeekRequest(BaseModel):
    position_ms: float = Field(ge=0)

# ────────────────── Shared primitives ──────────────────

class RGB(BaseModel):
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)

# ────────────────── Lights ──────────────────

class LightsSetRequest(BaseModel):
    target_id: str
    brightness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    color_temperature: Optional[int] = Field(default=None, ge=2700, le=6500)
    color: Optional[RGB] = None
    transition_ms: Optional[float] = Field(default=0, ge=0)

# ────────────────── Effects ──────────────────

class EffectCommonParams(BaseModel):
    color: Optional[RGB] = None
    speed: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)

class EffectsSetRequest(BaseModel):
    target_id: str
    effect_type: str
    params: Optional[EffectCommonParams] = None
    effect_params: Optional[dict[str, Any]] = None
    transition_ms: Optional[float] = Field(default=0, ge=0)

# ────────────────── Audio (V1.1) ──────────────────

class AudioSetRequest(BaseModel):
    volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    muted: Optional[bool] = None
    transition_ms: Optional[float] = Field(default=0, ge=0)

# ────────────────── Scenes (V1.1) ──────────────────

class SceneAudio(BaseModel):
    volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    muted: Optional[bool] = None

class SceneEntry(BaseModel):
    target_id: str
    # lights/set 字段
    brightness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    color_temperature: Optional[int] = Field(default=None, ge=2700, le=6500)
    # effects/set 字段
    effect_type: Optional[str] = None
    params: Optional[EffectCommonParams] = None
    effect_params: Optional[dict[str, Any]] = None
    transition_ms: Optional[float] = Field(default=0, ge=0)

class SceneSaveRequest(BaseModel):
    scene_id: Optional[str] = Field(default=None, pattern=r"^[a-z0-9-]{1,64}$")
    name: str = Field(min_length=1)
    audio: Optional[SceneAudio] = None
    entries: Optional[list[SceneEntry]] = None

class SceneApplyRequest(BaseModel):
    scene_id: str = Field(min_length=1)
    transition_ms: Optional[float] = Field(default=None, ge=0)

class SceneDeleteRequest(BaseModel):
    scene_id: str = Field(min_length=1)
