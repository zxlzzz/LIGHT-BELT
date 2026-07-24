"""
Engine Adapter —— 唯一和「下层」打交道的地方。

Mock 模式（ENGINE_ADAPTER=mock，默认）：所有状态存在内存里，不依赖 mpv /
light_engine / 硬件。

生产模式（ENGINE_ADAPTER=real）：同样的内存状态 + 真实 light_engine 子进程
（通过 _real_adapter）。测试永远跑 mock 模式，不受影响。
"""

import time
import json
import logging
import os
import uuid
import socket
import subprocess
from typing import Any
from .config import (
    SCENE_MAX_COUNT, SCENE_FILE_PATH, SHOWS_MANIFEST_PATH,
    ENGINE_PROFILE_PATH, ENGINE_ADAPTER, VIDEO_DETECT_ENABLED,
)
from .schemas import VALID_EFFECT_TYPES

_log = logging.getLogger(__name__)


class MpvUnavailableError(RuntimeError):
    """Raised when mpv cannot be started or its socket directory cannot be created."""


# ══════════════════════════════════════════════
# Layout vocabulary (derived at import time)
# ══════════════════════════════════════════════

def _load_layout_vocab():
    """Return (valid_target_ids, capability_targets, devices) from ENGINE_PROFILE_PATH."""
    try:
        from pathlib import Path as _Path
        from light_engine.config import Config as _Config
        from light_engine.mapping import Layout
        from .layout_vocab import derive_target_ids, derive_capabilities_targets, derive_device_list
        config = _Config.get_instance(_Path(ENGINE_PROFILE_PATH))
        layout = Layout.from_config(config)
        return (
            derive_target_ids(layout),
            derive_capabilities_targets(layout),
            derive_device_list(layout),
        )
    except Exception as exc:
        _log.warning(
            "engine_adapter: failed to load layout vocab from %s: %s; using empty vocab",
            ENGINE_PROFILE_PATH, exc,
        )
        return frozenset({"all"}), [{"target_id": "all", "name": "all"}], []


_valid_target_ids: frozenset[str]
_capability_targets: list[dict]
_devices: list[dict]
_valid_target_ids, _capability_targets, _devices = _load_layout_vocab()


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

    def add_audio_track(self, path: str):
        """Add an external audio file as the selected audio track."""
        self._send(["audio-add", path, "select"])


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

# Internal fields hidden from the /shows API response.
_SHOW_INTERNAL_FIELDS = {"media_path", "show_yaml", "aux_triggers", "audio_path"}

# Overridable in tests via monkeypatch; None means use shows_loader discovery.
_shows: list[dict] | None = None


def _load_shows() -> list[dict]:
    if _shows is not None:
        return _shows
    from . import shows_loader
    return shows_loader.load_shows()

_scenes: dict[str, dict] = {}  # 启动时由下方 _scenes.update(_load_scenes()) 从 SCENE_FILE_PATH 恢复


def _now_ms() -> int:
    return int(time.time() * 1000)

import urllib.request

def _probe_devices() -> None:
    """Ping each WLED node's HTTP API; update status in-place."""
    t = _now_ms()
    for d in _devices:
        host = d.get("host")
        if not host:
            continue
        try:
            urllib.request.urlopen(f"http://{host}/json/info", timeout=1)
            d["status"] = "online"
            d["connection_confirmed"] = True
            d["last_seen_ms"] = t
            d["error_code"] = None
        except Exception:
            d["status"] = "offline"
            d["connection_confirmed"] = False

def _mark_devices_output() -> None:
    t = _now_ms()
    for d in _devices:
        d["last_output_ms"] = t


# ══════════════════════════════════════════════
# Real adapter (None in mock mode)
# ══════════════════════════════════════════════

_real_adapter = None  # type: Any  # RealEngineAdapter | None

# Accumulated manual-target state for real-adapter calls.
# key = target_id (strip), value = {target_id, effect_type, color}.
_manual_targets: dict[str, dict] = {}


def _init_real_adapter():
    global _real_adapter
    if ENGINE_ADAPTER != "real":
        return
    try:
        from .real_engine_adapter import RealEngineAdapter
        from .config import MPV_SOCKET_PATH
        strip_ids = _valid_target_ids - {"all", "starry_sky"}
        _real_adapter = RealEngineAdapter(
            profile_path=ENGINE_PROFILE_PATH,
            mpv_socket_path=MPV_SOCKET_PATH,
            strip_ids=strip_ids,
        )
        _log.info("engine_adapter: real adapter initialized")
    except Exception as exc:
        _log.error("engine_adapter: failed to init real adapter: %s", exc)


_init_real_adapter()


def _detect_video_available() -> bool:
    """Check HDMI connection via xrandr. Returns True if any HDMI output is connected."""
    if not VIDEO_DETECT_ENABLED:
        return True
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "HDMI" in line and " connected" in line:
                    return True
            return False
    except Exception as exc:
        _log.warning("video detection failed: %s; assuming available", exc)
    return True


_state["video_available"] = _detect_video_available()


def _accumulate_hw_entry(tid: str, effect_type: str, hw_color: list) -> None:
    """Merge one hw entry into _manual_targets, expanding 'all' to per-strip IDs."""
    strip_ids = _valid_target_ids - {"all", "starry_sky"}
    entry = {"target_id": tid, "effect_type": effect_type, "color": hw_color}
    if tid == "all":
        for sid in strip_ids:
            _manual_targets[sid] = {**entry, "target_id": sid}
    else:
        _manual_targets[tid] = entry


def _apply_manual_targets() -> None:
    """Send the complete accumulated _manual_targets list to the real adapter."""
    if _real_adapter is not None and _manual_targets:
        _real_adapter.on_manual_command(list(_manual_targets.values()))
    if _manual_targets:
        _mark_devices_output()


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
    _probe_devices()
    safe_devices = [
        {k: v for k, v in d.items() if k != "host"}
        for d in _devices
    ]
    return {**_state, "devices": safe_devices}


# ══════════════════════════════════════════════
# Shows
# ══════════════════════════════════════════════

def get_shows() -> list[dict]:
    return [
        {k: v for k, v in s.items() if k not in _SHOW_INTERNAL_FIELDS}
        for s in _load_shows()
    ]

# ══════════════════════════════════════════════
# Capabilities
# ══════════════════════════════════════════════

def get_capabilities() -> dict:
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
        "targets": _capability_targets,
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
    for s in _load_shows():
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


def _drain_stderr(proc: subprocess.Popen, name: str) -> None:
    import threading
    def _reader():
        for raw in proc.stderr:
            _log.warning("[%s] %s", name, raw.decode(errors="replace").rstrip())
    threading.Thread(target=_reader, daemon=True).start()


def _ensure_mpv() -> MpvClient:
    global _mpv, _mpv_proc
    from .config import MPV_SOCKET_PATH, MPV_DISPLAY
    sock = MPV_SOCKET_PATH

    if os.path.exists(sock):
        # Probe whether mpv is actually alive behind the socket.
        try:
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(1.0)
            probe.connect(sock)
            probe.close()
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            _log.warning("mpv socket %s is stale; removing and restarting mpv", sock)
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass
            if _mpv_proc is not None and _mpv_proc.poll() is None:
                _mpv_proc.terminate()
                try:
                    _mpv_proc.wait(3)
                except subprocess.TimeoutExpired:
                    _mpv_proc.kill()
                    _mpv_proc.wait()
            _mpv_proc = None
            _mpv = None
        # Probe succeeded — mpv is alive; skip restart.

    if not os.path.exists(sock):
        try:
            os.makedirs(os.path.dirname(sock), exist_ok=True)
        except Exception as exc:
            _log.error(
                "mpv: cannot create socket directory %s: %s — "
                "ensure /run/light-belt exists or set RuntimeDirectory=light-belt in the systemd unit",
                os.path.dirname(sock), exc,
            )
            raise MpvUnavailableError(f"Cannot create mpv socket directory: {exc}") from exc
        env = os.environ.copy()
        env.setdefault("DISPLAY", MPV_DISPLAY)
        try:
            _mpv_proc = subprocess.Popen(
                ["mpv", f"--input-ipc-server={sock}", "--idle=yes",
                 "--no-terminal"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                env=env,
            )
        except Exception as exc:
            _log.error(
                "mpv: failed to start mpv subprocess: %s — "
                "check that mpv is installed and the socket path %s is writable",
                exc, sock,
            )
            raise MpvUnavailableError(f"Cannot start mpv: {exc}") from exc
        _drain_stderr(_mpv_proc, "mpv")
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
    if show.get("media_path"):
        try:
            mpv = _ensure_mpv()
        except MpvUnavailableError:
            return None, "MPV_UNAVAILABLE"
        mpv.play_file(show["media_path"])
        if show.get("audio_path"):
            if not _wait_until(lambda: mpv.get_duration() > 0, timeout_s=2.0):
                _log.warning("mpv did not report duration in time; adding audio track anyway")
            mpv.add_audio_track(show["audio_path"])
        if start_ms and start_ms > 0:
            if not _wait_until(lambda: mpv.get_duration() > 0, timeout_s=2.0):
                _log.warning("mpv did not report duration in time; seeking anyway")
            mpv.seek(start_ms / 1000)
    _state["playback_state"] = "playing"
    _state["show_id"] = show_id
    _state["position_ms"] = start_ms or 0
    _state["duration_ms"] = show["duration_ms"]
    _state["scene_id"] = None
    _manual_targets.clear()
    if _real_adapter is not None:
        _real_adapter.on_playback_start(show, start_ms)
        _mark_devices_output()
    return _playback_data(), None


def playback_pause() -> tuple[dict | None, str | None]:
    if _state["playback_state"] != "playing":
        return None, "PLAYBACK_NOT_READY"
    _ensure_mpv().pause()
    _state["playback_state"] = "paused"
    return _playback_data(), None


def playback_resume() -> tuple[dict | None, str | None]:
    if _state["playback_state"] not in ("playing", "paused"):
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
    _manual_targets.clear()
    if _real_adapter is not None:
        _real_adapter.on_playback_stop()
    return _playback_data(), None


def playback_seek(position_ms: float) -> tuple[dict | None, str | None]:
    if _state["playback_state"] not in ("playing", "paused"):
        return None, "SHOW_NOT_LOADED"
    _ensure_mpv().seek(position_ms / 1000)
    _state["position_ms"] = position_ms
    return _playback_data(), None


def playback_reset() -> tuple[dict | None, str | None]:
    """Resume the show's YAML lighting after a manual override.

    Clears accumulated manual targets and restarts the show's light_engine
    subprocess.  mpv is NOT restarted; the engine re-syncs via --clock mpv.
    In mock mode (_real_adapter is None) only clears manual targets.
    """
    if _state["playback_state"] not in ("playing", "paused"):
        return None, "PLAYBACK_NOT_READY"
    _manual_targets.clear()
    if _real_adapter is not None:
        ok = _real_adapter.on_playback_resume_yaml()
        if not ok:
            return None, "NO_ACTIVE_SHOW"
    if _state["playback_state"] == "paused":
        if _mpv is not None:
            _mpv.resume()
        _state["playback_state"] = "playing"
    return _playback_data(), None


# ══════════════════════════════════════════════
# Lights
# ══════════════════════════════════════════════

def lights_set(target_id: str, brightness: float | None,
               color_temperature: int | None,
               transition_ms: float,
               color=None) -> tuple[dict | None, str | None]:
    if target_id not in _valid_target_ids:
        return None, "NOT_FOUND"
    if brightness is None and color_temperature is None and color is None:
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
    if color is not None:
        data["color"] = {"r": color.r, "g": color.g, "b": color.b}
    if _real_adapter is not None:
        if color is not None:
            hw_color = [color.r / 255, color.g / 255, color.b / 255]
        else:
            hw_color = [brightness if brightness is not None else 1.0] * 3
        _accumulate_hw_entry(target_id, "static", hw_color)
        _apply_manual_targets()
    else:
        _mark_devices_output()
    return data, None


# ══════════════════════════════════════════════
# Effects
# ══════════════════════════════════════════════

def effects_set(target_id: str, effect_type: str,
                transition_ms: float,
                params=None, effect_params=None) -> tuple[dict | None, str | None]:
    from .layout_vocab import STARRY_SKY_TARGET_ID
    if target_id not in _valid_target_ids:
        return None, "NOT_FOUND"
    # twinkle is the only valid effect for starry_sky; "off" is also accepted
    if target_id == STARRY_SKY_TARGET_ID:
        from . import starry_sky as _ss
        if effect_type == "twinkle":
            _ss.ensure_on()
        else:
            _ss.ensure_off()
        _state["scene_id"] = None
        return {
            "target_id": target_id,
            "effect_type": effect_type,
            "transition_ms": transition_ms,
            "accepted": True,
        }, None
    if effect_type not in VALID_EFFECT_TYPES:
        return None, "INVALID_ARGUMENT"
    _state["scene_id"] = None
    data: dict[str, Any] = {
        "target_id": target_id,
        "effect_type": effect_type,
        "transition_ms": transition_ms,
        "accepted": True,
    }
    if params is not None:
        data["params"] = params.model_dump(exclude_none=True)
    if effect_params is not None:
        data["effect_params"] = effect_params
    if _real_adapter is not None:
        if params is not None and params.color is not None:
            hw_color = [params.color.r / 255, params.color.g / 255, params.color.b / 255]
        else:
            hw_color = [1.0, 1.0, 1.0]
        _accumulate_hw_entry(target_id, effect_type, hw_color)
        _apply_manual_targets()
    return data, None


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
            if e.get("target_id") not in _valid_target_ids:
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
        if _mpv is not None:
            try:
                if a.get("volume") is not None:
                    _mpv.set_volume(a["volume"])
                if a.get("muted") is not None:
                    _mpv.set_mute(a["muted"])
            except Exception as exc:
                _log.warning("scene_apply: mpv IPC failed: %s", exc)
    if scene.get("entries"):
        _manual_targets.clear()
        for e in scene["entries"]:
            tid = e.get("target_id")
            if not tid:
                continue
            if tid == "all":
                if e.get("brightness") is not None:
                    _state["brightness"] = e["brightness"]
                if e.get("color_temperature") is not None:
                    _state["color_temperature"] = e["color_temperature"]
            color_raw = (e.get("params") or {}).get("color")
            if color_raw is not None:
                hw_color = [color_raw["r"] / 255, color_raw["g"] / 255, color_raw["b"] / 255]
            else:
                brightness = e.get("brightness")
                hw_color = [brightness if brightness is not None else 1.0] * 3
            effect_type = e.get("effect_type", "static")
            _accumulate_hw_entry(tid, effect_type, hw_color)
        _apply_manual_targets()
    _state["scene_id"] = scene_id
    return {
        "scene_id": scene_id,
        "accepted": True,
        "partial": False,
        "failed_targets": [],
        "applied_entries": scene.get("entries", []),
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
