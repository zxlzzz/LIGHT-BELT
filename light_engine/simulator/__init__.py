"""Lighting simulator: terminal-based visualization of strips and zones.

Headless fallback when no GUI is available.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional

from light_engine.config import Config
from light_engine.models import PixelFrame
from light_engine.outputs import SimulatorOutput


# ANSI color codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_CLEAR = "\033[2J\033[H"


def _rgb_to_ansi(r: float, g: float, b: float) -> str:
    """Convert RGB [0,1] to ANSI 24-bit color escape code."""
    ri = max(0, min(255, round(r * 255)))
    gi = max(0, min(255, round(g * 255)))
    bi = max(0, min(255, round(b * 255)))
    return f"\033[48;2;{ri};{gi};{bi}m"


class TerminalSimulator:
    """Terminal-based lighting visualization using ANSI color codes.

    Displays all strips as rows of colored blocks, plus debug info.

    Auto-exits when the engine has stopped AND the frame buffer is empty.
    """

    def __init__(
        self,
        output: SimulatorOutput,
        config: Optional[Config] = None,
        engine_done: Optional[threading.Event] = None,
    ):
        if config is None:
            config = Config.get_instance()
        self._output = output
        self._config = config
        self._width = config.get("outputs.simulator.width", 80)
        self._show_fps = config.get("outputs.simulator.show_fps", True)
        self._show_debug = config.get("outputs.simulator.show_debug", True)
        self._running = False
        self._frame_count = 0
        self._start_time = 0.0
        self._engine_done = engine_done  # set when engine thread exits

    def run(self, max_frames: Optional[int] = None) -> None:
        """Run the terminal simulator in a loop.

        Automatically exits when:
        - engine_done event is set AND the frame buffer is empty, OR
        - max_frames have been rendered.
        """
        self._running = True
        self._start_time = time.perf_counter()
        consecutive_empty = 0

        print(_CLEAR, end="")
        try:
            while self._running:
                frame = self._output.pop_latest()

                if frame is not None:
                    self._frame_count += 1
                    consecutive_empty = 0
                    self._draw(frame)
                else:
                    consecutive_empty += 1
                    time.sleep(0.01)

                # Check max_frames
                if max_frames is not None and self._frame_count >= max_frames:
                    break

                # Auto-exit: engine stopped AND buffer drained
                if self._engine_done is not None and self._engine_done.is_set():
                    if frame is None:
                        # Buffer is already empty, exit after a short grace
                        if consecutive_empty >= 5:
                            break

                # Check for quit key (if stdin available)
                if sys.platform == "win32":
                    import msvcrt
                    if msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key in (b'q', b'Q', b'\x1b'):
                            break
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            print(_RESET)

    def _draw(self, frame: PixelFrame) -> None:
        """Render one frame to the terminal."""
        elapsed = time.perf_counter() - self._start_time
        fps = self._frame_count / max(0.001, elapsed)

        lines = []
        lines.append(_CLEAR)
        lines.append(f"{_BOLD}╔══ Light Engine Simulator ══╗{_RESET}")

        # Draw each digital strip
        for strip in frame.strips:
            line = f" {strip.strip_id:<16} │"
            pixels_uint8 = strip.to_uint8()
            pixels_per_char = max(1, strip.pixel_count // self._width)
            for i in range(0, strip.pixel_count, pixels_per_char):
                if i < len(pixels_uint8):
                    r, g, b = pixels_uint8[i]
                    line += _rgb_to_ansi(r / 255, g / 255, b / 255) + " " + _RESET
            lines.append(line)

        # Draw RGB+CCT zones
        if frame.zones:
            lines.append(f" {'─' * 80}")
            for zone in frame.zones:
                c = zone.color.to_uint8()
                block = _rgb_to_ansi(c["r"] / 255, c["g"] / 255, c["b"] / 255)
                lines.append(
                    f" {zone.zone_id:<16} │{block}  {_RESET}"
                    f" R:{c['r']:3d} G:{c['g']:3d} B:{c['b']:3d}"
                    f" WW:{c['warm_white']:3d} CW:{c['cool_white']:3d}"
                )

        # Debug info
        if self._show_debug:
            lines.append(f" {'─' * 80}")
            lines.append(
                f" Sim Frame: {self._frame_count:6d}  |  FPS: {fps:.1f}  |  "
                f"Time: {frame.timestamp:.2f}s"
            )
            lines.append(
                f" Engine Generated: {self._output.frames_sent():6d}  |  "
                f"Dropped: {self._output.frames_dropped()}"
            )
            meta = frame.metadata
            if meta:
                if "demo_current" in meta:
                    lines.append(f" Effect: {meta['demo_current']}")
                if "video_rgb" in meta:
                    vr, vg, vb = meta["video_rgb"]
                    lines.append(f" Video: RGB({vr:.2f},{vg:.2f},{vb:.2f})")
                if "audio_rms" in meta:
                    lines.append(
                        f" Audio: RMS={meta['audio_rms']:.3f} "
                        f"Bass={meta.get('bass', 0):.3f} "
                        f"Beat={'Y' if meta.get('beat') else 'N'}"
                    )

        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()

    def stop(self) -> None:
        self._running = False

    @property
    def frame_count(self) -> int:
        """Number of unique frames actually rendered."""
        return self._frame_count
