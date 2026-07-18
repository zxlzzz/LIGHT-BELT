"""
Engine Adapter —— 唯一和「下层」打交道的地方。

本地测试版：所有状态存在内存里，不依赖 mpv / light_engine / 硬件。
切换到生产时，只需要把这个文件里的方法实现换成真实调用。

相当于 Java 里 ServiceImpl 的 mock 版本。
"""

import time
import json
import logging
import os
import uuid
import socket
import subprocess
from typing import Any
from .config import SCENE_MAX_COUNT, SCENE_FILE_PATH, SHOWS_MANIFEST_PATH
from .schemas import VALID_TARGET_IDS, VALID_EFFECT_TYPES

_log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# mpv IPC 客户端
# ══════════════════════════════════════════════

class MpvClient:
    def __init__(self, sock_path: str):
        self._sock_path = sock_path

    def _send(self, cmd: list) -> dict:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self._sock_path)
            msg = json.dumps({"command": cmd}) + "\n"
            s.sendall(msg.encode())
            resp = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if b"\n" in resp:
                    break
            s.close()
            return json.loads(resp.split(b"\n")[0])
        except Exception as e:
            return {"error": str(e)}

    def play_file(self, path: str):
        self._send(["loadfile", path, "replace"])

    def pause(self):
        self._send(["set_property", "pause", True])

    def resume(self):
        self._send(["set_property", "pause", False])

    def stop(self):
        self._send(["stop"])

    def seek(self, position_sec: float):
        self._send(["seek", position_sec, "absolute"])

    def get_duration(self) -> float:
        r = self._send(["get_property", "duration"])
        return r.get("data") or 0.0

    def get_position(self) -> float:
        r = self._send(["get_property", "time-pos"])
        return r.get("data") or 0.0

    def set_volume(self, volume_0_1: float):
        self._send(["set_property", "volume", volume_0_1 * 100])

    def set_mute(self, muted: bool):
        self._send(["set_property", "mute", muted])


# ══════════════════════════════════════════════
# 内存状态 —— Postman 测试时状态会随操作变化
# ══════════════════════════════════════════════

_state = {
    "system_state": "running",
    "playback_state": "idle",
    "show_id": None,
    "position_ms": 0,
    "duration_ms": 0,
    "brightness": 1.0,
    "color_temperature": 4200,
    "audio_available": True,
    "video_available": True,
    "audio_link_enabled": True,
    "video_link_enabled": True,
    # V1.1
    "volume": 0.5,
    "muted": False,
    "scene_id": None,
}

_SHOW_REQUIRED_FIELDS = ("show_id", "name", "duration_ms", "media_path")
# 对 APP 隐藏的内部字段（媒体与灯效文件路径）
_SHOW_INTERNAL_FIELDS = {"media_path", "show_yaml"}


def _load_shows_manifest() -> list[dict]:
    """从 SHOWS_MANIFEST_PATH 加载节目单。

    格式见 host_services/shows_manifest.example.json。
    非法条目跳过并告警，不影响其余节目。
    """
    try:
        with open(SHOWS_MANIFEST_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        _log.warning("shows manifest not found at %s; starting with empty show list", SHOWS_MANIFEST_PATH)
        return []
    except Exception as exc:
        _log.warning("failed to load shows manifest: %s; starting with empty show list", exc)
        return []
    if not isinstance(raw, list):
        _log.warning("shows manifest must be a JSON array; got %s", type(raw).__name__)
        return []
    shows: list[dict] = []
    seen: set[str] = set()
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            _log.warning("manifest entry %d is not an object; skipped", i)
            continue
        missing = [k for k in _SHOW_REQUIRED_FIELDS if s.get(k) is None]
        if missing:
            _log.warning("manifest entry %d (show_id=%r) missing %s; skipped",
                         i, s.get("show_id"), missing)
            continue
        if s["show_id"] in seen:
            _log.warning("duplicate show_id %r at entry %d; skipped", s["show_id"], i)
            continue
        seen.add(s["show_id"])
        shows.append({"description": None, "show_yaml": None, **s})
    return shows


_shows: list[dict] = _load_shows_manifest()

_devices = [
    {"device_id": "analog.ceiling_left", "device_type": "light_zone",
     "status": "online", "last_output_ms": 0, "last_seen_ms": 0,
     "connection_confirmed": True, "error_code": None},
    {"device_id": "digital.screen_to_wall", "device_type": "light_path",
     "status": "online", "last_output_ms": 0, "last_seen_ms": 0,
     "connection_confirmed": True, "error_code": None},
]

_scenes: dict[str, dict] = {}  # 启动时由下方 _scenes.update(_load_scenes()) 从 SCENE_FILE_PATH 恢复


def _now_ms() -> int:
    return int(time.time() * 1000)


def _touch_devices():
    t = _now_ms()
    for d in _devices:
        d["last_output_ms"] = t
        d["last_seen_ms"] = t


# ══════════════════════════════════════════════
# Status
# ══════════════════════════════════════════════

def get_status() -> dict:
    from .config import SERVICE_NAME, HOST_ID, API_VERSION, SERVICE_VERSION
    return {
        "service": SERVICE_NAME,
        "host_id": HOST_ID,
        "api_version": API_VERSION,
        "version": SERVICE_VERSION,
        "time_ms": _now_ms(),
    }


# ══════════════════════════════════════════════
# State
# ══════════════════════════════════════════════

def get_state() -> dict:
    _touch_devices()
    return {**_state, "devices": _devices}


# ══════════════════════════════════════════════
# Shows
# ══════════════════════════════════════════════

def get_shows() -> list[dict]:
    # media_path / show_yaml 是内部字段，不对外暴露
    return [
        {k: v for k, v in s.items() if k not in _SHOW_INTERNAL_FIELDS}
        for s in _shows
    ]


# ══════════════════════════════════════════════
# Capabilities
# ══════════════════════════════════════════════

def get_capabilities() -> dict:
    targets = [
        {"target_id": "all", "name": "全部区域"},
        {"target_id": "ceiling_left", "name": "左侧顶部"},
        {"target_id": "ceiling_right", "name": "右侧顶部"},
        {"target_id": "wall_left", "name": "左墙"},
        {"target_id": "wall_right", "name": "右墙"},
        {"target_id": "front", "name": "前方"},
        {"target_id": "rear", "name": "后方"},
        {"target_id": "screen", "name": "屏幕"},
        {"target_id": "screen_surround", "name": "屏幕环绕"},
        {"target_id": "virtual_path.screen_to_wall", "name": "屏幕到墙面路径"},
    ]
    effects = [
        {"effect_type": "static", "name": "Static",
         "params": ["color", "intensity"], "effect_params": []},
        {"effect_type": "breath", "name": "Breath",
         "params": ["color", "intensity"], "effect_params": ["period", "min_brightness"]},
        {"effect_type": "chase", "name": "Chase",
         "params": ["speed", "intensity"],
         "effect_params": ["width", "gap", "direction"]},
        {"effect_type": "color_wave", "name": "Color Wave",
         "params": ["speed", "intensity"], "effect_params": ["width"]},
        {"effect_type": "comet", "name": "Comet",
         "params": ["speed", "intensity"], "effect_params": ["tail_length", "decay"]},
        {"effect_type": "audio_pulse", "name": "Audio Pulse",
         "params": ["color", "intensity"], "effect_params": ["attack", "release"]},
        {"effect_type": "bass_pulse", "name": "Bass Pulse",
         "params": ["color", "intensity"], "effect_params": ["attack", "release"]},
        {"effect_type": "spectrum", "name": "Spectrum",
         "params": ["intensity"], "effect_params": ["bass_zones", "mid_zones", "treble_zones"]},
        {"effect_type": "video_ambient", "name": "Video Ambient",
         "params": ["intensity"], "effect_params": ["smoothing"]},
        {"effect_type": "video_audio_fusion", "name": "Video Audio Fusion",
         "params": ["intensity"], "effect_params": ["video_weight", "audio_weight"]},
        {"effect_type": "calm", "name": "Calm",
         "params": ["color", "intensity"], "effect_params": ["period"]},
        {"effect_type": "demo", "name": "Demo",
         "params": [], "effect_params": ["cycle_interval", "effects"]},
    ]
    ws_types = [
        "session.connected", "runtime.state", "playback.progress",
        "device.status", "error.event", "heartbeat", "scene.applied",
    ]
    supports = {
        "playback": True, "resume": True, "seek": True,
        "lights": True, "effects": True, "color_temperature": True,
        "transitions": True, "websocket": True,
        "audio": True, "scenes": True,
    }
    return {
        "targets": targets,
        "effects": effects,
        "websocket": {"message_types": ws_types},
        "supports": supports,
    }


# ══════════════════════════════════════════════
# Playback
# ══════════════════════════════════════════════

_mpv: MpvClient | None = None
_mpv_proc: subprocess.Popen | None = None


def _find_show(show_id: str) -> dict | None:
    for s in _shows:
        if s["show_id"] == show_id:
            return s
    return None


def _playback_data() -> dict:
    return {
        "playback_state": _state["playback_state"],
        "show_id": _state["show_id"],
        "position_ms": _state["position_ms"],
        "duration_ms": _state["duration_ms"],
    }


def _wait_until(cond, timeout_s: float = 3.0, interval_s: float = 0.05) -> bool:
    """轮询直到 cond() 为真或超时。返回是否成功。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(interval_s)
    return cond()


def _ensure_mpv() -> MpvClient:
    global _mpv, _mpv_proc
    from .config import MPV_SOCKET_PATH, MPV_DISPLAY
    sock = MPV_SOCKET_PATH
    if not os.path.exists(sock):
        os.makedirs(os.path.dirname(sock), exist_ok=True)
        env = os.environ.copy()
        env.setdefault("DISPLAY", MPV_DISPLAY)
        _mpv_proc = subprocess.Popen(
            ["mpv", f"--input-ipc-server={sock}", "--idle=yes",
             "--no-terminal"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env,
        )
        if not _wait_until(lambda: os.path.exists(sock)):
            _log.warning("mpv IPC socket %s not ready after timeout", sock)
    if _mpv is None:
        _mpv = MpvClient(sock)
    return _mpv


def playback_play(show_id: str, start_ms: float | None) -> tuple[dict | None, str | None]:
    show = _find_show(show_id)
    if show is None:
        return None, "NOT_FOUND"
    if start_ms is not None and start_ms > show["duration_ms"]:
        return None, "INVALID_ARGUMENT"
    mpv = _ensure_mpv()
    mpv.play_file(show["media_path"])
    if start_ms and start_ms > 0:
        # 等文件真正加载（duration 可读）再 seek，替代固定 sleep
        if not _wait_until(lambda: mpv.get_duration() > 0, timeout_s=2.0):
            _log.warning("mpv did not report duration in time; seeking anyway")
        mpv.seek(start_ms / 1000)
    _state["playback_state"] = "playing"
    _state["show_id"] = show_id
    _state["position_ms"] = start_ms or 0
    _state["duration_ms"] = show["duration_ms"]
    _state["scene_id"] = None
    return _playback_data(), None


def playback_pause() -> tuple[dict | None, str | None]:
    if _state["playback_state"] != "playing":
        return None, "PLAYBACK_NOT_READY"
    _ensure_mpv().pause()
    _state["playback_state"] = "paused"
    return _playback_data(), None


def playback_resume() -> tuple[dict | None, str | None]:
    if _state["playback_state"] != "paused":
        return None, "PLAYBACK_NOT_READY"
    _ensure_mpv().resume()
    _state["playback_state"] = "playing"
    return _playback_data(), None


def playback_stop() -> tuple[dict, None]:
    if _mpv:
        _mpv.stop()
    _state["playback_state"] = "stopped"
    _state["show_id"] = None
    _state["position_ms"] = 0
    _state["duration_ms"] = 0
    return _playback_data(), None


def playback_seek(position_ms: float) -> tuple[dict | None, str | None]:
    if _state["playback_state"] not in ("playing", "paused"):
        return None, "SHOW_NOT_LOADED"
    _ensure_mpv().seek(position_ms / 1000)
    _state["position_ms"] = position_ms
    return _playback_data(), None


# ══════════════════════════════════════════════
# Lights
# ══════════════════════════════════════════════

def lights_set(target_id: str, brightness: float | None,
               color_temperature: int | None,
               transition_ms: float) -> tuple[dict | None, str | None]:
    if target_id not in VALID_TARGET_IDS:
        return None, "NOT_FOUND"
    if brightness is None and color_temperature is None:
        return None, "INVALID_ARGUMENT"
    if target_id == "all":
        if brightness is not None:
            _state["brightness"] = brightness
        if color_temperature is not None:
            _state["color_temperature"] = color_temperature
    _state["scene_id"] = None
    data: dict[str, Any] = {
        "target_id": target_id,
        "transition_ms": transition_ms,
        "accepted": True,
    }
    if brightness is not None:
        data["brightness"] = brightness
    if color_temperature is not None:
        data["color_temperature"] = color_temperature
    return data, None


# ══════════════════════════════════════════════
# Effects
# ══════════════════════════════════════════════

def effects_set(target_id: str, effect_type: str,
                transition_ms: float) -> tuple[dict | None, str | None]:
    if target_id not in VALID_TARGET_IDS:
        return None, "NOT_FOUND"
    if effect_type not in VALID_EFFECT_TYPES:
        return None, "INVALID_ARGUMENT"
    _state["scene_id"] = None
    return {
        "target_id": target_id,
        "effect_type": effect_type,
        "transition_ms": transition_ms,
        "accepted": True,
    }, None


# ══════════════════════════════════════════════
# Audio (V1.1)
# ══════════════════════════════════════════════

def get_audio() -> dict:
    return {
        "volume": _state["volume"],
        "muted": _state["muted"],
        "audio_output_available": True,
    }


def audio_set(volume: float | None, muted: bool | None,
              transition_ms: float) -> tuple[dict | None, str | None]:
    if volume is None and muted is None:
        return None, "INVALID_ARGUMENT"
    if volume is not None:
        _state["volume"] = volume
    if muted is not None:
        _state["muted"] = muted
    _state["scene_id"] = None
    if _mpv is not None:
        try:
            if volume is not None:
                _mpv.set_volume(volume)
            if muted is not None:
                _mpv.set_mute(muted)
        except Exception as exc:
            _log.warning("audio_set: mpv IPC failed: %s", exc)
    else:
        _log.warning("audio_set: mpv not running, state updated in memory only")
    return {
        "volume": _state["volume"],
        "muted": _state["muted"],
        "transition_ms": transition_ms,
        "accepted": True,
    }, None


# ══════════════════════════════════════════════
# Scenes (V1.1)
# ══════════════════════════════════════════════

def _load_scenes() -> dict[str, dict]:
    try:
        with open(SCENE_FILE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        _log.warning("scene file %s has unexpected format; ignoring", SCENE_FILE_PATH)
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log.warning("failed to load scenes from %s: %s", SCENE_FILE_PATH, exc)
    return {}


def _save_scenes() -> None:
    try:
        d = os.path.dirname(SCENE_FILE_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = SCENE_FILE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_scenes, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SCENE_FILE_PATH)
    except Exception as exc:
        _log.warning("failed to persist scenes to %s: %s", SCENE_FILE_PATH, exc)


# 服务启动时从磁盘恢复场景（文件不存在则保持空）
_scenes.update(_load_scenes())


def get_scenes() -> list[dict]:
    return [
        {"scene_id": sid, "name": s["name"],
         "created_ms": s["created_ms"], "updated_ms": s["updated_ms"]}
        for sid, s in _scenes.items()
    ]


def scene_save(scene_id: str | None, name: str,
               audio: dict | None,
               entries: list[dict] | None) -> tuple[dict | None, str | None]:
    if audio is None and entries is None:
        return None, "INVALID_ARGUMENT"
    if entries:
        for i, e in enumerate(entries):
            if e.get("target_id") not in VALID_TARGET_IDS:
                return {"error_detail": {"entry_index": i, "field": "target_id"}}, "INVALID_ARGUMENT"
            if e.get("effect_type") and e["effect_type"] not in VALID_EFFECT_TYPES:
                return {"error_detail": {"entry_index": i, "field": "effect_type"}}, "INVALID_ARGUMENT"
    if scene_id is None:
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    if scene_id not in _scenes and len(_scenes) >= SCENE_MAX_COUNT:
        return None, "SCENE_LIMIT_EXCEEDED"
    now = _now_ms()
    _scenes[scene_id] = {
        "name": name, "audio": audio, "entries": entries,
        "created_ms": _scenes.get(scene_id, {}).get("created_ms", now),
        "updated_ms": now,
    }
    _save_scenes()
    return {"scene_id": scene_id, "saved": True}, None


def scene_apply(scene_id: str,
                transition_ms: float | None) -> tuple[dict | None, str | None]:
    if scene_id not in _scenes:
        return None, "NOT_FOUND"
    scene = _scenes[scene_id]
    if _state["playback_state"] == "playing":
        playback_stop()
    if scene.get("audio"):
        a = scene["audio"]
        if "volume" in a and a["volume"] is not None:
            _state["volume"] = a["volume"]
        if "muted" in a and a["muted"] is not None:
            _state["muted"] = a["muted"]
    if scene.get("entries"):
        for e in scene["entries"]:
            if e.get("target_id") == "all":
                if "brightness" in e and e["brightness"] is not None:
                    _state["brightness"] = e["brightness"]
                if "color_temperature" in e and e["color_temperature"] is not None:
                    _state["color_temperature"] = e["color_temperature"]
    _state["scene_id"] = scene_id
    return {
        "scene_id": scene_id,
        "accepted": True,
        "partial": False,
        "failed_targets": [],
    }, None


def scene_delete(scene_id: str) -> tuple[dict | None, str | None]:
    if scene_id not in _scenes:
        return None, "NOT_FOUND"
    del _scenes[scene_id]
    if _state["scene_id"] == scene_id:
        _state["scene_id"] = None
    _save_scenes()
    return {"scene_id": scene_id, "deleted": True}, None


# ══════════════════════════════════════════════
# WebSocket 状态快照（供 ws.py 推送）
# ══════════════════════════════════════════════

def get_runtime_state_snapshot() -> dict:
    return {
        "system_state": _state["system_state"],
        "playback_state": _state["playback_state"],
        "show_id": _state["show_id"],
        "brightness": _state["brightness"],
        "color_temperature": _state["color_temperature"],
        "audio_available": _state["audio_available"],
        "video_available": _state["video_available"],
        "audio_link_enabled": _state["audio_link_enabled"],
        "video_link_enabled": _state["video_link_enabled"],
        "volume": _state["volume"],
        "muted": _state["muted"],
        "scene_id": _state["scene_id"],
    }


def get_playback_progress_snapshot() -> dict:
    return _playback_data()
