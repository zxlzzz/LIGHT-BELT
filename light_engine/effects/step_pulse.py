"""Two-level pulse with discrete, deterministic state changes."""

from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, runtime_float, runtime_rgb
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, ZoneOutput


class StepPulseEffect(BaseEffect):
    """Alternate between two exact colors without interpolation."""

    def process(self, ctx: EffectContext) -> PixelFrame:
        period = max(0.001, runtime_float(ctx, "period", 4.0))
        low = runtime_rgb(ctx, "low_color", (0.125, 0.03125, 0.0))
        high = runtime_rgb(ctx, "high_color", (0.125, 0.0625, 0.0))
        cue_time = float(ctx.mode_parameters.get("cue_local_time", 0.0))
        color = low if cue_time % period < period / 2.0 else high

        strips = [
            DigitalStrip(
                strip_id=strip["id"],
                pixel_count=strip["pixel_count"],
                pixels=[color] * strip["pixel_count"],
            )
            for strip in ctx.mode_parameters.get("strip_defs", [])
        ]
        zones = [
            ZoneOutput(zone_id=zone["id"], color=rgb_to_rgbcct(*color))
            for zone in ctx.mode_parameters.get("zone_defs", [])
        ]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=zones,
        )
