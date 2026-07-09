"""VIDEO_AMBIENT effect - strip colors follow video zone colors."""

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, runtime_float
from light_engine.mapping.resolve import resolve_video_color
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)
from light_engine.util import ColorSmoother


class VideoAmbientEffect(BaseEffect):
    """Strip and zone colors follow video region colors with smoothing.

    Each strip/zone uses its own video_zone (top/left/right/center/bottom)
    to select a different region of the video frame.
    """

    def __init__(self, name: str = "video_ambient"):
        super().__init__(name)
        config = Config.get_instance()
        smooth_alpha = config.get("effects.video_ambient.smoothing", 0.15)
        self._smoothers: dict[str, ColorSmoother] = {}
        self._alpha = smooth_alpha

    def _get_smoother(self, key: str, alpha: float) -> ColorSmoother:
        if key not in self._smoothers:
            self._smoothers[key] = ColorSmoother(alpha=alpha)
        smoother = self._smoothers[key]
        smoother._r.alpha = alpha
        smoother._g.alpha = alpha
        smoother._b.alpha = alpha
        return smoother

    def process(self, ctx: EffectContext) -> PixelFrame:
        alpha = runtime_float(ctx, "smoothing", self._alpha)
        vf = ctx.video_features

        # --- Digital strips ---
        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            sid = sd["id"]
            n = sd["pixel_count"]
            video_zone = sd.get("video_zone", "center")
            direction = sd.get("direction", "forward")

            base_rgb = resolve_video_color(video_zone, vf, sid)
            sm = self._get_smoother(sid, alpha)
            r, g, b = sm.update(*base_rgb)

            pixels = [(r, g, b)] * n
            # Direction reverse: only for digital strips
            if direction == "reverse":
                pixels = list(reversed(pixels))

            strips.append(DigitalStrip(strip_id=sid, pixel_count=n, pixels=pixels))

        # --- RGB+CCT zones ---
        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zid = zd["id"]
            video_zone = zd.get("video_zone", "center")

            base_rgb = resolve_video_color(video_zone, vf, zid)
            sm = self._get_smoother(zid, alpha)
            r, g, b = sm.update(*base_rgb)

            zones.append(ZoneOutput(
                zone_id=zid,
                color=rgb_to_rgbcct(r, g, b),
            ))

        zone_mapping = {}
        for sd in ctx.mode_parameters.get("strip_defs", []):
            zone_mapping[sd["id"]] = sd.get("video_zone", "center")
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zone_mapping[zd["id"]] = zd.get("video_zone", "center")

        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=zones,
            metadata={"effect": "video_ambient", "zone_mapping": zone_mapping},
        )

    def reset(self) -> None:
        self._smoothers.clear()
