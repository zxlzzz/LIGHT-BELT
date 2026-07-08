"""Immutable show-domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def frozen_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an immutable shallow copy of a mapping."""
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class TargetSelector:
    kind: str
    id: str | None = None
    ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EffectSpec:
    mode: str
    name: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    allowed: Mapping[str, str] = field(default_factory=dict)
    fallback: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", frozen_mapping(self.parameters))
        object.__setattr__(self, "allowed", frozen_mapping(self.allowed))


@dataclass(frozen=True)
class TransitionSpec:
    fade_in: float = 0.0
    fade_out: float = 0.0
    blend: str = "replace"
    min_effect_hold: float | None = None
    switch_cooldown: float | None = None


@dataclass(frozen=True)
class AudioControlSpec:
    tempo_sync: str = "off"
    tempo_confidence_min: float = 0.0
    beat_regularity_min: float = 0.0
    no_beat_fallback: str = "hold"
    beats_per_cycle: float | None = None
    speed_smoothing_seconds: float = 0.0
    state_confirmation_seconds: float = 0.0
    min_effect_hold: float = 0.0
    switch_cooldown: float = 0.0


@dataclass(frozen=True)
class Cue:
    id: str
    start: float
    end: float
    target: TargetSelector
    effect: EffectSpec
    priority: int = 0
    transition: TransitionSpec = field(default_factory=TransitionSpec)
    audio_control: AudioControlSpec | None = None


@dataclass(frozen=True)
class ShowDefinition:
    schema_version: int
    id: str
    duration: float
    cues: tuple[Cue, ...]
    defaults: TransitionSpec = field(default_factory=TransitionSpec)
