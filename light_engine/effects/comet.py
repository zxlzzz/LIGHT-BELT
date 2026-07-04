"""COMET effect - meteor with decaying tail."""

import colorsys
import math
import random

from light_engine.config import Config
from light_engine.effects.base import BaseEffect
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


class CometEffect(BaseEffect):
    """Meteor/comet effect with a bright head and decaying tail."""

    def __init__(self, name: str = "comet"):
        super().__init__(name)
        config = Config.get_instance()
        self._speed = config.get("effects.comet.speed", 1.5)
        self._tail_len = config.get("effects.comet.tail_length", 0.4)
        self._decay = config.get("effects.comet.decay", 0.85)
        self._positions: dict[str, float] = {}
        self._hues: dict[str, float] = {}
        self._tails: dict[str, list[tuple[float, float, float, float]]] = {}

    def process(self, ctx: EffectContext) -> PixelFrame:
        strips = []

        for sd in ctx.mode_parameters.get("strip_defs", []):
            sid = sd["id"]
            n = sd["pixel_count"]
            if n == 0:
                continue

            if sid not in self._positions:
                self._positions[sid] = 0.0
                self._hues[sid] = random.uniform(0, 360)
                self._tails[sid] = []

            self._positions[sid] += self._speed * ctx.speed * ctx.delta_time
            pos = self._positions[sid]

            # Wrap around
            if pos > n + 2:
                pos -= n + 2
                self._hues[sid] = (self._hues[sid] + 60) % 360
                self._tails[sid] = []
            self._positions[sid] = pos

            # Add new head
            hue = self._hues[sid]
            head_r, head_g, head_b = colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
            self._tails[sid].append((pos, head_r, head_g, head_b))

            # Decay and remove old tails
            for t in self._tails[sid]:
                r, g, b = t[1], t[2], t[3]
                r *= self._decay
                g *= self._decay
                b *= self._decay
                t = (t[0], r, g, b)

            # Cleanup
            self._tails[sid] = [
                t for t in self._tails[sid]
                if t[1] > 0.01 or t[2] > 0.01 or t[3] > 0.01
            ]

            # Render
            pixels = [(0.0, 0.0, 0.0)] * n
            for t_pos, tr, tg, tb in self._tails[sid]:
                tail_px = int(t_pos) % n
                tail_len = int(n * self._tail_len)
                for offset in range(tail_len):
                    px = (tail_px - offset) % n
                    factor = 1.0 - offset / max(1, tail_len)
                    cr = tr * factor
                    cg = tg * factor
                    cb = tb * factor
                    if max(cr, cg, cb) > 0.01:
                        existing = pixels[px]
                        pixels[px] = (
                            max(existing[0], cr),
                            max(existing[1], cg),
                            max(existing[2], cb),
                        )
            strips.append(DigitalStrip(strip_id=sid, pixel_count=n, pixels=pixels))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=RGBCCTColor(),
            ))

        return PixelFrame(timestamp=ctx.timestamp, strips=strips, zones=zones)

    def reset(self) -> None:
        self._positions.clear()
        self._hues.clear()
        self._tails.clear()
