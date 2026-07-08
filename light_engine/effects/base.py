"""Base effect class and effect registry."""

from __future__ import annotations

from abc import ABC, abstractmethod

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

_EFFECT_PARAMETER_KEYS: dict[str, frozenset[str]] = {
    "static": frozenset({"color"}),
    "breath": frozenset({"period", "min_brightness", "color"}),
    "color_wave": frozenset({"speed", "width", "hue_cycle_rate"}),
    "chase": frozenset(
        {"speed", "width", "gap", "direction", "trail", "color_source", "beat_boost"}
    ),
    "comet": frozenset({"speed", "tail_length", "decay"}),
    "audio_pulse": frozenset({"attack", "release", "color"}),
    "bass_pulse": frozenset({"attack", "release", "color"}),
    "spectrum": frozenset({"bass_zones", "mid_zones", "treble_zones"}),
    "video_ambient": frozenset({"smoothing"}),
    "video_audio_fusion": frozenset(
        {"video_weight", "audio_weight", "bass_boost", "treble_limit"}
    ),
    "calm": frozenset({"period", "color"}),
    "demo": frozenset({"cycle_interval", "effects"}),
}


def register_effect(name: str, cls: type[BaseEffect]) -> None:
    """Register an effect class."""
    _EFFECT_REGISTRY[name] = cls


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


def get_effect_parameter_keys(name: str) -> frozenset[str]:
    """Return registered V1 authored-show parameter keys for an effect."""
    if name not in _EFFECT_REGISTRY:
        raise KeyError(
            f"Unknown effect: {name}. Available: {list(_EFFECT_REGISTRY.keys())}"
        )
    return _EFFECT_PARAMETER_KEYS.get(name, frozenset())
