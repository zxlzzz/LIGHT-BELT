"""CHASE effect - running light with multiple chase patterns.

Uses delta_time for frame-rate-independent animation.
Supports: single, multi, bounce, rainbow, video-color chase.
"""

from __future__ import annotations

import colorsys
import math
from typing import Optional

from light_engine.config import Config
from light_engine.effects.base import BaseEffect
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


class ChaseEffect(BaseEffect):
    """Configurable chase/running-light effect.

    Uses delta_time for consistent speed across different frame rates.
    """

    def __init__(self, name: str = "chase"):
        super().__init__(name)
        config = Config.get_instance()
        self._speed_pps = config.get("effects.chase.speed", 2.0)  # pixels per second at speed=1
        self._width = config.get("effects.chase.width", 5)
        self._gap = config.get("effects.chase.gap", 10)
        self._direction = config.get("effects.chase.direction", "forward")
        self._trail = config.get("effects.chase.trail", 0.3)
        self._color_source = config.get("effects.chase.color_source", "rainbow")
        self._beat_boost = config.get("effects.chase.beat_boost", 2.0)
        self._position: float = 0.0
        self._hue_offset: float = 0.0
        self._last_direction: int = 1

    def _chase_color(
        self, pos: float, pixel_count: int, base_rgb: Optional[tuple[float, float, float]]
    ) -> tuple[float, float, float]:
        """Get the color for a chase position."""
        if self._color_source == "rainbow":
            hue = (pos / max(1, pixel_count) * 360 + self._hue_offset) % 360
            return colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
        elif self._color_source == "video" and base_rgb:
            return base_rgb
        else:
            return (1.0, 0.6, 0.0)  # default orange

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = self._speed_pps * ctx.speed
        if ctx.mode_parameters.get("beat_boost") and ctx.audio_features:
            if ctx.audio_features.beat:
                speed *= self._beat_boost

        # Direction
        if self._direction == "bounce":
            dir_sign = self._last_direction
        elif self._direction == "reverse":
            dir_sign = -1
        else:
            dir_sign = 1

        self._position += dir_sign * speed * ctx.delta_time
        self._hue_offset = (self._hue_offset + ctx.delta_time * 30) % 360

        # Get video color if available
        video_rgb = None
        if ctx.video_features:
            video_rgb = ctx.video_features.average_rgb

        strips = []

        for sd in ctx.mode_parameters.get("strip_defs", []):
            n = sd["pixel_count"]
            if n == 0:
                continue
            period = self._width + self._gap
            if period <= 0:
                period = 1
            pixels = []
            for i in range(n):
                # Compute distance from nearest chase dot
                pos = self._position
                if self._direction == "bounce":
                    # For bounce, check both directions
                    dist_fwd = (i - pos) % period
                    dist_rev = (n - 1 - i - (n - 1 - pos)) % period
                    dist = min(dist_fwd, dist_rev)
                    # Bounce at boundaries
                    if pos > n - 1 or pos < 0:
                        self._last_direction *= -1
                else:
                    if dir_sign > 0:
                        dist = (i - pos) % period
                    else:
                        dist = (pos - (n - 1 - i)) % period

                if dist <= self._width:
                    intensity = 1.0 - (dist / self._width) * (1.0 - self._trail)
                    r, g, b = self._chase_color(i, n, video_rgb)
                    pixels.append((r * intensity, g * intensity, b * intensity))
                else:
                    pixels.append((0.0, 0.0, 0.0))

            strips.append(DigitalStrip(
                strip_id=sd["id"], pixel_count=n, pixels=pixels
            ))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=RGBCCTColor(),
            ))

        return PixelFrame(timestamp=ctx.timestamp, strips=strips, zones=zones)

    def reset(self) -> None:
        self._position = 0.0
        self._hue_offset = 0.0
        self._last_direction = 1

    def get_parameters(self) -> dict:
        return {
            "name": self.name,
            "position": round(self._position, 1),
            "speed_pps": self._speed_pps,
            "direction": self._direction,
        }
