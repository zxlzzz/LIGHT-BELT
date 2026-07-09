"""CALM effect - low-stimulation slow color drift for quiet environments."""

import colorsys
import math

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, runtime_float, runtime_rgb
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)


class CalmEffect(BaseEffect):
    """Very slow, gentle color shifts suitable for relaxation."""

    def __init__(self, name: str = "calm"):
        super().__init__(name)
        config = Config.get_instance()
        c = config.get("effects.calm.color", [0.3, 0.2, 0.5])
        self._color: tuple[float, float, float] = (
            float(c[0]), float(c[1]), float(c[2])
        )
        self._base_hue = colorsys.rgb_to_hsv(
            self._color[0], self._color[1], self._color[2]
        )[0] * 360
        self._phase = 0.0

    def process(self, ctx: EffectContext) -> PixelFrame:
        color = runtime_rgb(ctx, "color", self._color)
        base_hue = colorsys.rgb_to_hsv(color[0], color[1], color[2])[0] * 360
        period = max(0.001, runtime_float(ctx, "period", 12.0))

        self._phase += ctx.delta_time
        t = self._phase / period

        hue = (base_hue + math.sin(t * 2 * math.pi) * 10) % 360
        val = 0.1 + math.sin(t * 0.8) * 0.05 + 0.15
        val = min(0.35, val)
        bri = val
        r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.3, val)

        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            n = sd["pixel_count"]
            pixels = [(r * bri, g * bri, b * bri)] * n
            strips.append(DigitalStrip(
                strip_id=sd["id"], pixel_count=n, pixels=pixels
            ))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=rgb_to_rgbcct(r * bri, g * bri, b * bri),
            ))

        return PixelFrame(
            timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones
        )

    def reset(self) -> None:
        self._phase = 0.0
