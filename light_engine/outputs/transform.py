"""Output-domain transforms for brightness, power, gamma, and safety."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, Tuple

from light_engine.models import DigitalStrip, PixelFrame, RGBCCTColor, ZoneOutput


def _validate_brightness(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"global_brightness must be finite, got {value}")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"global_brightness must be in [0, 1], got {value}")
    return value


def _validate_non_negative_finite(value: float, name: str) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def _clamp_channel(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass
class OutputTransform:
    """Apply final output-domain transforms.

    Brightness is applied exactly once here after effects have produced pure
    logical colors. The remaining transforms operate only on copies.
    """

    global_brightness: float = 1.0
    power_limit: float = 5.0
    gamma: float = 1.0
    per_zone_warm_bias: Mapping[str, float] | None = None
    per_zone_cool_bias: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        self.global_brightness = _validate_brightness(self.global_brightness)
        self.power_limit = _validate_non_negative_finite(
            self.power_limit, "power_limit"
        )
        self.gamma = _validate_non_negative_finite(self.gamma, "gamma")
        if self.gamma == 0.0:
            raise ValueError("gamma must be > 0")
        self.per_zone_warm_bias = dict(self.per_zone_warm_bias or {})
        self.per_zone_cool_bias = dict(self.per_zone_cool_bias or {})
        for zone_id, value in self.per_zone_warm_bias.items():
            self.per_zone_warm_bias[zone_id] = _validate_non_negative_finite(
                value, f"per_zone_warm_bias[{zone_id!r}]"
            )
        for zone_id, value in self.per_zone_cool_bias.items():
            self.per_zone_cool_bias[zone_id] = _validate_non_negative_finite(
                value, f"per_zone_cool_bias[{zone_id!r}]"
            )

    def gamma_correct(self, value: float) -> float:
        """Apply deterministic gamma correction to one normalized channel."""
        return _clamp_channel(_clamp_channel(value) ** self.gamma)

    def _limit_power(
        self,
        channels: Tuple[float, float, float, float, float],
    ) -> Tuple[float, float, float, float, float]:
        total = sum(channels)
        if self.power_limit <= 0.0:
            return (0.0, 0.0, 0.0, 0.0, 0.0)
        if total <= self.power_limit:
            return channels
        scale = self.power_limit / total
        return tuple(ch * scale for ch in channels)  # type: ignore[return-value]

    def apply_to_zone(
        self, color: RGBCCTColor, zone_id: str | None = None
    ) -> RGBCCTColor:
        scale = self.global_brightness
        warm_bias = (
            self.per_zone_warm_bias.get(zone_id, 1.0)
            if zone_id is not None and self.per_zone_warm_bias is not None
            else 1.0
        )
        cool_bias = (
            self.per_zone_cool_bias.get(zone_id, 1.0)
            if zone_id is not None and self.per_zone_cool_bias is not None
            else 1.0
        )
        channels = (
            self.gamma_correct(color.r * scale),
            self.gamma_correct(color.g * scale),
            self.gamma_correct(color.b * scale),
            self.gamma_correct(color.warm_white * scale * warm_bias),
            self.gamma_correct(color.cool_white * scale * cool_bias),
        )
        r, g, b, warm_white, cool_white = self._limit_power(channels)
        return RGBCCTColor(
            r=r,
            g=g,
            b=b,
            warm_white=warm_white,
            cool_white=cool_white,
        )

    def apply_to_pixels(
        self, pixels: Iterable[Tuple[float, float, float]]
    ) -> list[Tuple[float, float, float]]:
        scale = self.global_brightness
        return [
            (
                self.gamma_correct(r * scale),
                self.gamma_correct(g * scale),
                self.gamma_correct(b * scale),
            )
            for r, g, b in pixels
        ]

    def apply_to_frame(self, frame: PixelFrame) -> PixelFrame:
        return PixelFrame(
            timestamp=frame.timestamp,
            sequence=frame.sequence,
            strips=[
                DigitalStrip(
                    strip_id=strip.strip_id,
                    pixel_count=strip.pixel_count,
                    pixels=self.apply_to_pixels(strip.pixels),
                )
                for strip in frame.strips
            ],
            zones=[
                ZoneOutput(
                    zone_id=zone.zone_id,
                    color=self.apply_to_zone(zone.color, zone.zone_id),
                )
                for zone in frame.zones
            ],
            metadata=dict(frame.metadata),
        )

    @classmethod
    def generate_safe_frame(
        cls,
        *,
        timestamp: float = 0.0,
        sequence: int = 0,
        zone_ids: Sequence[str] | None = None,
        strips: Sequence[Mapping[str, object]] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> PixelFrame:
        """Generate an all-black safe-state logical frame."""
        safe_metadata = dict(metadata or {})
        safe_metadata["SAFE_STATE"] = True
        safe_metadata["safe_state"] = True

        safe_strips: list[DigitalStrip] = []
        for strip in strips or ():
            strip_id = str(strip["id"])
            pixel_count = int(strip["pixel_count"])
            safe_strips.append(
                DigitalStrip(
                    strip_id=strip_id,
                    pixel_count=pixel_count,
                    pixels=[(0.0, 0.0, 0.0)] * pixel_count,
                )
            )

        return PixelFrame(
            timestamp=timestamp,
            sequence=sequence,
            strips=safe_strips,
            zones=[
                ZoneOutput(zone_id=zone_id, color=RGBCCTColor())
                for zone_id in (zone_ids or ())
            ],
            metadata=safe_metadata,
        )
