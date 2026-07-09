"""AUDIO_PULSE effect - brightness follows music RMS energy."""

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, runtime_float, runtime_rgb
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)
from light_engine.util import AttackReleaseEnvelope


class AudioPulseEffect(BaseEffect):
    """Brightness breathes with overall music energy (RMS)."""

    def __init__(self, name: str = "audio_pulse"):
        super().__init__(name)
        config = Config.get_instance()
        c = config.get("effects.audio_pulse.color", [0.9, 0.5, 0.1])
        self._color: tuple[float, float, float] = (
            float(c[0]), float(c[1]), float(c[2])
        )
        attack = config.get("effects.audio_pulse.attack", 0.4)
        release = config.get("effects.audio_pulse.release", 0.15)
        self._env = AttackReleaseEnvelope(attack=attack, release=release)

    def process(self, ctx: EffectContext) -> PixelFrame:
        self._env.attack = max(0.001, runtime_float(ctx, "attack", self._env.attack))
        self._env.release = max(0.001, runtime_float(ctx, "release", self._env.release))
        target = 0.0
        if ctx.audio_features and not ctx.audio_features.silence:
            target = ctx.audio_features.rms * ctx.intensity

        bri = self._env.update(target, ctx.delta_time)

        r, g, b = runtime_rgb(ctx, "color", self._color)
        r, g, b = r * bri, g * bri, b * bri

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
        self._env.reset(0.0)
