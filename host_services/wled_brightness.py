"""Keep WLED local state black while DDP owns the visible output."""

from __future__ import annotations

import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

_log = logging.getLogger(__name__)

_STATE_PATH = "/json/state"
_CONFIG_PATH = "/json/cfg"
_BLACK_RGBA = [0, 0, 0, 0]


def _black_state(*, on: bool, bri: int | None = None) -> dict[str, Any]:
    """Return one atomic WLED state update with a black local fallback.

    Production has one active segment per WLED board.  Keeping that segment
    enabled lets DDP take over immediately, while Solid black prevents WLED's
    local 0xFFA000 default from becoming visible before or after realtime mode.
    """
    payload: dict[str, Any] = {
        "on": on,
        "transition": 0,
        "seg": [{"id": 0, "on": True, "fx": 0, "col": [_BLACK_RGBA]}],
        "v": False,
    }
    if bri is not None:
        payload["bri"] = bri
    return payload


def _post_json(host: str, path: str, payload: dict[str, Any], timeout: float) -> bool:
    try:
        req = urllib.request.Request(
            f"http://{host}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(req, timeout=timeout)
        try:
            status = response.getcode()
            return status is None or 200 <= status < 300
        finally:
            response.close()
    except Exception as exc:
        _log.warning("WLED POST %s%s failed: %s", host, path, exc)
        return False


def _get_json(host: str, path: str, timeout: float) -> dict[str, Any] | None:
    try:
        response = urllib.request.urlopen(f"http://{host}{path}", timeout=timeout)
        try:
            status = response.getcode()
            if status is not None and not 200 <= status < 300:
                raise RuntimeError(f"HTTP {status}")
            data = json.loads(response.read().decode())
        finally:
            response.close()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        _log.warning("WLED GET %s%s failed: %s", host, path, exc)
        return None


def _post_bri(host: str, bri: int, timeout: float) -> None:
    _post_json(host, _STATE_PATH, _black_state(on=True, bri=bri), timeout)


def apply_scale(devices: list[dict], scale: float, timeout: float = 1.0) -> None:
    """Safely enable all WLED devices at black with the requested brightness."""
    bri = max(0, min(255, round(255 * scale)))
    hosts = [d["host"] for d in devices if d.get("host")]
    if not hosts:
        return
    with ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_post_bri, h, bri, timeout) for h in hosts]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass


def apply_off(devices: list[dict], timeout: float = 1.0) -> None:
    """Set the local fallback to Solid black, then turn the master state off."""
    hosts = [d["host"] for d in devices if d.get("host")]
    if not hosts:
        return
    def _off(host: str) -> None:
        _post_json(host, _STATE_PATH, _black_state(on=False), timeout)

    with ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_off, h) for h in hosts]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass


def _ensure_black_boot(host: str, timeout: float) -> bool:
    """Persist an off/no-preset boot policy without rewriting unchanged config."""
    config = _get_json(host, _CONFIG_PATH, timeout)
    if config is None:
        return False
    defaults = config.get("def")
    if isinstance(defaults, dict) and defaults.get("on") is False and defaults.get("ps") == 0:
        return True
    return _post_json(host, _CONFIG_PATH, {"def": {"on": False, "ps": 0}}, timeout)


def apply_black_boot_policy(devices: list[dict], timeout: float = 1.0) -> dict[str, bool]:
    """Ensure every WLED cold-boots black instead of using DEFAULT_COLOR.

    WLED's partial ``/json/cfg`` update preserves unrelated hardware and network
    settings.  Reading first avoids unnecessary flash writes on Host restarts.
    """
    hosts = [d["host"] for d in devices if d.get("host")]
    if not hosts:
        return {}
    with ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = {host: ex.submit(_ensure_black_boot, host, timeout) for host in hosts}
        return {host: future.result() for host, future in futures.items()}
