"""BREATH effect - slow periodic brightness oscillation."""

import math

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)


class BreathEffect(BaseEffect):
    """Slow sinusoidal brightness breathing."""

    def __init__(self, name: str = "breath"):
        super().__init__(name)
        config = Config.get_instance()
        self._period = config.get("effects.breath.period", 4.0)
        c = config.get("effects.breath.color", [0.4, 0.2, 0.6])
        self._color: tuple[float, float, float] = (
            float(c[0]), float(c[1]), float(c[2])
        )
        self._min = config.get("system.smoothing.min_brightness", 0.01)
        self._phase = 0.0

    def process(self, ctx: EffectContext) -> PixelFrame:
        self._phase += ctx.delta_time
        t = (math.sin(2 * math.pi * self._phase / self._period) + 1) / 2
        brightness = self._min + (1.0 - self._min) * t

        r, g, b = self._color
        r, g, b = r * brightness, g * brightness, b * brightness

        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            pixels = [(r, g, b)] * sd["pixel_count"]
            strips.append(DigitalStrip(
                strip_id=sd["id"], pixel_count=sd["pixel_count"], pixels=pixels
            ))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=rgb_to_rgbcct(r, g, b),
            ))

        return PixelFrame(timestamp=ctx.timestamp, strips=strips, zones=zones)

    def reset(self) -> None:
        self._phase = 0.0
