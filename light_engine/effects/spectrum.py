"""SPECTRUM effect - different zones mapped to different frequency bands."""

import colorsys

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, runtime_param
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)
from light_engine.util import AttackReleaseEnvelope


class SpectrumEffect(BaseEffect):
    """Maps bass, mid, treble bands to different lighting zones."""

    def __init__(self, name: str = "spectrum"):
        super().__init__(name)
        config = Config.get_instance()
        self._bass_zones = config.get("effects.spectrum.bass_zones", [])
        self._mid_zones = config.get("effects.spectrum.mid_zones", [])
        self._treble_zones = config.get("effects.spectrum.treble_zones", [])
        self._bass_env = AttackReleaseEnvelope(attack=0.5, release=0.2)
        self._mid_env = AttackReleaseEnvelope(attack=0.3, release=0.15)
        self._treble_env = AttackReleaseEnvelope(attack=0.3, release=0.1)

    def process(self, ctx: EffectContext) -> PixelFrame:
        bass_zones = set(runtime_param(ctx, "bass_zones", self._bass_zones))
        mid_zones = set(runtime_param(ctx, "mid_zones", self._mid_zones))
        treble_zones = set(runtime_param(ctx, "treble_zones", self._treble_zones))
        bass = 0.0
        mid = 0.0
        treble = 0.0
        if ctx.audio_features and not ctx.audio_features.silence:
            bass = ctx.audio_features.bass
            mid = ctx.audio_features.mid
            treble = ctx.audio_features.treble

        bass_bri = self._bass_env.update(bass, ctx.delta_time)
        mid_bri = self._mid_env.update(mid, ctx.delta_time)
        treble_bri = self._treble_env.update(treble, ctx.delta_time)

        # Colors: bass=red, mid=green, treble=blue
        band_colors = {
            "bass": (1.0, 0.15, 0.05),
            "mid": (0.05, 1.0, 0.15),
            "treble": (0.1, 0.3, 1.0),
        }

        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            sid = sd["id"]
            n = sd["pixel_count"]
            if sid in bass_zones:
                br, bri = band_colors["bass"], bass_bri
            elif sid in mid_zones:
                br, bri = band_colors["mid"], mid_bri
            elif sid in treble_zones:
                br, bri = band_colors["treble"], treble_bri
            else:
                br, bri = (0.05, 0.05, 0.05), 0.0
            pixels = [(br[0] * bri, br[1] * bri, br[2] * bri)] * n
            strips.append(DigitalStrip(strip_id=sid, pixel_count=n, pixels=pixels))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zid = zd["id"]
            if zid in bass_zones:
                cr, cg, cb = band_colors["bass"]
                bri = bass_bri
            elif zid in mid_zones:
                cr, cg, cb = band_colors["mid"]
                bri = mid_bri
            elif zid in treble_zones:
                cr, cg, cb = band_colors["treble"]
                bri = treble_bri
            else:
                cr, cg, cb, bri = 0.0, 0.0, 0.0, 0.0
            zones.append(ZoneOutput(
                zone_id=zid,
                color=rgb_to_rgbcct(cr * bri, cg * bri, cb * bri),
            ))

        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=zones,
            metadata={"bass": bass, "mid": mid, "treble": treble},
        )

    def reset(self) -> None:
        self._bass_env.reset(0.0)
        self._mid_env.reset(0.0)
        self._treble_env.reset(0.0)
