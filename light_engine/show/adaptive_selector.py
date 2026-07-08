"""Cue-bounded adaptive effect selection from MusicControlState.

Decision table:

State classification, in priority order, uses only MusicControlState:

1. silence: energy <= 0.03 and transient <= 0.05
2. impact: bass_pulse >= 0.65 or transient >= 0.85, with energy >= 0.15
3. energetic: energy >= 0.72 and spectral_motion >= 0.35
4. rhythmic: tempo confidence and beat regularity meet the cue thresholds,
   and beat_strength >= 0.35
5. transition: abs(energy_trend) >= 0.25 or spectral_motion >= 0.50
6. ambient: bass_ambient >= 0.55 and bass_pulse < 0.35
7. flowing: energy >= 0.18, spectral_motion >= 0.18, or
   abs(energy_trend) >= 0.12
8. calm: energy >= 0.04
9. silence fallback

Sync selection, in priority order:

1. BEAT_CONFIDENT -> beat_sync when tempo and regularity meet thresholds.
2. EVENT_FALLBACK -> event_sync when transient/onset evidence is sufficient.
3. ENVELOPE_FALLBACK -> envelope_sync when trend or spectral motion is useful.
4. FREE_RUN_FALLBACK -> free_run otherwise.

Switch state machine:

candidate state -> confirmation timer -> confirmed state -> allowed mapping
-> hold/cooldown gates -> selected effect. Missing active-state mapping uses
the explicit cue fallback validated by the loader.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from light_engine.models import MusicControlState
from light_engine.show.models import AudioControlSpec, Cue


MUSIC_STATES = frozenset(
    {
        "silence",
        "calm",
        "flowing",
        "rhythmic",
        "energetic",
        "impact",
        "transition",
        "ambient",
    }
)
SYNC_MODES = frozenset({"beat_sync", "event_sync", "envelope_sync", "free_run"})
REASON_CODES = frozenset(
    {
        "BEAT_CONFIDENT",
        "EVENT_FALLBACK",
        "ENVELOPE_FALLBACK",
        "FREE_RUN_FALLBACK",
        "FIXED_CUE",
        "HOLD_ACTIVE",
        "COOLDOWN_ACTIVE",
        "STATE_UNCONFIRMED",
    }
)

DEFAULT_FREE_RUN_SPEED = 1.0
MIN_SPEED = 0.1
MAX_SPEED = 4.0
REFERENCE_PERIOD_SECONDS = 4.0


@dataclass(frozen=True)
class SelectionDecision:
    show_time: float
    music_state: str
    sync_mode: str
    selected_effect: str
    previous_effect: str | None
    source_features: Mapping[str, float]
    hold_active: bool
    cooldown_active: bool
    confirmation_active: bool
    reason_code: str
    tempo_period: float | None
    speed: float

    def __post_init__(self) -> None:
        if self.music_state not in MUSIC_STATES:
            raise ValueError(f"unknown music state {self.music_state!r}")
        if self.sync_mode not in SYNC_MODES:
            raise ValueError(f"unknown sync mode {self.sync_mode!r}")
        if self.reason_code not in REASON_CODES:
            raise ValueError(f"unknown reason code {self.reason_code!r}")
        for name, value in self.source_features.items():
            if not math.isfinite(float(value)):
                raise ValueError(f"source feature {name} must be finite")
        object.__setattr__(
            self, "source_features", MappingProxyType(dict(self.source_features))
        )


@dataclass(frozen=True)
class _SyncChoice:
    mode: str
    reason_code: str
    tempo_period: float | None
    target_speed: float


class AdaptiveEffectSelector:
    """Stateful selector for one adaptive cue."""

    def __init__(self, cue: Cue):
        if cue.effect.mode != "adaptive":
            raise ValueError("AdaptiveEffectSelector requires an adaptive cue")
        if cue.effect.fallback is None:
            raise ValueError("adaptive cue requires an explicit fallback")
        self._cue = cue
        self._current_effect: str | None = None
        self._confirmed_state: str | None = None
        self._pending_state: str | None = None
        self._pending_since: float | None = None
        self._last_switch_time: float | None = None
        self._last_tempo_period: float | None = None
        self._speed = DEFAULT_FREE_RUN_SPEED
        self.last_decision: SelectionDecision | None = None

    def reset(self) -> None:
        self._current_effect = None
        self._confirmed_state = None
        self._pending_state = None
        self._pending_since = None
        self._last_switch_time = None
        self._last_tempo_period = None
        self._speed = DEFAULT_FREE_RUN_SPEED
        self.last_decision = None

    def evaluate(
        self, show_time: float, state: MusicControlState | None
    ) -> SelectionDecision:
        control = state or MusicControlState(timestamp=show_time)
        audio = self._cue.audio_control or AudioControlSpec()
        candidate_state = classify_music_state(control, audio)
        confirmed_state, confirmation_active = self._confirm_state(
            show_time, candidate_state, audio.state_confirmation_seconds
        )
        elapsed = _elapsed_since(
            self.last_decision.show_time if self.last_decision else None, show_time
        )
        sync = choose_sync(control, audio, self._last_tempo_period, self._speed)
        smoothed_period = _smooth_period(
            current=self._last_tempo_period,
            target=sync.tempo_period,
            elapsed=elapsed,
            smoothing_seconds=audio.speed_smoothing_seconds,
        )
        if sync.mode == "beat_sync":
            sync = _SyncChoice(
                sync.mode,
                sync.reason_code,
                smoothed_period,
                _speed_for_period(smoothed_period),
            )
        self._last_tempo_period = smoothed_period
        self._speed = _smooth_speed(
            current=self._speed,
            target=sync.target_speed,
            elapsed=elapsed,
            smoothing_seconds=audio.speed_smoothing_seconds,
        )

        previous = self._current_effect
        target_effect = _effect_for_state(self._cue, confirmed_state)
        hold_active = _gate_active(
            show_time,
            self._last_switch_time,
            _hold_seconds(self._cue, audio),
        )
        cooldown_active = _gate_active(
            show_time,
            self._last_switch_time,
            _cooldown_seconds(self._cue, audio),
        )
        reason_code = sync.reason_code
        selected = target_effect
        if previous is None:
            self._current_effect = target_effect
            self._last_switch_time = show_time
            selected = target_effect
        elif confirmation_active:
            selected = previous
            reason_code = "STATE_UNCONFIRMED"
        elif target_effect != previous and hold_active:
            selected = previous
            reason_code = "HOLD_ACTIVE"
        elif target_effect != previous and cooldown_active:
            selected = previous
            reason_code = "COOLDOWN_ACTIVE"
        elif target_effect != previous:
            self._current_effect = target_effect
            self._last_switch_time = show_time
            selected = target_effect
        else:
            selected = previous

        decision = SelectionDecision(
            show_time=show_time,
            music_state=confirmed_state,
            sync_mode=sync.mode,
            selected_effect=selected,
            previous_effect=previous,
            source_features=_snapshot(control),
            hold_active=hold_active,
            cooldown_active=cooldown_active,
            confirmation_active=confirmation_active,
            reason_code=reason_code,
            tempo_period=sync.tempo_period,
            speed=self._speed,
        )
        self.last_decision = decision
        return decision

    def _confirm_state(
        self, show_time: float, candidate: str, confirmation_seconds: float
    ) -> tuple[str, bool]:
        if self._confirmed_state is None:
            self._confirmed_state = candidate
            self._pending_state = candidate
            self._pending_since = show_time
            return candidate, False
        if candidate == self._confirmed_state:
            self._pending_state = candidate
            self._pending_since = show_time
            return self._confirmed_state, False
        if candidate != self._pending_state:
            self._pending_state = candidate
            self._pending_since = show_time
        assert self._pending_since is not None
        if show_time - self._pending_since >= confirmation_seconds:
            self._confirmed_state = candidate
            return candidate, False
        return self._confirmed_state, True


def classify_music_state(state: MusicControlState, audio: AudioControlSpec) -> str:
    beat_ready = _beat_ready(state, audio)
    if state.energy <= 0.03 and state.transient <= 0.05:
        return "silence"
    if state.energy >= 0.15 and (state.bass_pulse >= 0.65 or state.transient >= 0.85):
        return "impact"
    if state.energy >= 0.72 and state.spectral_motion >= 0.35:
        return "energetic"
    if beat_ready and state.beat_strength >= 0.35:
        return "rhythmic"
    if abs(state.energy_trend) >= 0.25 or state.spectral_motion >= 0.50:
        return "transition"
    if state.bass_ambient >= 0.55 and state.bass_pulse < 0.35:
        return "ambient"
    if (
        state.energy >= 0.18
        or state.spectral_motion >= 0.18
        or abs(state.energy_trend) >= 0.12
    ):
        return "flowing"
    if state.energy >= 0.04:
        return "calm"
    return "silence"


def choose_sync(
    state: MusicControlState,
    audio: AudioControlSpec,
    previous_period: float | None,
    previous_speed: float,
) -> _SyncChoice:
    if _beat_ready(state, audio):
        period = _tempo_period(state, audio)
        target_speed = _speed_for_period(period)
        return _SyncChoice("beat_sync", "BEAT_CONFIDENT", period, target_speed)
    if state.transient >= 0.45 or state.bass_pulse >= 0.45:
        return _SyncChoice("event_sync", "EVENT_FALLBACK", previous_period, max(previous_speed, MIN_SPEED))
    if abs(state.energy_trend) >= 0.08 or state.spectral_motion >= 0.12:
        target = _bounded_speed(1.0 + state.energy_trend * 0.5 + state.spectral_motion * 0.5)
        return _SyncChoice("envelope_sync", "ENVELOPE_FALLBACK", previous_period, target)
    return _SyncChoice("free_run", "FREE_RUN_FALLBACK", previous_period, DEFAULT_FREE_RUN_SPEED)


def fixed_decision(cue: Cue, show_time: float) -> SelectionDecision:
    if cue.effect.mode != "fixed" or cue.effect.name is None:
        raise ValueError("fixed_decision requires a fixed cue")
    return SelectionDecision(
        show_time=show_time,
        music_state="silence",
        sync_mode="free_run",
        selected_effect=cue.effect.name,
        previous_effect=cue.effect.name,
        source_features=_snapshot(MusicControlState(timestamp=show_time)),
        hold_active=False,
        cooldown_active=False,
        confirmation_active=False,
        reason_code="FIXED_CUE",
        tempo_period=None,
        speed=DEFAULT_FREE_RUN_SPEED,
    )


def _beat_ready(state: MusicControlState, audio: AudioControlSpec) -> bool:
    return (
        audio.tempo_sync != "off"
        and state.tempo_bpm > 0.0
        and state.tempo_confidence >= audio.tempo_confidence_min
        and state.beat_regularity >= audio.beat_regularity_min
    )


def _tempo_period(state: MusicControlState, audio: AudioControlSpec) -> float:
    beats = audio.beats_per_cycle if audio.beats_per_cycle is not None else 4.0
    subdivision = audio.beat_subdivision
    quantized_beats = max(subdivision, round(beats / subdivision) * subdivision)
    return quantized_beats * 60.0 / state.tempo_bpm


def _speed_for_period(period: float | None) -> float:
    if period is None or period <= 0.0:
        return DEFAULT_FREE_RUN_SPEED
    return _bounded_speed(REFERENCE_PERIOD_SECONDS / period)


def _smooth_speed(
    *, current: float, target: float, elapsed: float, smoothing_seconds: float
) -> float:
    target = _bounded_speed(target)
    current = _bounded_speed(current)
    if smoothing_seconds <= 0.0 or elapsed <= 0.0:
        return target
    alpha = min(1.0, elapsed / smoothing_seconds)
    return _bounded_speed(current + (target - current) * alpha)


def _smooth_period(
    *,
    current: float | None,
    target: float | None,
    elapsed: float,
    smoothing_seconds: float,
) -> float | None:
    if target is None:
        return current
    if current is None or smoothing_seconds <= 0.0 or elapsed <= 0.0:
        return target
    alpha = min(1.0, elapsed / smoothing_seconds)
    return current + (target - current) * alpha


def _bounded_speed(value: float) -> float:
    if not math.isfinite(value):
        return DEFAULT_FREE_RUN_SPEED
    return min(MAX_SPEED, max(MIN_SPEED, value))


def _elapsed_since(previous: float | None, current: float) -> float:
    if previous is None:
        return 0.0
    return max(0.0, current - previous)


def _effect_for_state(cue: Cue, state: str) -> str:
    effect_name = cue.effect.allowed.get(state)
    if effect_name is not None:
        return effect_name
    assert cue.effect.fallback is not None
    return cue.effect.fallback


def _hold_seconds(cue: Cue, audio: AudioControlSpec) -> float:
    if audio.min_effect_hold > 0.0:
        return audio.min_effect_hold
    return cue.transition.min_effect_hold or 0.0


def _cooldown_seconds(cue: Cue, audio: AudioControlSpec) -> float:
    if audio.switch_cooldown > 0.0:
        return audio.switch_cooldown
    return cue.transition.switch_cooldown or 0.0


def _gate_active(show_time: float, last_switch: float | None, seconds: float) -> bool:
    return last_switch is not None and seconds > 0.0 and show_time - last_switch < seconds


def _snapshot(state: MusicControlState) -> Mapping[str, float]:
    return {
        "timestamp": float(state.timestamp),
        "tempo_bpm": float(state.tempo_bpm),
        "tempo_confidence": float(state.tempo_confidence),
        "beat_phase": float(state.beat_phase),
        "beat_strength": float(state.beat_strength),
        "beat_regularity": float(state.beat_regularity),
        "energy": float(state.energy),
        "energy_trend": float(state.energy_trend),
        "transient": float(state.transient),
        "bass_ambient": float(state.bass_ambient),
        "bass_pulse": float(state.bass_pulse),
        "spectral_motion": float(state.spectral_motion),
    }
