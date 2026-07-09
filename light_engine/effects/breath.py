"""BREATH effect - slow periodic brightness oscillation."""

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
        self._min = config.get(
            "effects.breath.min_brightness",
            config.get("system.smoothing.min_brightness", 0.01),
        )
        self._phase = 0.0

    def process(self, ctx: EffectContext) -> PixelFrame:
        period = max(0.001, runtime_float(ctx, "period", self._period))
        minimum = runtime_float(ctx, "min_brightness", self._min)
        r, g, b = runtime_rgb(ctx, "color", self._color)

        self._phase += ctx.delta_time
        phase = float(ctx.mode_parameters.get("cue_local_time", self._phase))
        t = (math.sin(2 * math.pi * phase / period) + 1) / 2
        brightness = minimum + (1.0 - minimum) * t

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

        return PixelFrame(
            timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones
        )

    def reset(self) -> None:
        self._phase = 0.0
