"""Unified clock abstraction for timeline control.

Provides multiple clock implementations:
- MonotonicClock: real-time wall clock
- OfflineRenderClock: deterministic fixed-step clock
- FakeClock: manually advanced for testing
- VideoPtsClock: driven by video presentation timestamps
- AudioPlaybackClock: driven by audio playback position
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvIPCError


class ClockError(RuntimeError):
    """Base class for explicit clock failures."""


class MediaEnded(ClockError):
    """Raised when a media-owned clock reaches end of media."""


class ClockConnectionError(ClockError):
    """Raised when a clock cannot connect to its external time source."""


class Clock(ABC):
    """Abstract clock interface.

    All time values are in seconds (float).
    """

    @abstractmethod
    def now(self) -> float:
        """Get current clock time in seconds."""
        ...

    @abstractmethod
    def tick(self) -> float:
        """Advance clock and return new time. Returns delta_time."""
        ...

    def reset(self) -> None:
        """Reset clock to initial state."""
        pass

    @property
    def paused(self) -> bool:
        return False

    @property
    def ended(self) -> bool:
        return False


class MonotonicClock(Clock):
    """Real-time wall clock using time.perf_counter()."""

    def __init__(self):
        self._start = time.perf_counter()
        self._last = self._start

    def now(self) -> float:
        return time.perf_counter() - self._start

    def tick(self) -> float:
        now = self.now()
        dt = now - self._last
        self._last = now
        return max(0.0, dt)

    def reset(self) -> None:
        self._start = time.perf_counter()
        self._last = self._start


class OfflineRenderClock(Clock):
    """Deterministic fixed-step clock for offline rendering.

    Advances by a fixed delta_time each tick.
    Same input always produces same output.
    """

    def __init__(self, fps: float = 30.0):
        self._fps = fps
        self._delta = 1.0 / fps
        self._time: float = 0.0

    def now(self) -> float:
        return self._time

    def tick(self) -> float:
        self._time += self._delta
        return self._delta

    def reset(self) -> None:
        self._time = 0.0

    @property
    def delta(self) -> float:
        return self._delta


class FakeClock(Clock):
    """Manually advanced clock for testing.

    Allows tests to precisely control time progression.
    """

    def __init__(self, start_time: float = 0.0):
        self._time = start_time
        self._paused = False
        self._ended = False

    def now(self) -> float:
        return self._time

    def tick(self) -> float:
        return 0.0

    def advance(self, delta: float) -> float:
        """Manually advance time by delta seconds."""
        self._time += delta
        return delta

    def set_time(self, t: float) -> None:
        """Set absolute time."""
        self._time = t

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_ended(self, ended: bool) -> None:
        self._ended = ended

    def reset(self) -> None:
        self._time = 0.0
        self._paused = False
        self._ended = False

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def ended(self) -> bool:
        return self._ended


class MpvIPCClock(Clock):
    """Clock driven by mpv's JSON IPC playback-time property."""

    def __init__(self, ipc_path: str, adapter: Optional[MpvIPCAdapter] = None):
        self._adapter = adapter or MpvIPCAdapter(ipc_path)
        self._position = 0.0
        self._last_position = 0.0
        self._paused = False
        self._ended = False

    def connect(self) -> None:
        try:
            self._adapter.connect()
        except MpvIPCError as exc:
            raise ClockConnectionError(str(exc)) from exc

    def now(self) -> float:
        return self._position

    def tick(self) -> float:
        try:
            state = self._adapter.read_state()
        except MpvIPCError as exc:
            raise ClockError(str(exc)) from exc

        if state.ended:
            self._ended = True
            raise MediaEnded("mpv reported end of media")

        self._paused = state.paused
        self._last_position = self._position
        self._position = state.position
        if self._paused:
            return 0.0
        return max(0.0, self._position - self._last_position)

    def reset(self) -> None:
        self._position = 0.0
        self._last_position = 0.0
        self._paused = False
        self._ended = False

    def close(self) -> None:
        self._adapter.close()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def ended(self) -> bool:
        return self._ended


class VideoPtsClock(Clock):
    """Clock driven by video presentation timestamps.

    Handles variable frame rate by using actual PTS values.
    """

    def __init__(self):
        self._pts: float = 0.0
        self._last_pts: float = 0.0
        self._active: bool = False

    def now(self) -> float:
        return self._pts

    def tick(self) -> float:
        dt = self._pts - self._last_pts
        self._last_pts = self._pts
        return max(0.0, dt)

    def update_pts(self, pts: float) -> None:
        """Update from a new video PTS value."""
        self._last_pts = self._pts
        self._pts = pts
        self._active = True

    def reset(self) -> None:
        self._pts = 0.0
        self._last_pts = 0.0
        self._active = False

    @property
    def active(self) -> bool:
        return self._active


class AudioPlaybackClock(Clock):
    """Clock driven by audio playback position.

    Uses audio sample position and sample rate to compute time.
    """

    def __init__(self, sample_rate: int = 44100):
        self._sample_rate = sample_rate
        self._position: float = 0.0
        self._last_position: float = 0.0
        self._active: bool = False

    def now(self) -> float:
        return self._position

    def tick(self) -> float:
        dt = self._position - self._last_position
        self._last_position = self._position
        return max(0.0, dt)

    def update_samples(self, sample_offset: int) -> None:
        """Update from audio sample offset."""
        self._last_position = self._position
        self._position = sample_offset / self._sample_rate
        self._active = True

    def reset(self) -> None:
        self._position = 0.0
        self._last_position = 0.0
        self._active = False

    @property
    def active(self) -> bool:
        return self._active


class MasterClock:
    """Manages the primary clock source and tracks sync diagnostics.

    Handles the relationship between the master clock and media clocks.
    """

    def __init__(self, clock: Optional[Clock] = None):
        self._master = clock or MonotonicClock()
        self._video_clock: Optional[VideoPtsClock] = None
        self._audio_clock: Optional[AudioPlaybackClock] = None
        self._schedule_error: float = 0.0
        self._output_delay: float = 0.0

    @property
    def master(self) -> Clock:
        return self._master

    def set_video_clock(self, clock: VideoPtsClock) -> None:
        self._video_clock = clock

    def set_audio_clock(self, clock: AudioPlaybackClock) -> None:
        self._audio_clock = clock

    def now(self) -> float:
        return self._master.now()

    def tick(self) -> float:
        expected = 1.0 / 30.0  # nominal frame period
        t0 = time.perf_counter()
        dt = self._master.tick()
        actual = time.perf_counter() - t0
        self._schedule_error = actual - expected
        return dt

    def diagnostics(self) -> dict:
        """Return sync diagnostics for monitoring."""
        diag = {
            "master_clock_time": self.now(),
            "master_clock_type": type(self._master).__name__,
        }
        if self._video_clock is not None:
            diag["video_pts"] = self._video_clock.now()
            diag["video_active"] = self._video_clock.active
            diag["video_sync_error_ms"] = round(
                abs(self.now() - self._video_clock.now()) * 1000, 2
            )
        else:
            diag["video_pts"] = None
            diag["video_sync_error_ms"] = None

        if self._audio_clock is not None:
            diag["audio_pts"] = self._audio_clock.now()
            diag["audio_active"] = self._audio_clock.active
            diag["audio_sync_error_ms"] = round(
                abs(self.now() - self._audio_clock.now()) * 1000, 2
            )
        else:
            diag["audio_pts"] = None
            diag["audio_sync_error_ms"] = None

        diag["engine_schedule_error_ms"] = round(self._schedule_error * 1000, 2)
        diag["output_queue_delay_ms"] = round(self._output_delay * 1000, 2)
        return diag
