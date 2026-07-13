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
class ColorSpec:
    """Cue-authored color policy, independent from the selected effect."""

    mode: str = "effect_default"
    color: tuple[float, float, float] | None = None
    palette: tuple[tuple[float, float, float], ...] = ()


@dataclass(frozen=True)
class VirtualPathSpec:
    """A hardware-agnostic ordered path through logical targets."""

    id: str
    targets: tuple[TargetSelector, ...]
    origin: str = "start"


@dataclass(frozen=True)
class CueBranchSpec:
    """Bounded release from one authored path member to one target set."""

    path_id: str
    after_target_id: str
    target: TargetSelector
    origin: str = "start"


@dataclass(frozen=True, init=False)
class EffectSpec:
    mode: str
    id: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    allowed: Mapping[str, str] = field(default_factory=dict)
    fallback: str | None = None

    def __init__(
        self,
        mode: str,
        id: str | None = None,
        params: Mapping[str, Any] | None = None,
        allowed: Mapping[str, str] | None = None,
        fallback: str | None = None,
        *,
        name: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        if id is not None and name is not None:
            raise TypeError("EffectSpec accepts id or legacy name, not both")
        if params is not None and parameters is not None:
            raise TypeError("EffectSpec accepts params or legacy parameters, not both")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "id", id if id is not None else name)
        object.__setattr__(self, "params", frozen_mapping(params if params is not None else (parameters or {})))
        object.__setattr__(self, "allowed", frozen_mapping(allowed or {}))
        object.__setattr__(self, "fallback", fallback)

    @property
    def name(self) -> str | None:
        """Read-only v1 compatibility alias; new authoring uses ``id``."""
        return self.id

    @property
    def parameters(self) -> Mapping[str, Any]:
        """Read-only v1 compatibility alias; new authoring uses ``params``."""
        return self.params


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
    beats_per_cycle: float | None = None
    beat_subdivision: float = 1.0
    speed_smoothing_seconds: float = 0.0
    state_confirmation_seconds: float = 0.0
    min_effect_hold: float = 0.0
    switch_cooldown: float = 0.0


@dataclass(frozen=True)
class AudioModulationChannelSpec:
    """One continuous music/audio-driven cue modulation channel."""

    source: str
    amount: float
    min_multiplier: float
    max_multiplier: float
    smoothing_seconds: float


@dataclass(frozen=True)
class AudioModulationSpec:
    """Cue-local audio modulation policy.

    Channels are optional so an author can modulate only the dimensions that
    preserve the intended identity of a particular effect.
    """

    enabled: bool = True
    brightness: AudioModulationChannelSpec | None = None
    speed: AudioModulationChannelSpec | None = None
    intensity: AudioModulationChannelSpec | None = None


@dataclass(frozen=True)
class BrightnessKeyframe:
    """One show-time brightness value in a target-level automation track."""

    time: float
    value: float


@dataclass(frozen=True)
class BrightnessTrackSpec:
    """A bounded target-level brightness automation track."""

    id: str
    target: TargetSelector
    start: float
    end: float
    interpolation: str
    keyframes: tuple[BrightnessKeyframe, ...]


@dataclass(frozen=True)
class Cue:
    id: str
    start: float
    end: float
    target: TargetSelector
    effect: EffectSpec
    color: ColorSpec = field(default_factory=ColorSpec)
    # ``None`` means a v2 virtual-path cue inherits its path origin. Runtime
    # treats it as ``start`` for every other target. V1 loading is explicit.
    origin: str | None = None
    branches: tuple[CueBranchSpec, ...] = ()
    priority: int = 0
    transition: TransitionSpec = field(default_factory=TransitionSpec)
    audio_control: AudioControlSpec | None = None
    audio_modulation: AudioModulationSpec | None = None


@dataclass(frozen=True)
class ShowDefinition:
    schema_version: int
    id: str
    duration: float
    cues: tuple[Cue, ...]
    defaults: TransitionSpec = field(default_factory=TransitionSpec)
    virtual_paths: tuple[VirtualPathSpec, ...] = ()
    brightness_tracks: tuple[BrightnessTrackSpec, ...] = ()
