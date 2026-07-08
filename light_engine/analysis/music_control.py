"""Deterministic music-control feature derivation.

This module consumes existing :class:`AudioFeatures` values and produces a
bounded :class:`MusicControlState` stream. It does not select effects.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import asdict
from typing import Deque, Iterable

import numpy as np

from light_engine.models import AudioFeatures, MusicControlState
from light_engine.util import clamp


MIN_TEMPO_BPM = 60.0
MAX_TEMPO_BPM = 180.0
MIN_BEAT_INTERVAL = 60.0 / MAX_TEMPO_BPM
MAX_BEAT_INTERVAL = 60.0 / MIN_TEMPO_BPM


class MusicControlAnalyzer:
    """Causal bounded music-control feature extractor.

    History windows are fixed at 2s, 8s, and 30s with a 60 FPS sizing
    assumption plus margin. Storage is capped by frame count, so memory does
    not grow with song duration.
    """

    short_seconds = 2.0
    medium_seconds = 8.0
    long_seconds = 30.0
    assumed_fps = 60.0
    short_capacity = int(short_seconds * assumed_fps) + 8
    medium_capacity = int(medium_seconds * assumed_fps) + 8
    long_capacity = int(long_seconds * assumed_fps) + 8
    beat_capacity = 64

    def __init__(self) -> None:
        self._short: Deque[AudioFeatures] = deque(maxlen=self.short_capacity)
        self._medium: Deque[AudioFeatures] = deque(maxlen=self.medium_capacity)
        self._long: Deque[AudioFeatures] = deque(maxlen=self.long_capacity)
        self._beat_times: Deque[float] = deque(maxlen=self.beat_capacity)
        self._last_event_time: float | None = None
        self._bass_baseline = 0.0
        self._energy_smooth = 0.0
        self._energy_baseline = 0.0
        self._last_state = MusicControlState(timestamp=0.0)

    @property
    def history_bound(self) -> int:
        return (
            self.short_capacity
            + self.medium_capacity
            + self.long_capacity
            + self.beat_capacity
        )

    @property
    def history_size(self) -> int:
        return len(self._short) + len(self._medium) + len(self._long) + len(self._beat_times)

    def reset(self) -> None:
        self._short.clear()
        self._medium.clear()
        self._long.clear()
        self._beat_times.clear()
        self._last_event_time = None
        self._bass_baseline = 0.0
        self._energy_smooth = 0.0
        self._energy_baseline = 0.0
        self._last_state = MusicControlState(timestamp=0.0)

    def update(self, features: AudioFeatures) -> MusicControlState:
        self._short.append(features)
        self._medium.append(features)
        self._long.append(features)

        raw_energy = clamp(0.65 * features.rms + 0.35 * max(features.bass, features.mid, features.treble))
        self._energy_smooth = 0.75 * self._energy_smooth + 0.25 * raw_energy
        energy = clamp(self._energy_smooth)

        spectral_motion = clamp(0.7 * features.spectral_flux + 0.3 * features.onset)
        transient = self._transient(features, raw_energy)

        bass_excess = max(0.0, features.bass - self._bass_baseline)
        bass_pulse = clamp(bass_excess * 4.0)
        self._update_energy_baseline(raw_energy)
        self._update_bass_baseline(features.bass)
        bass_ambient = clamp(self._bass_baseline)

        event_strength = max(transient, bass_pulse, 1.0 if features.beat and transient > 0.25 else 0.0)
        if self._is_beat_event(features.timestamp, event_strength):
            self._beat_times.append(features.timestamp)
            self._last_event_time = features.timestamp

        tempo_bpm, tempo_confidence, beat_regularity = self._estimate_tempo()
        beat_phase = self._beat_phase(features.timestamp, tempo_bpm)
        energy_trend = self._energy_trend()

        state = MusicControlState(
            timestamp=features.timestamp,
            tempo_bpm=tempo_bpm,
            tempo_confidence=tempo_confidence,
            beat_phase=beat_phase,
            beat_strength=clamp(event_strength),
            beat_regularity=beat_regularity,
            energy=energy,
            energy_trend=energy_trend,
            transient=transient,
            bass_ambient=bass_ambient,
            bass_pulse=bass_pulse,
            spectral_motion=spectral_motion,
        )
        self._last_state = state
        return state

    def summary(self, states: Iterable[MusicControlState]) -> dict[str, float | int]:
        values = list(states)
        if not values:
            return {
                "frames": 0,
                "history_size": self.history_size,
                "history_bound": self.history_bound,
            }
        warmed = [state for state in values if state.timestamp >= 4.0] or values
        return {
            "frames": len(values),
            "duration_seconds": values[-1].timestamp,
            "history_size": self.history_size,
            "history_bound": self.history_bound,
            "tempo_bpm_median_after_warmup": _median(state.tempo_bpm for state in warmed),
            "tempo_confidence_mean_after_warmup": _mean(state.tempo_confidence for state in warmed),
            "beat_regularity_mean_after_warmup": _mean(state.beat_regularity for state in warmed),
            "energy_min": min(state.energy for state in values),
            "energy_max": max(state.energy for state in values),
            "energy_trend_mean_after_warmup": _mean(state.energy_trend for state in warmed),
            "transient_max": max(state.transient for state in values),
            "bass_ambient_max": max(state.bass_ambient for state in values),
            "bass_pulse_max": max(state.bass_pulse for state in values),
            "spectral_motion_max": max(state.spectral_motion for state in values),
        }

    def state_dict(self, state: MusicControlState) -> dict[str, float]:
        return asdict(state)

    def _transient(self, features: AudioFeatures, raw_energy: float) -> float:
        if len(self._short) < 4:
            return clamp(max(0.0, raw_energy - self._energy_baseline) * 3.0)
        recent_energy = [0.65 * item.rms + 0.35 * max(item.bass, item.mid, item.treble) for item in self._short]
        baseline = float(np.percentile(recent_energy, 60))
        energy_excess = max(0.0, raw_energy - max(baseline, self._energy_baseline))
        bass_excess = max(0.0, features.bass - self._bass_baseline)
        return clamp(max(energy_excess * 4.0, bass_excess * 3.0))

    def _update_energy_baseline(self, energy: float) -> None:
        if self._energy_baseline == 0.0:
            self._energy_baseline = energy
            return
        alpha = 0.985 if energy > self._energy_baseline else 0.90
        self._energy_baseline = clamp(alpha * self._energy_baseline + (1.0 - alpha) * energy)

    def _update_bass_baseline(self, bass: float) -> None:
        if self._bass_baseline == 0.0:
            self._bass_baseline = bass
            return
        alpha = 0.985 if bass > self._bass_baseline else 0.90
        self._bass_baseline = clamp(alpha * self._bass_baseline + (1.0 - alpha) * bass)

    def _is_beat_event(self, timestamp: float, strength: float) -> bool:
        if strength < 0.55:
            return False
        if self._last_event_time is None:
            return True
        return (timestamp - self._last_event_time) >= MIN_BEAT_INTERVAL * 0.72

    def _estimate_tempo(self) -> tuple[float, float, float]:
        times = list(self._beat_times)
        if len(times) < 4:
            return 0.0, 0.0, 0.0

        intervals = np.diff(np.array(times, dtype=np.float64))
        intervals = intervals[(intervals >= MIN_BEAT_INTERVAL) & (intervals <= MAX_BEAT_INTERVAL)]
        if len(intervals) < 3:
            return 0.0, 0.0, 0.0

        median_interval = float(np.median(intervals))
        tempo_bpm = clamp(60.0 / median_interval, MIN_TEMPO_BPM, MAX_TEMPO_BPM)
        deviations = np.abs(intervals - median_interval)
        tolerance = max(0.035, median_interval * 0.12)
        inliers = deviations <= tolerance
        inlier_ratio = float(np.mean(inliers))
        regularity = clamp(1.0 - float(np.median(deviations)) / tolerance)
        evidence = clamp((len(intervals) - 2) / 8.0)
        confidence = clamp(inlier_ratio * regularity * evidence)
        if confidence < 0.18:
            tempo_bpm = 0.0
        return tempo_bpm, confidence, regularity

    def _beat_phase(self, timestamp: float, tempo_bpm: float) -> float:
        if tempo_bpm <= 0.0 or not self._beat_times:
            return 0.0
        period = 60.0 / tempo_bpm
        elapsed = max(0.0, timestamp - self._beat_times[-1])
        return clamp((elapsed % period) / period)

    def _energy_trend(self) -> float:
        if len(self._medium) < 8:
            return 0.0
        energies = np.array(
            [0.65 * item.rms + 0.35 * max(item.bass, item.mid, item.treble) for item in self._medium],
            dtype=np.float64,
        )
        split = max(1, len(energies) // 3)
        early = float(np.mean(energies[:split]))
        late = float(np.mean(energies[-split:]))
        return clamp((late - early) * 2.5, -1.0, 1.0)


def _mean(values: Iterable[float]) -> float:
    data = list(values)
    return float(sum(data) / len(data)) if data else 0.0


def _median(values: Iterable[float]) -> float:
    data = list(values)
    return float(np.median(data)) if data else 0.0
