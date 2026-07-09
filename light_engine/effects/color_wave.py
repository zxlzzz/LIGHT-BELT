"""COLOR_WAVE effect - color flows continuously along strips."""

import colorsys
import math

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, runtime_float
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)


class ColorWaveEffect(BaseEffect):
    """Continuous color wave flowing along each strip."""

    def __init__(self, name: str = "color_wave"):
        super().__init__(name)
        config = Config.get_instance()
        self._speed = config.get("effects.color_wave.speed", 1.0)
        self._width = config.get("effects.color_wave.width", 0.3)
        self._hue_rate = config.get("effects.color_wave.hue_cycle_rate", 0.1)
        self._phase = 0.0

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = runtime_float(ctx, "speed", self._speed)
        width = max(0.001, runtime_float(ctx, "width", self._width))
        hue_rate = runtime_float(ctx, "hue_cycle_rate", self._hue_rate)

        self._phase += ctx.delta_time * speed * ctx.speed
        hue_base = (self._phase * hue_rate * 360) % 360

        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            n = sd["pixel_count"]
            pixels = []
            for i in range(n):
                pos = (i / max(1, n)) / width + self._phase
                hue = (hue_base + pos * 120) % 360
                r, g, b = colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
                pixels.append((r, g, b))
            strips.append(DigitalStrip(
                strip_id=sd["id"], pixel_count=n, pixels=pixels
            ))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            hue = (hue_base + self._phase * 60) % 360
            r, g, b = colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=rgb_to_rgbcct(r, g, b),
            ))

        return PixelFrame(
            timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones
        )

    def reset(self) -> None:
        self._phase = 0.0
