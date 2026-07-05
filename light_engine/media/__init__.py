"""Media I/O: video and audio file reading, frame sampling, audio windowing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import soundfile as sf

from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvIPCError, MpvState

logger = logging.getLogger(__name__)

__all__ = [
    "AudioReader",
    "MpvIPCAdapter",
    "MpvIPCError",
    "MpvState",
    "VideoReader",
]


class VideoReader:
    """Read video files and provide frame sampling."""

    def __init__(self, path: str):
        if not Path(path).exists():
            raise FileNotFoundError(f"Video file not found: {path}")
        self._path = path
        self._cap: Optional[cv2.VideoCapture] = None
        self._fps: float = 30.0
        self._total_frames: int = 0
        self._width: int = 0
        self._height: int = 0
        self._current_frame: int = 0

    def open(self) -> VideoReader:
        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self._path}")
        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(
            "Video opened: %s (%dx%d, %.1f fps, %d frames)",
            self._path, self._width, self._height, self._fps, self._total_frames,
        )
        return self

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def duration(self) -> float:
        return self._total_frames / max(0.001, self._fps)

    @property
    def resolution(self) -> Tuple[int, int]:
        return (self._width, self._height)

    def read_frame(self, timestamp: Optional[float] = None) -> Optional[np.ndarray]:
        """Read the next frame, or seek to timestamp.

        Returns BGR frame as numpy array, or None if at end.
        """
        if self._cap is None:
            return None
        if timestamp is not None:
            self._cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ret, frame = self._cap.read()
        if not ret:
            return None
        self._current_frame = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        return frame

    def seek(self, timestamp: float) -> bool:
        """Seek to a specific timestamp in seconds."""
        if self._cap is None:
            return False
        return self._cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()


class AudioReader:
    """Read audio files and provide windowed sample access."""

    def __init__(self, path: str):
        if not Path(path).exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        self._path = path
        self._data: Optional[np.ndarray] = None
        self._sample_rate: int = 44100
        self._channels: int = 1
        self._duration: float = 0.0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def channels(self) -> int:
        return self._channels

    def open(self) -> AudioReader:
        try:
            self._data, self._sample_rate = sf.read(self._path, dtype="float32")
        except Exception as e:
            raise RuntimeError(f"Cannot open audio: {self._path}") from e
        if self._data.ndim == 1:
            self._channels = 1
        else:
            self._channels = self._data.shape[1]
            # Mix down to mono in-place to avoid doubling memory.
            # Use the first channel weighted 0.5, then accumulate the rest.
            mono = self._data[:, 0].copy()
            for ch in range(1, self._channels):
                mono += self._data[:, ch]
            mono /= self._channels
            self._data = mono
        self._duration = len(self._data) / max(1, self._sample_rate)
        logger.info(
            "Audio opened: %s (%.1f Hz, %d ch, %.1f s)",
            self._path, self._sample_rate, self._channels, self._duration,
        )
        return self

    def get_window(
        self, center_time: float, window_size: float
    ) -> Optional[np.ndarray]:
        """Get audio samples centered at center_time with given window size.

        Args:
            center_time: Center time in seconds.
            window_size: Window size in seconds.

        Returns:
            1D numpy array of samples, or None if outside audio range.
        """
        if self._data is None:
            return None
        half = window_size / 2
        start = int((center_time - half) * self._sample_rate)
        end = int((center_time + half) * self._sample_rate)
        if start < 0:
            start = 0
        if end > len(self._data):
            end = len(self._data)
        if start >= end:
            return None
        return self._data[start:end].copy()

    def get_window_at(
        self, start_time: float, window_size: float
    ) -> Optional[np.ndarray]:
        """Get audio samples starting at start_time.

        Uses round() for start and a fixed integer window_sample count
        to guarantee consistent window length for every call except
        the final truncated window at end-of-file.
        """
        if self._data is None:
            return None
        window_samples = round(window_size * self._sample_rate)
        start = round(start_time * self._sample_rate)
        end = start + window_samples
        if start < 0:
            start = 0
            end = min(window_samples, len(self._data))
        if start >= len(self._data):
            return None
        end = min(end, len(self._data))
        return self._data[start:end].copy()

    def close(self) -> None:
        self._data = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()
