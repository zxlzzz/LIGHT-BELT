"""Core engine: unified timeline, feature fusion, effect management, output routing."""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from light_engine.analysis import AudioAnalyzer, VideoAnalyzer
from light_engine.clock import Clock, ClockError, MediaEnded, OfflineRenderClock
from light_engine.config import Config
from light_engine.effects.base import BaseEffect, create_effect, list_effects
from light_engine.mapping import Layout, ZoneDef, PhysicalMapping
from light_engine.media import AudioReader, VideoReader
from light_engine.models import (
    AudioFeatures,
    EffectContext,
    PixelFrame,
    VideoFeatures,
)
from light_engine.outputs import (
    LightOutput,
    create_outputs,
    open_all,
    send_all,
    close_all,
    health_summary,
)
from light_engine.outputs.transform import OutputTransform
from light_engine.data.generators import SyntheticDataSource
from light_engine.show.compositor import ShowRuntime, black_base_frame

logger = logging.getLogger(__name__)


class Engine:
    """Main lighting engine orchestrating analysis, effects, and output."""

    def __init__(self, config: Optional[Config] = None, clock: Optional[Clock] = None):
        if config is None:
            config = Config.get_instance()
        self._config = config

        # Rates
        self._output_fps = config.get("system.output_fps", 30.0)
        self._video_fps = config.get("system.video_analysis_fps", 10.0)
        self._audio_fps = config.get("system.audio_update_fps", 60.0)

        # Layout
        self._layout = Layout.from_config(config)
        self._physical_mapping = PhysicalMapping(self._layout)

        # Analyzers (lazy init)
        self._video_analyzer: Optional[VideoAnalyzer] = None
        self._audio_analyzer: Optional[AudioAnalyzer] = None

        # Media readers
        self._video_reader: Optional[VideoReader] = None
        self._audio_reader: Optional[AudioReader] = None

        # Data source
        self._data_source: Optional[SyntheticDataSource] = None

        # Current effect
        self._effect: Optional[BaseEffect] = None
        self._effect_name: str = ""
        self._show_runtime: Optional[ShowRuntime] = None

        # Outputs
        self._outputs: dict[str, LightOutput] = {}
        self._output_transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness", 0.85)
        )
        self._clock: Clock = clock or OfflineRenderClock(fps=self._output_fps)

        # State
        self._running = False
        self._timestamp: float = 0.0
        self._last_clock_time: float = self._clock.now()
        self._frame_count: int = 0
        self._sequence: int = 0
        self._fps_stats: list[float] = []
        self._run_start_wall: float = 0.0
        self._run_end_wall: float = 0.0

        # Latest features
        self._latest_video: Optional[VideoFeatures] = None
        self._latest_audio: Optional[AudioFeatures] = None

        # Diagnostic state
        self._diagnostics: dict = {
            "running": False,
            "mode": "",
            "fps": 0.0,
            "media_position": 0.0,
            "video_available": False,
            "audio_available": False,
            "output_health": {},
            "last_error": None,
        }

        # Strip and zone definitions for effects
        self._strip_defs = [
            {
                "id": s.id,
                "pixel_count": s.pixel_count,
                "video_zone": s.video_zone,
                "direction": s.direction,
            }
            for s in self._layout.strips
        ]
        self._zone_defs = [
            {
                "id": z.id,
                "video_zone": z.video_zone,
                "direction": z.direction,
            }
            for z in self._layout.zones
        ]

    # ---- Setup methods ----

    def use_synthetic(self, seed: int = 42) -> None:
        """Use synthetic/generative data for demo/testing."""
        self._data_source = SyntheticDataSource(seed=seed)

    def load_video(self, path: str) -> None:
        """Load a video file for analysis."""
        self._video_reader = VideoReader(path).open()
        self._video_analyzer = VideoAnalyzer(self._config)

    def load_audio(self, path: str) -> None:
        """Load an audio file for analysis."""
        self._audio_reader = AudioReader(path).open()
        self._audio_analyzer = AudioAnalyzer(self._config)

    def set_effect(self, name: str) -> BaseEffect:
        """Set the active lighting effect."""
        self._effect = create_effect(name)
        self._effect_name = name
        self._show_runtime = None
        self._diagnostics["mode"] = name
        logger.info("Effect set to: %s", name)
        return self._effect

    def set_show_runtime(self, runtime: ShowRuntime) -> None:
        """Use an explicit show runtime instead of the single-effect path."""
        self._show_runtime = runtime
        self._effect = None
        self._effect_name = runtime.show.id
        self._diagnostics["mode"] = runtime.show.id

    def reset(self) -> None:
        """Explicitly reset stateful runtime components before replaying from start."""
        self._handle_timeline_reset()
        self._timestamp = 0.0
        self._last_clock_time = self._clock.now()

    def init_outputs(self) -> None:
        """Initialize output backends from config."""
        self._outputs = create_outputs(self._config)
        open_all(self._outputs)

    # ---- Main loop ----

    def run(
        self,
        duration: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> None:
        """Run the main lighting loop.

        Args:
            duration: Maximum run duration in seconds.
            max_frames: Maximum number of output frames.
        """
        if self._effect is None and self._show_runtime is None:
            self.set_effect(self._config.get("effects.active", "demo"))

        if not self._outputs:
            self.init_outputs()

        self._running = True
        self._diagnostics["running"] = True
        self._diagnostics["video_available"] = self._video_reader is not None
        self._diagnostics["audio_available"] = self._audio_reader is not None

        frame_period = 1.0 / self._output_fps
        video_period = 1.0 / self._video_fps if self._video_fps > 0 else 0.1
        audio_period = 1.0 / self._audio_fps if self._audio_fps > 0 else 0.016

        last_video_time = -video_period
        last_audio_time = -audio_period
        self._run_start_wall = time.perf_counter()

        try:
            while self._running:
                frame_start = time.perf_counter()
                dt = self._clock.tick()
                self._timestamp = self._clock.now()
                clock_delta = self._timestamp - self._last_clock_time
                if dt <= 0.0:
                    dt = max(0.0, clock_delta)
                if clock_delta < -frame_period:
                    raise RuntimeError(
                        "engine clock moved backward; call reset/replay before rendering earlier show time"
                    )
                seek_detected = dt > frame_period * 2
                paused = self._clock.paused or dt < frame_period * 0.1
                if self._clock.ended:
                    break

                if seek_detected:
                    self._handle_timeline_reset()
                    last_video_time = -video_period
                    last_audio_time = -audio_period
                self._last_clock_time = self._timestamp

                # Check stop conditions
                if duration is not None and self._timestamp >= duration:
                    break
                if max_frames is not None and self._frame_count >= max_frames:
                    break

                # Determine if each attached media source has finished.
                # A source is "finished" when timestamp >= its duration.
                # With no source attached, we rely on explicit duration / max_frames.
                video_finished = (
                    self._timestamp >= self._video_reader.duration
                    if self._video_reader is not None
                    else True  # no video → not a limiting factor
                )
                audio_finished = (
                    self._timestamp >= self._audio_reader.duration
                    if self._audio_reader is not None
                    else True
                )
                data_finished = (
                    self._timestamp >= self._data_source.duration()
                    if self._data_source is not None
                    else True
                )

                has_any_media = (
                    self._video_reader is not None
                    or self._audio_reader is not None
                    or self._data_source is not None
                )

                if has_any_media and video_finished and audio_finished and data_finished:
                    break

                # Video analysis
                if not paused and self._timestamp - last_video_time >= video_period:
                    self._latest_video = self._get_video_features()
                    last_video_time = self._timestamp

                # Audio analysis
                if not paused and self._timestamp - last_audio_time >= audio_period:
                    self._latest_audio = self._get_audio_features()
                    last_audio_time = self._timestamp

                # Build context and run effect
                self._sequence += 1
                context_dt = dt if dt > 0.0 else 1e-9
                ctx = EffectContext(
                    timestamp=self._timestamp,
                    delta_time=context_dt,
                    sequence=self._sequence,
                    video_features=self._latest_video,
                    audio_features=self._latest_audio,
                    mode_parameters={
                        "strip_defs": self._strip_defs,
                        "zone_defs": self._zone_defs,
                    },
                )
                if self._show_runtime is None:
                    if self._effect is None:
                        raise RuntimeError("single-effect engine path has no active effect")
                    frame = self._effect.process(ctx)
                else:
                    base = black_base_frame(
                        timestamp=self._timestamp,
                        sequence=self._sequence,
                        analog_zones=self._layout.zones,
                        digital_strips=self._layout.strips,
                    )
                    frame = self._show_runtime.render(ctx, base)
                frame = self._output_transform.apply_to_frame(frame)
                physical_frame = self._physical_mapping.map(frame)

                # Send to outputs
                send_all(self._outputs, physical_frame)

                # Update diagnostics
                self._frame_count += 1
                elapsed = time.perf_counter() - frame_start
                self._fps_stats.append(elapsed)
                self._diagnostics["fps"] = 1.0 / max(0.0001, elapsed)
                self._diagnostics["media_position"] = self._timestamp

                # Frame rate control
                sleep_time = frame_period - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Engine interrupted by user")
        except MediaEnded:
            logger.info("Media clock reached end of media")
        except ClockError as e:
            logger.exception("Engine clock error")
            self._diagnostics["last_error"] = str(e)
            raise
        except Exception as e:
            logger.exception("Engine error")
            self._diagnostics["last_error"] = str(e)
            raise
        finally:
            self._shutdown()

    def _handle_timeline_reset(self) -> None:
        """Reset stateful analysis/effect components after a media seek."""
        if self._video_analyzer is not None and hasattr(self._video_analyzer, "reset"):
            self._video_analyzer.reset()
        if self._audio_analyzer is not None and hasattr(self._audio_analyzer, "reset"):
            self._audio_analyzer.reset()
        if self._effect is not None:
            self._effect.reset()
        if self._show_runtime is not None:
            self._show_runtime.reset()
        self._latest_video = None
        self._latest_audio = None

    def _get_video_features(self) -> Optional[VideoFeatures]:
        """Get latest video features from reader or synthetic source."""
        if self._video_reader and self._video_analyzer:
            frame = self._video_reader.read_frame(self._timestamp)
            if frame is not None:
                return self._video_analyzer.analyze(frame, self._timestamp)
        if self._data_source:
            return self._data_source.get_video_features(self._timestamp)
        return None

    def _get_audio_features(self) -> Optional[AudioFeatures]:
        """Get latest audio features from reader or synthetic source."""
        if self._audio_reader and self._audio_analyzer:
            window = self._config.get("system.audio.window_size", 0.05)
            samples = self._audio_reader.get_window_at(self._timestamp, window)
            if samples is not None and len(samples) > 0:
                return self._audio_analyzer.analyze(
                    samples, self._timestamp, self._audio_reader.sample_rate
                )
        if self._data_source:
            return self._data_source.get_audio_features(self._timestamp)
        return None

    def _shutdown(self) -> None:
        """Clean shutdown of all resources."""
        self._running = False
        self._run_end_wall = time.perf_counter()
        try:
            self._sequence += 1
            safe_frame = OutputTransform.generate_safe_frame(
                timestamp=self._timestamp,
                sequence=self._sequence,
                zone_ids=[zone["id"] for zone in self._zone_defs],
                strips=self._strip_defs,
            )
            physical_safe_frame = self._physical_mapping.map(safe_frame)
            send_all(self._outputs, physical_safe_frame)
        except Exception as e:
            logger.exception("Failed to send shutdown safe frame")
            self._diagnostics["last_error"] = str(e)
        close_all(self._outputs)
        if self._video_reader:
            self._video_reader.close()
        if self._audio_reader:
            self._audio_reader.close()
        self._diagnostics["running"] = False

    # ---- Info ----

    def diagnostics(self) -> dict:
        """Return current diagnostic state."""
        self._diagnostics["output_health"] = health_summary(self._outputs)
        return self._diagnostics

    def get_fps_stats(self) -> dict:
        """Return FPS statistics.

        effective_fps: actual output frames / wall-clock duration (includes sleep).
        processing_capacity: raw compute speed based on per-frame processing time.
        """
        wall_time = max(0.001, self._run_end_wall - self._run_start_wall)
        effective_fps = self._frame_count / wall_time

        result: dict = {
            "effective_fps": effective_fps,
            "processing_capacity": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "wall_time_s": wall_time,
            "frame_count": self._frame_count,
        }
        if self._fps_stats:
            times_ms = np.array(self._fps_stats) * 1000
            result["processing_capacity"] = 1.0 / max(0.0001, np.mean(self._fps_stats))
            result["p50_ms"] = float(np.percentile(times_ms, 50))
            result["p95_ms"] = float(np.percentile(times_ms, 95))
            result["p99_ms"] = float(np.percentile(times_ms, 99))
        return result

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def timestamp(self) -> float:
        return self._timestamp
