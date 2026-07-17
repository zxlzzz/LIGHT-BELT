"""Base effect class and effect registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Mapping as TypingMapping

from light_engine.models import EffectContext, PixelFrame


class BaseEffect(ABC):
    """Abstract base class for all lighting effects."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def process(self, ctx: EffectContext) -> PixelFrame:
        """Process a single frame of this effect."""
        ...

    def reset(self) -> None:
        """Reset effect state (called on mode switch)."""
        pass

    def get_parameters(self) -> dict:
        """Get current effect parameters for display."""
        return {"name": self.name}


# Registry of all effects
_EFFECT_REGISTRY: dict[str, type[BaseEffect]] = {}


@dataclass(frozen=True)
class EffectRegistration:
    """Complete authoring/runtime contract for one reusable effect ID."""

    id: str
    validator: Callable[[TypingMapping[str, Any]], TypingMapping[str, Any]]
    renderer: type[BaseEffect]


_EFFECT_CONTRACTS: dict[str, EffectRegistration] = {}

_EFFECT_PARAMETER_KEYS: dict[str, frozenset[str]] = {
    "static": frozenset({"color", "color_timeline"}),
    "breath": frozenset({"period", "min_brightness", "color", "color_timeline"}),
    "color_wave": frozenset({"speed", "width", "hue_cycle_rate"}),
    "chase": frozenset(
        {"speed", "width", "gap", "direction", "trail", "color_source", "beat_boost"}
    ),
    "comet": frozenset({"speed", "tail_length", "decay"}),
    "audio_pulse": frozenset({"attack", "release", "color", "color_timeline"}),
    "bass_pulse": frozenset({"attack", "release", "color", "color_timeline"}),
    "spectrum": frozenset({"bass_zones", "mid_zones", "treble_zones"}),
    "video_ambient": frozenset({"smoothing"}),
    "video_audio_fusion": frozenset(
        {"video_weight", "audio_weight", "bass_boost", "treble_limit"}
    ),
    "calm": frozenset({"period", "color", "color_timeline"}),
    "color_wipe": frozenset({"speed", "color", "color_timeline"}),
    "twinkle": frozenset(
        {"density", "fade_time", "color_source", "color", "color_timeline"}
    ),
    "demo": frozenset({"cycle_interval", "effects"}),
    "step_pulse": frozenset({"period", "low_color", "high_color"}),
    "single_dot": frozenset({"speed", "direction", "color", "color_timeline"}),
    "theater_phase": frozenset({"speed", "color", "color_timeline"}),
}


def register_effect(
    name: str,
    cls: type[BaseEffect],
    validator: Callable[[TypingMapping[str, Any]], TypingMapping[str, Any]] | None = None,
) -> None:
    """Register an ID, parameter validator, and renderer without target coupling."""
    _EFFECT_REGISTRY[name] = cls
    if validator is None:
        allowed = _EFFECT_PARAMETER_KEYS.get(name, frozenset())

        def validator(values: TypingMapping[str, Any]) -> TypingMapping[str, Any]:
            unknown = set(values) - set(allowed)
            if unknown:
                raise ValueError(f"unknown effect parameters: {sorted(unknown)}")
            return dict(values)

    _EFFECT_CONTRACTS[name] = EffectRegistration(name, validator, cls)


def create_effect(name: str) -> BaseEffect:
    """Create an effect by name."""
    if name not in _EFFECT_REGISTRY:
        raise KeyError(
            f"Unknown effect: {name}. Available: {list(_EFFECT_REGISTRY.keys())}"
        )
    return _EFFECT_REGISTRY[name](name)


def list_effects() -> list[str]:
    """List all registered effect names."""
    return list(_EFFECT_REGISTRY.keys())


def get_effect_registration(name: str) -> EffectRegistration:
    """Return the complete registered contract for an effect ID."""
    if name not in _EFFECT_CONTRACTS:
        raise KeyError(f"Unknown effect: {name}")
    return _EFFECT_CONTRACTS[name]


def validate_effect_params(name: str, values: TypingMapping[str, Any]) -> TypingMapping[str, Any]:
    return get_effect_registration(name).validator(values)


def get_effect_parameter_keys(name: str) -> frozenset[str]:
    """Return registered V1 authored-show parameter keys for an effect."""
    if name not in _EFFECT_REGISTRY:
        raise KeyError(
            f"Unknown effect: {name}. Available: {list(_EFFECT_REGISTRY.keys())}"
        )
    return _EFFECT_PARAMETER_KEYS.get(name, frozenset())


def runtime_param(ctx: EffectContext, key: str, default: Any) -> Any:
    """Return a cue-authored runtime parameter, falling back to effect defaults."""

    return ctx.mode_parameters.get(key, default)


def runtime_float(ctx: EffectContext, key: str, default: float) -> float:
    return float(runtime_param(ctx, key, default))


def runtime_int(ctx: EffectContext, key: str, default: int) -> int:
    return int(runtime_param(ctx, key, default))


def runtime_str(ctx: EffectContext, key: str, default: str) -> str:
    return str(runtime_param(ctx, key, default))


def runtime_bool(ctx: EffectContext, key: str, default: bool) -> bool:
    return bool(runtime_param(ctx, key, default))


def runtime_rgb(
    ctx: EffectContext,
    key: str,
    default: tuple[float, float, float],
) -> tuple[float, float, float]:
    value = runtime_param(ctx, key, default)
    if isinstance(value, Mapping):
        return (float(value["r"]), float(value["g"]), float(value["b"]))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{key} must be an RGB sequence or mapping")
    if len(value) != 3:
        raise ValueError(f"{key} must have exactly 3 RGB channels")
    return (float(value[0]), float(value[1]), float(value[2]))
