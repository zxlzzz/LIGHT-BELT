"""Simulator output - thread-safe frame buffer for the lighting simulator."""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

from light_engine.models import PixelFrame
from light_engine.outputs import LightOutput


class SimulatorOutput(LightOutput):
    """Thread-safe frame buffer for the terminal simulator.

    send_frame() is called by the Engine thread.
    pop_latest() is called by the Simulator thread.

    When the simulator is slower than the engine, old frames are dropped
    so the simulator always shows the latest state.
    """

    def __init__(self, max_frames: int = 64):
        super().__init__()
        self._buffer: deque[PixelFrame] = deque(maxlen=max_frames)
        self._max_frames = max_frames
        self._lock = threading.Lock()

        # Counters (thread-safe)
        self._frames_sent: int = 0
        self._frames_consumed: int = 0
        self._frames_dropped: int = 0

    def open(self) -> None:
        self._open = True

    def send_frame(self, frame: PixelFrame) -> None:
        """Thread-safe: enqueue a frame from the engine thread."""
        with self._lock:
            self._buffer.append(frame)
            self._frames_sent += 1
            if len(self._buffer) > 1:
                self._frames_dropped += 1

    def pop_latest(self) -> Optional[PixelFrame]:
        """Thread-safe: get the latest frame and drain all older ones.

        Returns:
            The most recent PixelFrame, or None if buffer is empty.
            Each frame is returned at most once.
        """
        with self._lock:
            if not self._buffer:
                return None
            frame = self._buffer[-1]
            self._buffer.clear()
            self._frames_consumed += 1
            return frame

    def close(self) -> None:
        with self._lock:
            self._buffer.clear()
        self._open = False

    def frame_count(self) -> int:
        """Thread-safe: number of frames currently buffered."""
        with self._lock:
            return len(self._buffer)

    def frames_sent(self) -> int:
        """Total frames sent by the engine."""
        with self._lock:
            return self._frames_sent

    def frames_consumed(self) -> int:
        """Total frames consumed by the simulator."""
        with self._lock:
            return self._frames_consumed

    def frames_dropped(self) -> int:
        """Frames overwritten before the simulator could consume them."""
        with self._lock:
            return self._frames_dropped

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update({"supports_rgbcct": True, "supports_digital": True})
        return caps
