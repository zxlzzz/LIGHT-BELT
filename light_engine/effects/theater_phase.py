"""Discrete three-phase theater mask with exact colors."""

import math

from light_engine.effects.base import BaseEffect, runtime_float, runtime_rgb
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


class TheaterPhaseEffect(BaseEffect):
    """Advance an exact ``index % 3`` mask without interpolation."""

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = max(0.0, runtime_float(ctx, "speed", 2.5))
        color = runtime_rgb(ctx, "color", (0.0, 0.0, 0.125))
        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", 0.0)))
        phase = int(math.floor(cue_time * speed + 1e-9)) % 3
        black = (0.0, 0.0, 0.0)

        strips = []
        for strip in ctx.mode_parameters.get("strip_defs", []):
            count = strip["pixel_count"]
            pixels = [
                color if index % 3 == phase else black
                for index in range(count)
            ]
            strips.append(
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=count,
                    pixels=pixels,
                )
            )

        zones = [
            ZoneOutput(zone_id=zone["id"], color=RGBCCTColor())
            for zone in ctx.mode_parameters.get("zone_defs", [])
        ]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=zones,
        )
