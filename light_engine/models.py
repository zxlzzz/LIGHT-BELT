"""Data models for the lighting engine.

All public data models have type annotations, validate required fields,
prevent NaN/Inf propagation, and use explicit timestamp units (seconds).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

import numpy as np

def _validate_float(
    value: float, name: str, min_val: float = 0.0, max_val: float = 1.0
) -> float:
    """Validate a float value is within bounds and not NaN/Inf."""
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be a finite number, got {value}")
    if value < min_val or value > max_val:
        raise ValueError(
            f"{name} must be in [{min_val}, {max_val}], got {value}"
        )
    return value


def _validate_rgb(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Validate RGB channels are in [0, 1] and finite."""
    return (
        _validate_float(r, "r"),
        _validate_float(g, "g"),
        _validate_float(b, "b"),
    )


def clamp_rgb(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Clamp RGB values to [0, 1] without raising."""
    return (
        max(0.0, min(1.0, r)),
        max(0.0, min(1.0, g)),
        max(0.0, min(1.0, b)),
    )


def is_valid_rgb(r: float, g: float, b: float) -> bool:
    """Check if RGB values are finite and within [0, 1]."""
    for v in (r, g, b):
        if math.isnan(v) or math.isinf(v) or v < 0.0 or v > 1.0:
            return False
    return True


@dataclass
class VideoFeatures:
    """Per-frame video analysis features.

    Attributes:
        timestamp: Time in seconds since media start.
        average_rgb: (r,g,b) tuple in [0,1] range.
        dominant_rgb: (r,g,b) dominant color in [0,1] range.
        zone_colors: Dict mapping zone name to (r,g,b) tuple.
        brightness: Overall brightness in [0,1].
        saturation: Overall saturation in [0,1].
        scene_change: Scene change intensity in [0,1].
    """

    timestamp: float
    average_rgb: Tuple[float, float, float]
    dominant_rgb: Tuple[float, float, float]
    zone_colors: dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    brightness: float = 0.0
    saturation: float = 0.0
    scene_change: float = 0.0

    def __post_init__(self) -> None:
        if math.isnan(self.timestamp) or math.isinf(self.timestamp):
            raise ValueError(f"timestamp must be finite, got {self.timestamp}")
        self.average_rgb = clamp_rgb(*self.average_rgb)
        self.dominant_rgb = clamp_rgb(*self.dominant_rgb)
        self.zone_colors = {
            k: clamp_rgb(*v) for k, v in self.zone_colors.items()
        }
        self.brightness = _validate_float(self.brightness, "brightness")
        self.saturation = _validate_float(self.saturation, "saturation")
        self.scene_change = _validate_float(self.scene_change, "scene_change")


@dataclass
class AudioFeatures:
    """Per-window audio analysis features.

    Attributes:
        timestamp: Time in seconds since media start.
        rms: Root mean square energy in [0,1] (normalized).
        bass: Low frequency energy (20-200Hz) in [0,1].
        mid: Mid frequency energy (200-2000Hz) in [0,1].
        treble: High frequency energy (2000-12000Hz) in [0,1].
        spectral_flux: Spectral flux / transient intensity in [0,1].
        beat: Boolean beat detection flag.
        onset: Onset detection strength in [0,1].
        silence: Boolean silence flag.
    """

    timestamp: float
    rms: float = 0.0
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    spectral_flux: float = 0.0
    beat: bool = False
    onset: float = 0.0
    silence: bool = True

    def __post_init__(self) -> None:
        if math.isnan(self.timestamp) or math.isinf(self.timestamp):
            raise ValueError(f"timestamp must be finite, got {self.timestamp}")
        self.rms = _validate_float(self.rms, "rms")
        self.bass = _validate_float(self.bass, "bass")
        self.mid = _validate_float(self.mid, "mid")
        self.treble = _validate_float(self.treble, "treble")
        self.spectral_flux = _validate_float(self.spectral_flux, "spectral_flux")
        self.onset = _validate_float(self.onset, "onset")


@dataclass(frozen=True)
class MusicControlState:
    """Deterministic bounded music-control state.

    Tempo is reported for the supported 60-180 BPM range. Confidence,
    beat phase, beat strength, beat regularity, energy, transient,
    bass ambience/pulse, and spectral motion are finite values in [0,1].
    Energy trend is finite in [-1,1], where positive values indicate rising
    energy over the bounded medium window.
    """

    timestamp: float
    tempo_bpm: float = 0.0
    tempo_confidence: float = 0.0
    beat_phase: float = 0.0
    beat_strength: float = 0.0
    beat_regularity: float = 0.0
    energy: float = 0.0
    energy_trend: float = 0.0
    transient: float = 0.0
    bass_ambient: float = 0.0
    bass_pulse: float = 0.0
    spectral_motion: float = 0.0

    def __post_init__(self) -> None:
        if math.isnan(self.timestamp) or math.isinf(self.timestamp):
            raise ValueError(f"timestamp must be finite, got {self.timestamp}")
        object.__setattr__(
            self, "tempo_bpm", _validate_float(self.tempo_bpm, "tempo_bpm", 0.0, 240.0)
        )
        for field_name in (
            "tempo_confidence",
            "beat_phase",
            "beat_strength",
            "beat_regularity",
            "energy",
            "transient",
            "bass_ambient",
            "bass_pulse",
            "spectral_motion",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_float(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "energy_trend",
            _validate_float(self.energy_trend, "energy_trend", -1.0, 1.0),
        )


@dataclass
class EffectContext:
    """Context passed to each effect's process() method.

    Attributes:
        timestamp: Current time in seconds.
        sequence: Engine-assigned logical frame sequence.
        delta_time: Time since last frame in seconds.
        video_features: Latest video analysis features (may be None).
        audio_features: Latest audio analysis features (may be None).
        speed: Global speed multiplier.
        intensity: Global intensity multiplier.
        mode_parameters: Effect-specific parameters dict.
    """

    timestamp: float
    delta_time: float
    sequence: int = 0
    video_features: Optional[VideoFeatures] = None
    audio_features: Optional[AudioFeatures] = None
    music_control_state: Optional[MusicControlState] = None
    speed: float = 1.0
    intensity: float = 1.0
    mode_parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if math.isnan(self.timestamp) or math.isinf(self.timestamp):
            raise ValueError(f"timestamp must be finite, got {self.timestamp}")
        if self.delta_time <= 0:
            raise ValueError(f"delta_time must be positive, got {self.delta_time}")
        if self.sequence < 0:
            raise ValueError(f"sequence must be >= 0, got {self.sequence}")
        self.speed = _validate_float(self.speed, "speed", min_val=0.0, max_val=10.0)
        self.intensity = _validate_float(
            self.intensity, "intensity", min_val=0.0, max_val=10.0
        )


@dataclass
class RGBCCTColor:
    """Color for analog RGB+CCT zones.

    Channels are [0,1] floats internally. Brightness is intentionally not
    stored here; OutputTransform is the only global brightness application
    point.
    """

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    warm_white: float = 0.0
    cool_white: float = 0.0

    def __post_init__(self) -> None:
        self.r = _validate_float(self.r, "r")
        self.g = _validate_float(self.g, "g")
        self.b = _validate_float(self.b, "b")
        self.warm_white = _validate_float(self.warm_white, "warm_white")
        self.cool_white = _validate_float(self.cool_white, "cool_white")

    def to_uint8(self) -> dict[str, int]:
        """Convert to 0-255 integer representation."""
        return {
            "r": round(self.r * 255),
            "g": round(self.g * 255),
            "b": round(self.b * 255),
            "warm_white": round(self.warm_white * 255),
            "cool_white": round(self.cool_white * 255),
        }


@dataclass
class DigitalStrip:
    """Per-pixel colors for a digital addressable LED strip.

    Attributes:
        strip_id: Strip identifier.
        pixel_count: Number of pixels in this strip.
        pixels: List of (r,g,b) tuples in [0,1] range.
    """

    strip_id: str
    pixel_count: int
    pixels: list[Tuple[float, float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.pixel_count < 0:
            raise ValueError(f"pixel_count must be >= 0, got {self.pixel_count}")
        # Validate pixel values
        self.pixels = [clamp_rgb(*p) for p in self.pixels]
        if len(self.pixels) != self.pixel_count:
            # Pad or trim
            while len(self.pixels) < self.pixel_count:
                self.pixels.append((0.0, 0.0, 0.0))
            self.pixels = self.pixels[: self.pixel_count]

    def to_uint8(self) -> list[Tuple[int, int, int]]:
        """Convert pixels to 0-255 integer representation."""
        return [
            (round(r * 255), round(g * 255), round(b * 255))
            for r, g, b in self.pixels
        ]


@dataclass
class ZoneOutput:
    """Output for an analog RGB+CCT zone."""

    zone_id: str
    color: RGBCCTColor = field(default_factory=RGBCCTColor)


@dataclass
class PixelFrame:
    """Complete output frame with strips and zones.

    Attributes:
        timestamp: Frame time in seconds.
        sequence: Engine-assigned logical frame sequence.
        strips: List of DigitalStrip outputs.
        zones: List of ZoneOutput for analog zones.
        metadata: Arbitrary key-value metadata.
    """

    timestamp: float
    sequence: int = 0
    strips: list[DigitalStrip] = field(default_factory=list)
    zones: list[ZoneOutput] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if math.isnan(self.timestamp) or math.isinf(self.timestamp):
            raise ValueError(f"timestamp must be finite, got {self.timestamp}")
        if self.sequence < 0:
            raise ValueError(f"sequence must be >= 0, got {self.sequence}")

    def all_pixels_valid(self) -> bool:
        """Check that all pixel values are finite and in [0,1]."""
        for strip in self.strips:
            for r, g, b in strip.pixels:
                if not is_valid_rgb(r, g, b):
                    return False
        for zone in self.zones:
            c = zone.color
            if (
                not is_valid_rgb(c.r, c.g, c.b)
                or not is_valid_rgb(c.warm_white, c.cool_white, 0.0)
            ):
                return False
        return True


# Type aliases
ColorRGB = Tuple[float, float, float]
ColorRGBA = Tuple[float, float, float, float]
