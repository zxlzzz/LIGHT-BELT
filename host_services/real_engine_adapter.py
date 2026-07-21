"""Real engine adapter — subprocess-based light_engine integration.

This adapter is activated when ENGINE_ADAPTER=real.  It manages two kinds of
subprocesses:

  - Playback subprocess: `python -m light_engine --config <profile> run
      --show <show_yaml> --clock mpv --mpv-socket <socket>`
      (audio shows add --audio <media_path>)
  - Manual subprocess: same binary but `--clock internal`, re-created each time
      lights_set / effects_set is called (replaces previous manual process).

Starry-sky UDP control (aux_triggers) is handled here during playback polling.

The caller (engine_adapter.py) keeps all API-visible state.  This class only
manages subprocesses and hardware side-effects; it does not own _state.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml

_log = logging.getLogger(__name__)


def _kill_proc(proc: subprocess.Popen | None, name: str = "engine") -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _log.warning("%s did not terminate; sending SIGKILL", name)
            proc.kill()
            proc.wait(timeout=3)
    except Exception as exc:
        _log.warning("error stopping %s: %s", name, exc)


class RealEngineAdapter:
    """Manages light_engine subprocesses for production mode."""

    def __init__(
        self,
        profile_path: str,
        mpv_socket_path: str,
        python_executable: str = "python",
    ) -> None:
        self._profile = profile_path
        self._mpv_socket = mpv_socket_path
        self._python = python_executable

        self._playback_proc: subprocess.Popen | None = None
        self._manual_proc: subprocess.Popen | None = None
        self._aux_poll_thread: threading.Thread | None = None
        self._aux_stop_event = threading.Event()

        # Temp file for manual show YAML (cleaned up on replace/stop).
        self._manual_yaml_tmp: str | None = None

    # ── playback ──────────────────────────────────────────────────────────────

    def on_playback_start(self, show: dict, start_ms: float | None) -> None:
        """Launch engine subprocess for show playback."""
        self._stop_manual()
        _kill_proc(self._playback_proc, "playback engine")

        show_yaml = show.get("show_yaml")
        media_path = show.get("media_path")

        if not show_yaml:
            _log.warning("real adapter: show %r has no show_yaml; engine not started", show.get("show_id"))
            return

        cmd = [
            self._python, "-m", "light_engine",
            "--config", self._profile,
            "run",
            "--show", show_yaml,
            "--clock", "mpv",
            "--mpv-socket", self._mpv_socket,
        ]
        if media_path:
            cmd += ["--audio", media_path]

        _log.info("real adapter: starting playback engine: %s", " ".join(cmd))
        self._playback_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Start aux_triggers polling thread.
        aux_triggers = show.get("aux_triggers") or []
        if aux_triggers:
            self._start_aux_poll(aux_triggers, start_ms or 0)

    def on_playback_stop(self) -> None:
        """Stop playback engine and aux polling."""
        self._stop_aux_poll()
        _kill_proc(self._playback_proc, "playback engine")
        self._playback_proc = None

        from . import starry_sky
        starry_sky.ensure_off()

    # ── manual lights / effects ────────────────────────────────────────────────

    def on_manual_command(self, target_states: list[dict]) -> None:
        """Render target_states as a temp show YAML and launch manual engine."""
        self._stop_manual()
        _kill_proc(self._playback_proc, "playback engine")
        self._playback_proc = None

        show_yaml = self._build_manual_show(target_states)
        if show_yaml is None:
            return

        cmd = [
            self._python, "-m", "light_engine",
            "--config", self._profile,
            "run",
            "--show", show_yaml,
            "--clock", "internal",
        ]
        _log.info("real adapter: starting manual engine: %s", " ".join(cmd))
        self._manual_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def _build_manual_show(self, target_states: list[dict]) -> str | None:
        """Write a schema_version 2 show YAML for infinite static cues and return path."""
        cues = []
        for i, ts in enumerate(target_states):
            tid = ts.get("target_id", "")
            if tid == "all":
                continue  # 'all' has no direct v2 target type; skip
            effect_type = ts.get("effect_type", "static")
            color = ts.get("color", [1.0, 1.0, 1.0])
            cues.append({
                "id": f"manual_{i}",
                "start": 0.0,
                "end": 86400.0,
                "target": {"type": "digital_strip", "id": tid},
                "effect": {"mode": "fixed", "id": effect_type, "params": {}},
                "color": {"mode": "solid", "color": color},
            })

        if not cues:
            return None

        doc = {
            "schema_version": 2,
            "show": {
                "id": "manual_override",
                "duration": 86400.0,
                "defaults": {
                    "fade_in": 0.0, "fade_out": 0.0,
                    "blend": "replace", "min_effect_hold": 0.0,
                    "switch_cooldown": 0.0,
                },
                "cues": cues,
            },
        }

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix="lb_manual_")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                yaml.safe_dump(doc, f, allow_unicode=True)
        except Exception as exc:
            _log.warning("real adapter: failed to write manual show YAML: %s", exc)
            return None

        if self._manual_yaml_tmp and os.path.exists(self._manual_yaml_tmp):
            try:
                os.unlink(self._manual_yaml_tmp)
            except Exception:
                pass
        self._manual_yaml_tmp = tmp_path
        return tmp_path

    def _stop_manual(self) -> None:
        _kill_proc(self._manual_proc, "manual engine")
        self._manual_proc = None
        if self._manual_yaml_tmp and os.path.exists(self._manual_yaml_tmp):
            try:
                os.unlink(self._manual_yaml_tmp)
            except Exception:
                pass
            self._manual_yaml_tmp = None

    # ── aux_triggers polling ───────────────────────────────────────────────────

    def _start_aux_poll(self, aux_triggers: list[dict], start_ms: float) -> None:
        self._stop_aux_poll()
        self._aux_stop_event.clear()
        self._aux_poll_thread = threading.Thread(
            target=self._aux_poll_loop,
            args=(aux_triggers, start_ms),
            daemon=True,
            name="aux-triggers-poll",
        )
        self._aux_poll_thread.start()

    def _stop_aux_poll(self) -> None:
        self._aux_stop_event.set()
        if self._aux_poll_thread and self._aux_poll_thread.is_alive():
            self._aux_poll_thread.join(timeout=2)
        self._aux_poll_thread = None

    def _aux_poll_loop(self, aux_triggers: list[dict], _start_ms: float) -> None:
        """Poll mpv position ~1/s and fire starry_sky on/off triggers."""
        from . import starry_sky
        from .engine_adapter import _mpv  # noqa: PLC0415 — import inside thread

        while not self._aux_stop_event.is_set():
            try:
                mpv = _mpv
                pos_ms = (mpv.get_position() * 1000) if mpv else 0.0

                for trigger in aux_triggers:
                    if trigger.get("target") != "starry_sky":
                        continue
                    at_ms = trigger.get("at_ms", 0)
                    action = trigger.get("action", "")
                    if pos_ms >= at_ms:
                        if action == "on":
                            starry_sky.ensure_on()
                        elif action == "off":
                            starry_sky.ensure_off()
                    else:
                        if action == "on":
                            starry_sky.ensure_off()
            except Exception as exc:
                _log.debug("aux_poll_loop: %s", exc)

            self._aux_stop_event.wait(timeout=1.0)

    # ── shutdown ───────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean up all subprocesses and hardware state."""
        self._stop_aux_poll()
        _kill_proc(self._playback_proc, "playback engine")
        self._playback_proc = None
        self._stop_manual()

        from . import starry_sky
        starry_sky.ensure_off()
