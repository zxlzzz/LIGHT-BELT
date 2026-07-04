"""STATIC effect - constant color across all strips and zones."""

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)


class StaticEffect(BaseEffect):
    """Outputs a constant color to all strips and zones."""

    def __init__(self, name: str = "static"):
        super().__init__(name)
        config = Config.get_instance()
        c = config.get("effects.static.color", [0.2, 0.4, 0.8])
        self._color: tuple[float, float, float] = (
            float(c[0]), float(c[1]), float(c[2])
        )

    def process(self, ctx: EffectContext) -> PixelFrame:
        r, g, b = self._color

        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", []):
            pixel_count = strip_def.get("pixel_count", 0)
            pixels = [(r, g, b)] * pixel_count
            strips.append(DigitalStrip(
                strip_id=strip_def["id"], pixel_count=pixel_count, pixels=pixels
            ))

        zones = []
        for zone_def in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zone_def["id"],
                color=rgb_to_rgbcct(r, g, b),
            ))

        return PixelFrame(timestamp=ctx.timestamp, strips=strips, zones=zones)
