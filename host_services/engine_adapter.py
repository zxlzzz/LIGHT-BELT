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
import sys
import uuid
import socket
import subprocess
import threading
from typing import Any
from .config import (
    SCENE_MAX_COUNT, SCENE_FILE_PATH, SHOWS_MANIFEST_PATH,
    ENGINE_PROFILE_PATH, ENGINE_ADAPTER, VIDEO_DETECT_ENABLED,
    WLED_RUNTIME_PROFILE, WLED_TEMPLATE_PROFILE,
    BRIGHTNESS_SCALE_DEFAULT, WLED_HTTP_TIMEOUT_S,
)
from .schemas import VALID_EFFECT_TYPES

_log = logging.getLogger(__name__)

WLED_DEVICE_TYPE = "wled_board"
CUSTOM_UDP_V3_DEVICE_TYPE = "custom_esp32_udp_v3"


class MpvUnavailableError(RuntimeError):
    """Raised when mpv cannot be started or its socket directory cannot be created."""


def _device_type_from_outputs(enabled_outputs: list[str]) -> str:
    selected = set(enabled_outputs) & {"ddp", "udp_v3"}
    if selected == {"ddp"}:
        return WLED_DEVICE_TYPE
    if selected == {"udp_v3"}:
        return CUSTOM_UDP_V3_DEVICE_TYPE
    raise ValueError(
        "outputs.enabled must select exactly one of ddp or udp_v3 for Host device typing"
    )


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
        profile_path = _Path(ENGINE_PROFILE_PATH)
        if not profile_path.exists() and profile_path.resolve() == WLED_RUNTIME_PROFILE.resolve():
            profile_path = WLED_TEMPLATE_PROFILE
        config = _Config.get_instance(profile_path)
        layout = Layout.from_config(config)
        device_type = _device_type_from_outputs(config.get("outputs.enabled", []))
        return (
            derive_target_ids(layout),
            derive_capabilities_targets(layout),
            derive_device_list(layout, device_type=device_type),
        )
    except Exception as exc:
        _log.warning(
            "engine_adapter: failed to load layout vocab from %s: %s; using empty vocab",
            ENGINE_PROFILE_PATH, exc,
        )
        return frozenset({"all"}), [{"target_id": "all", "name": "all"}], []


def _run_resolve_nodes() -> None:
    """在进程内跑 resolve_nodes.py，确保 profile 里的 IP 是最新的。"""
    if ENGINE_ADAPTER != "real":
        return
    from pathlib import Path as _P
    if _P(ENGINE_PROFILE_PATH).resolve() != WLED_RUNTIME_PROFILE.resolve():
        return
    script = _P(__file__).resolve().parent.parent / "scripts" / "resolve_nodes.py"
    if not script.exists():
        raise RuntimeError(f"resolve_nodes.py not found at {script}")
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--template", str(WLED_TEMPLATE_PROFILE), "--out", ENGINE_PROFILE_PATH],
            timeout=30,
            capture_output=True,
            text=True,
        )
        for line in (result.stderr or "").splitlines():
            _log.info("[resolve_nodes] %s", line)
        if result.returncode:
            raise RuntimeError(
                f"resolve_nodes.py exited with {result.returncode}: {result.stderr or ''}".strip()
            )
    except Exception as exc:
        raise RuntimeError(f"resolve_nodes.py failed: {exc}") from exc


_valid_target_ids: frozenset[str]
_capability_targets: list[dict]
_devices: list[dict]
_run_resolve_nodes()
_valid_target_ids, _capability_targets, _devices = _load_layout_vocab()


# ══════════════════════════════════════════════
# mpv IPC 客户端
# ══════════════════════════════════════════════

class MpvClient:
    def __init__(self, sock_path: str):
        self._sock_path = sock_path

    _SEND_TIMEOUT_S = 2.0

    def _send(self, cmd: list) -> dict:
        s = None
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self._SEND_TIMEOUT_S)
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
            return json.loads(resp.split(b"\n")[0])
        except socket.timeout:
            _log.warning("mpv IPC timeout (%.1fs) for command: %s", self._SEND_TIMEOUT_S, cmd)
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

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

    def get_idle_active(self) -> bool:
        """Return True when mpv is idle (no file loaded / playback finished)."""
        r = self._send(["get_property", "idle-active"])
        return bool(r.get("data", False))


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
    # V1.2
    "brightness_scale": BRIGHTNESS_SCALE_DEFAULT,
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

def _filter_show_fields(show: dict) -> dict:
    return {k: v for k, v in show.items() if k not in _SHOW_INTERNAL_FIELDS}


_scenes: dict[str, dict] = {}  # 启动时由下方 _scenes.update(_load_scenes()) 从 SCENE_FILE_PATH 恢复


def _now_ms() -> int:
    return int(time.time() * 1000)


def _live_position_ms() -> int:
    """Return live mpv position in ms; falls back to stored position if mpv unavailable or idle."""
    if _mpv is None:
        return _state["position_ms"]
    try:
        if _mpv.get_idle_active():
            return _state["position_ms"]
        pos = _mpv.get_position()
        if pos <= 0:
            return _state["position_ms"]
        return int(pos * 1000)
    except Exception:
        return _state["position_ms"]


def _push_brightness_scale() -> None:
    """Send current brightness_scale to all WLED nodes (fire-and-forget)."""
    from . import wled_brightness
    scale = _state["brightness_scale"]
    hosts_devices = [d for d in _devices if d.get("host") and d.get("enabled", True) and d.get("device_type") == WLED_DEVICE_TYPE]
    if hosts_devices:
        wled_brightness.apply_scale(hosts_devices, scale, WLED_HTTP_TIMEOUT_S)


def _push_wled_off() -> None:
    """停止播放时把节点本地状态关掉。

    DDP 停流后 WLED 退出 realtime 会回落到本地状态（出厂默认 = 开 + 琥珀色），
    表现为节目结束后灯带全黄。显式发 {"on": false} 消掉这个回落。
    """
    from . import wled_brightness
    hosts_devices = [d for d in _devices if d.get("host") and d.get("enabled", True) and d.get("device_type") == WLED_DEVICE_TYPE]
    if hosts_devices:
        wled_brightness.apply_off(hosts_devices, WLED_HTTP_TIMEOUT_S)


import urllib.request

def _probe_devices() -> None:
    """Ping each WLED node's HTTP API; update status in-place."""
    t = _now_ms()
    for d in _devices:
        if not d.get("enabled", True):
            d["status"] = "offline"
            d["connection_confirmed"] = False
            d["error_code"] = "MDNS_UNRESOLVED"
            continue
        if d.get("device_type") != WLED_DEVICE_TYPE:
            continue
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
        if d.get("enabled", True):
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
        # 节点可能被 playback_stop / 自然结束看门狗关过，先重新点亮再下发。
        _push_brightness_scale()
        _real_adapter.on_manual_command(list(_manual_targets.values()))
    if _manual_targets:
        _mark_devices_output()


# ══════════════════════════════════════════════
# Status
# ══════════════════════════════════════════════

def get_status() -> dict:
    from .config import SERVICE_NAME, HOST_ID, API_VERSION, SERVICE_VERSION, GIT_COMMIT
    return {
        "service": SERVICE_NAME,
        "host_id": HOST_ID,
        "api_version": API_VERSION,
        "version": SERVICE_VERSION,
        "commit": GIT_COMMIT,
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
# Brightness scale (V1.2)
# ══════════════════════════════════════════════

def get_brightness_scale() -> dict:
    return {"brightness_scale": _state["brightness_scale"]}


def brightness_scale_set(brightness_scale: float, transition_ms: float) -> tuple[dict, None]:
    _state["brightness_scale"] = brightness_scale
    _push_brightness_scale()
    return {
        "brightness_scale": _state["brightness_scale"],
        "transition_ms": transition_ms,
        "accepted": True,
    }, None


# ══════════════════════════════════════════════
# Shows
# ══════════════════════════════════════════════

def get_shows() -> list[dict]:
    return [_filter_show_fields(s) for s in _load_shows()]

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
        "audio": True, "scenes": True, "brightness_scale": True,
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
    from .config import MPV_SOCKET_PATH, MPV_DISPLAY, MPV_XAUTHORITY, MPV_GEOMETRY
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
        env.setdefault("XAUTHORITY", MPV_XAUTHORITY)
        from pathlib import Path as _Path
        _input_conf = str(
            _Path(__file__).resolve().parent.parent / "config" / "mpv-kiosk-input.conf"
        )
        try:
            _mpv_proc = subprocess.Popen(
                ["mpv", f"--input-ipc-server={sock}", "--idle=yes",
                 "--keep-open=no", "--no-terminal",
                 "--vo=xv",
                 "--input-default-bindings=no",
                 f"--geometry={MPV_GEOMETRY}", "--no-border", "--force-window=yes","--no-osc",
                 f"--input-conf={_input_conf}"],
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
    # Tear down current playback before starting new show (same as stop).
    if _mpv and not show.get("media_path"):
        _mpv.stop()
    _manual_targets.clear()
    if _real_adapter is not None:
        _real_adapter.on_playback_stop()
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
        mpv.resume()
    _state["playback_state"] = "playing"
    _state["show_id"] = show_id
    _state["position_ms"] = start_ms or 0
    _state["duration_ms"] = show["duration_ms"]
    _state["scene_id"] = None
    _state["brightness_scale"] = BRIGHTNESS_SCALE_DEFAULT
    _manual_targets.clear()
    if _real_adapter is not None:
        _real_adapter.on_playback_start(show, start_ms)
        _mark_devices_output()
    _push_brightness_scale()
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
        _push_wled_off()
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
    _push_brightness_scale()
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

def get_playback_state() -> dict:
    """Live /playback/state response: live position, current show fields, brightness_scale, audio."""
    show_id = _state["show_id"]
    show = None
    if show_id:
        s = _find_show(show_id)
        if s:
            show = _filter_show_fields(s)
    return {
        "playback_state": _state["playback_state"],
        "show": show,
        "position_ms": _live_position_ms(),
        "duration_ms": _state["duration_ms"],
        "brightness_scale": _state["brightness_scale"],
        "audio": {
            "volume": _state["volume"],
            "muted": _state["muted"],
        },
    }


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
        "brightness_scale": _state["brightness_scale"],
    }


def get_playback_progress_snapshot() -> dict:
    return _playback_data()


# ══════════════════════════════════════════════
# 自然结束看门狗
# ══════════════════════════════════════════════
#
# 节目自己播到结尾时没有人调 /playback/stop：mpv 变 idle、light_engine 停止
# 推 DDP，节点在 if.live.timeout 之后回落到本地状态（默认琥珀色）→ 灯全黄。
# 这个线程负责补上那次收尾。仅在 real 模式启动，mock 模式（测试）不受影响。

_WATCHDOG_INTERVAL_S = 1.0
_WATCHDOG_IDLE_STREAK = 3      # 连续 3 次读到 idle 才认定结束，躲开加载中的空窗
_WATCHDOG_CRASH_STREAK = 5     # 连续 5 次进程已死/IPC 不可达才判定 mpv 崩溃
_watchdog_thread: threading.Thread | None = None


def _finalize_natural_end() -> None:
    """等价于一次 playback_stop。如果 mpv 进程已死，顺带清理引用以便下次重建。"""
    global _mpv, _mpv_proc
    _state["playback_state"] = "stopped"
    _state["show_id"] = None
    _state["position_ms"] = 0
    _state["duration_ms"] = 0
    _manual_targets.clear()
    if _mpv_proc is not None and _mpv_proc.poll() is not None:
        _log.warning(
            "_finalize_natural_end: mpv process already dead (exit %s); clearing references",
            _mpv_proc.returncode,
        )
        sock = _mpv._sock_path if _mpv is not None else None
        if sock:
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass
            except Exception:
                pass
        _mpv = None
        _mpv_proc = None
    if _real_adapter is not None:
        _real_adapter.on_playback_stop()
        _push_wled_off()

def _natural_end_watchdog() -> None:
    streak = 0
    dead_streak = 0
    ipc_streak = 0
    while True:
        time.sleep(_WATCHDOG_INTERVAL_S)
        try:
            # 只管「我们以为在播、且确实有媒体」的情况。
            # duration_ms == 0 的占位节目本来就没有 mpv 参与，跳过。
            if _state["playback_state"] != "playing" or not _state["duration_ms"]:
                streak = 0
                dead_streak = 0
                ipc_streak = 0
                continue

            # mpv 子进程已经退出（被 kill / 崩溃）——不用等 IPC 超时，直接判定。
            if _mpv_proc is not None and _mpv_proc.poll() is not None:
                dead_streak += 1
                if dead_streak >= _WATCHDOG_CRASH_STREAK:
                    _log.error(
                        "watchdog: mpv process dead (exit %s) while state='playing'; "
                        "finalizing as crash",
                        _mpv_proc.returncode,
                    )
                    dead_streak = 0
                    ipc_streak = 0
                    _finalize_natural_end()
                continue
            dead_streak = 0

            if _mpv is None:
                streak = 0
                continue

            # 直接调用 _send 而不是 get_idle_active()，因为后者把 IPC 失败
            # 和「IPC 成功但 idle=False」都折叠成同一个 False，无法区分
            # 「mpv 半死不活/超时」和「mpv 正常在播」。
            r = _mpv._send(["get_property", "idle-active"])
            if r.get("error") != "success":
                ipc_streak += 1
                if ipc_streak >= _WATCHDOG_CRASH_STREAK:
                    _log.error(
                        "watchdog: mpv IPC unreachable %d times (%s); finalizing as crash",
                        ipc_streak, r.get("error"),
                    )
                    ipc_streak = 0
                    _finalize_natural_end()
                streak = 0
                continue
            ipc_streak = 0

            if not bool(r.get("data", False)):
                streak = 0
                continue
            streak += 1
            if streak < _WATCHDOG_IDLE_STREAK:
                continue
            streak = 0
            _log.info("watchdog: mpv idle while playing; finalizing natural show end")
            _finalize_natural_end()
        except Exception as exc:                        # noqa: BLE001
            _log.debug("watchdog: %s: %s", type(exc).__name__, exc)
            streak = 0
            dead_streak = 0
            ipc_streak = 0

def _start_natural_end_watchdog() -> None:
    global _watchdog_thread
    if _real_adapter is None:
        return
    if _watchdog_thread is not None and _watchdog_thread.is_alive():
        return
    _watchdog_thread = threading.Thread(
        target=_natural_end_watchdog, name="natural-end-watchdog", daemon=True)
    _watchdog_thread.start()
    _log.info("engine_adapter: natural-end watchdog started")


_start_natural_end_watchdog()


def _ensure_mpv_at_startup() -> None:
    """在 real 模式下，服务启动时立即拉起 mpv 全屏黑窗口（遮住桌面）。"""
    if _real_adapter is None:
        return
    try:
        _ensure_mpv()
        _log.info("engine_adapter: mpv started at startup (fullscreen idle)")
    except MpvUnavailableError as exc:
        _log.warning("engine_adapter: mpv not available at startup: %s (will retry on first play)", exc)


_ensure_mpv_at_startup()


# ══════════════════════════════════════════════
# 延迟重新 resolve —— 补开机时节点还没 ready 的时序缝隙
# ══════════════════════════════════════════════

def _deferred_re_resolve() -> None:
    """开机后退避重试 resolve，直到九块全部解析出真实 IP 或耗尽重试。

    覆盖冷启动时节点还没连 WiFi / avahi 还没 ready 的时序缝隙。
    单次 30s 对慢冷启动不够，改为退避重试；任一次全部解析成功即停止。
    """
    global _valid_target_ids, _capability_targets, _devices
    if ENGINE_ADAPTER != "real":
        return
    from light_engine.config import Config as _Cfg
    for attempt, delay in enumerate((15, 15, 30, 30, 60, 60, 120), start=1):
        time.sleep(delay)
        try:
            old_hosts = {d["device_id"]: d.get("host") for d in _devices}
            _run_resolve_nodes()
            _Cfg.reset()  # 清掉 singleton 缓存，强制重新读文件
            new_ids, new_caps, new_devs = _load_layout_vocab()
            new_hosts = {d["device_id"]: d.get("host") for d in new_devs}
            changed = {k for k in old_hosts if old_hosts[k] != new_hosts.get(k)}
            if changed:
                _valid_target_ids = new_ids
                _capability_targets = new_caps
                _devices = new_devs
                _log.info(
                    "deferred re-resolve #%d: updated %s",
                    attempt,
                    ", ".join(f"{k}: {old_hosts[k]} -> {new_hosts.get(k)}" for k in changed),
                )
            unresolved = [k for k, v in new_hosts.items()
                          if not v or str(v).endswith(".local")]
            if not unresolved:
                _log.info("deferred re-resolve #%d: 九块全部解析成功，停止", attempt)
                return
            _log.info("deferred re-resolve #%d: 仍未解析 %s", attempt, unresolved)
        except Exception as exc:
            _log.warning("deferred re-resolve #%d failed: %s", attempt, exc)
    _log.warning("deferred re-resolve: 重试耗尽，仍有节点未解析")
    

_deferred_re_resolve_thread: threading.Thread | None = None


def _start_deferred_re_resolve() -> None:
    global _deferred_re_resolve_thread
    if ENGINE_ADAPTER != "real":
        return
    if _deferred_re_resolve_thread is not None and _deferred_re_resolve_thread.is_alive():
        return
    _deferred_re_resolve_thread = threading.Thread(
        target=_deferred_re_resolve, name="deferred-re-resolve", daemon=True)
    _deferred_re_resolve_thread.start()
    _log.info("engine_adapter: deferred re-resolve thread started")


_start_deferred_re_resolve()

def _start_deferred_re_resolve() -> None:
    """后台启动退避重试线程，补冷启动时节点未就绪的时序缝隙。

    _deferred_re_resolve 内部已对 ENGINE_ADAPTER != "real" 做了早退，
    这里始终尝试启动，避免遗漏。
    """
    threading.Thread(
        target=_deferred_re_resolve, name="deferred-re-resolve", daemon=True).start()
    _log.info("engine_adapter: deferred re-resolve thread started")


_start_deferred_re_resolve()