"""Minimal output transform for single global brightness application."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Tuple

from light_engine.models import DigitalStrip, PixelFrame, RGBCCTColor, ZoneOutput


def _validate_brightness(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"global_brightness must be finite, got {value}")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"global_brightness must be in [0, 1], got {value}")
    return value


@dataclass
class OutputTransform:
    """Apply final output-domain transforms.

    Phase 1 intentionally implements only global brightness so brightness is
    applied exactly once after effects have produced pure logical colors.
    """

    global_brightness: float = 1.0

    def __post_init__(self) -> None:
        self.global_brightness = _validate_brightness(self.global_brightness)

    def apply_to_zone(self, color: RGBCCTColor) -> RGBCCTColor:
        scale = self.global_brightness
        return RGBCCTColor(
            r=color.r * scale,
            g=color.g * scale,
            b=color.b * scale,
            warm_white=color.warm_white * scale,
            cool_white=color.cool_white * scale,
        )

    def apply_to_pixels(
        self, pixels: Iterable[Tuple[float, float, float]]
    ) -> list[Tuple[float, float, float]]:
        scale = self.global_brightness
        return [(r * scale, g * scale, b * scale) for r, g, b in pixels]

    def apply_to_frame(self, frame: PixelFrame) -> PixelFrame:
        return PixelFrame(
            timestamp=frame.timestamp,
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
                    color=self.apply_to_zone(zone.color),
                )
                for zone in frame.zones
            ],
            metadata=dict(frame.metadata),
        )
