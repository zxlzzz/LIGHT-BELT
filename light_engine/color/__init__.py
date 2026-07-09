"""Color conversion utilities: RGB, HSV, RGB+CCT, RGBW, gamma, interpolation."""

from __future__ import annotations

import colorsys
import math
from enum import Enum
from collections.abc import Mapping, Sequence
from typing import Any, Tuple

import numpy as np

from light_engine.models import RGBCCTColor


class WhiteStrategy(Enum):
    """RGBW white extraction strategies."""

    NONE = "none"
    MIN = "min"
    DESATURATE = "desaturate"
    PERCEPTUAL = "perceptual"


def rgb_to_hsv(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Convert RGB [0,1] to HSV (h[0,360], s[0,1], v[0,1])."""
    h, s, v = colorsys.rgb_to_hsv(
        max(0.0, min(1.0, r)),
        max(0.0, min(1.0, g)),
        max(0.0, min(1.0, b)),
    )
    return (h * 360.0, s, v)


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
    """Convert HSV to RGB [0,1]."""
    h = (h % 360.0) / 360.0
    s = max(0.0, min(1.0, s))
    v = max(0.0, min(1.0, v))
    result = colorsys.hsv_to_rgb(h, s, v)
    return (float(result[0]), float(result[1]), float(result[2]))


def rgb_to_rgbw(
    r: float,
    g: float,
    b: float,
    strategy: WhiteStrategy = WhiteStrategy.DESATURATE,
    white_strength: float = 1.0,
) -> Tuple[float, float, float, float]:
    """Convert RGB to RGBW using the specified white extraction strategy.

    Args:
        r, g, b: RGB channels in [0, 1].
        strategy: White extraction strategy.
        white_strength: Multiplier for white channel [0, 1].

    Returns:
        (r, g, b, w) tuple, channels in [0, 1].
        Brightness is approximately preserved for perceptual and desaturate strategies.

    Raises:
        ValueError: If any input channel is outside [0, 1].
    """
    r, g, b = float(r), float(g), float(b)
    for ch, name in [(r, "r"), (g, "g"), (b, "b")]:
        if math.isnan(ch) or math.isinf(ch) or ch < 0.0 or ch > 1.0:
            raise ValueError(f"RGB channel '{name}' must be in [0,1], got {ch}")

    white_strength = max(0.0, min(1.0, white_strength))

    if strategy == WhiteStrategy.NONE:
        return (r, g, b, 0.0)

    elif strategy == WhiteStrategy.MIN:
        w = min(r, g, b) * white_strength
        return (r - w, g - w, b - w, w)

    elif strategy == WhiteStrategy.DESATURATE:
        # Extract white based on saturation: fully saturated = no white,
        # fully desaturated (white/gray) = all white
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        if max_c > 0:
            sat = (max_c - min_c) / max_c
        else:
            sat = 0.0
        w = min_c * (1.0 - sat) * white_strength
        return (
            max(0.0, r - w),
            max(0.0, g - w),
            max(0.0, b - w),
            min(1.0, w),
        )

    elif strategy == WhiteStrategy.PERCEPTUAL:
        # Perceptual: use luminance weights and reduce saturation
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        if max_c > 0:
            sat = (max_c - min_c) / max_c
        else:
            sat = 0.0
        w = lum * (0.3 + 0.7 * (1.0 - sat)) * white_strength
        w = min(w, min_c * 1.5)
        return (
            max(0.0, r - w),
            max(0.0, g - w),
            max(0.0, b - w),
            min(1.0, w),
        )

    else:
        raise ValueError(f"Unknown white strategy: {strategy}")


def rgb_to_rgbcct(
    r: float,
    g: float,
    b: float,
    *,
    warm_bias: float = 1.0,
    cool_bias: float = 1.0,
    white_strength: float = 0.8,
    power_limit: float = 1.0,
) -> RGBCCTColor:
    """Map RGB color to RGB+CCT channels for analog COB zones.

    This is a visual mapping strategy, not a real color-temperature recovery
    algorithm. Saturated colors stay mainly RGB; neutral colors extract a
    configurable white component split between warm and cool white.
    """
    r, g, b = float(r), float(g), float(b)
    for ch, name in [(r, "r"), (g, "g"), (b, "b")]:
        if math.isnan(ch) or math.isinf(ch) or ch < 0.0 or ch > 1.0:
            raise ValueError(f"RGB channel '{name}' must be in [0,1], got {ch}")

    for value, name in [
        (warm_bias, "warm_bias"),
        (cool_bias, "cool_bias"),
        (white_strength, "white_strength"),
        (power_limit, "power_limit"),
    ]:
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"{name} must be finite, got {value}")

    warm_bias = max(0.0, float(warm_bias))
    cool_bias = max(0.0, float(cool_bias))
    white_strength = max(0.0, min(1.0, float(white_strength)))
    power_limit = max(0.0, float(power_limit))
    if power_limit == 0.0:
        return RGBCCTColor()

    max_c = max(r, g, b)
    min_c = min(r, g, b)
    if max_c <= 0.0 or white_strength <= 0.0:
        return RGBCCTColor(r=r, g=g, b=b)

    saturation = (max_c - min_c) / max_c
    white_total = min_c * (1.0 - saturation) * white_strength
    white_total = max(0.0, min(1.0, white_total))

    residual_r = max(0.0, r - white_total)
    residual_g = max(0.0, g - white_total)
    residual_b = max(0.0, b - white_total)

    cool_fraction = max(0.0, min(1.0, 0.5 + (b - r) * 0.5))
    warm_weight = (1.0 - cool_fraction) * warm_bias
    cool_weight = cool_fraction * cool_bias
    total_weight = warm_weight + cool_weight
    if total_weight > 0.0:
        warm_white = white_total * warm_weight / total_weight
        cool_white = white_total * cool_weight / total_weight
    else:
        warm_white = 0.0
        cool_white = 0.0

    channels = [residual_r, residual_g, residual_b, warm_white, cool_white]
    total_output = sum(channels)
    if power_limit > 0.0 and total_output > power_limit:
        scale = power_limit / total_output
        channels = [ch * scale for ch in channels]

    return RGBCCTColor(
        r=channels[0],
        g=channels[1],
        b=channels[2],
        warm_white=channels[3],
        cool_white=channels[4],
    )


def gamma_correct(r: float, g: float, b: float, gamma: float = 2.2) -> Tuple[float, float, float]:
    """Apply gamma correction to RGB values.

    Args:
        r, g, b: Linear RGB in [0, 1].
        gamma: Gamma value (> 0). 2.2 is sRGB standard.

    Returns:
        Gamma-corrected (r, g, b) in [0, 1].
    """
    inv_gamma = 1.0 / max(0.01, gamma)
    return (
        max(0.0, min(1.0, r ** inv_gamma)),
        max(0.0, min(1.0, g ** inv_gamma)),
        max(0.0, min(1.0, b ** inv_gamma)),
    )


def gamma_decode(r: float, g: float, b: float, gamma: float = 2.2) -> Tuple[float, float, float]:
    """Decode gamma-corrected RGB back to linear.

    Args:
        r, g, b: Gamma-corrected RGB in [0, 1].
        gamma: Gamma value (> 0).

    Returns:
        Linear (r, g, b) in [0, 1].
    """
    return (
        max(0.0, min(1.0, r ** gamma)),
        max(0.0, min(1.0, g ** gamma)),
        max(0.0, min(1.0, b ** gamma)),
    )


def perceptual_brightness(r: float, g: float, b: float) -> float:
    """Compute perceived brightness using luminance weights.

    Uses BT.601 coefficients: Y = 0.299R + 0.587G + 0.114B

    Returns:
        Perceived brightness in [0, 1].
    """
    return 0.299 * r + 0.587 * g + 0.114 * b


def lerp_color(
    c1: Tuple[float, float, float],
    c2: Tuple[float, float, float],
    t: float,
) -> Tuple[float, float, float]:
    """Linearly interpolate between two RGB colors.

    Args:
        c1, c2: RGB tuples in [0, 1].
        t: Interpolation factor [0, 1].

    Returns:
        Interpolated RGB tuple.
    """
    t = max(0.0, min(1.0, t))
    return (
        c1[0] + (c2[0] - c1[0]) * t,
        c1[1] + (c2[1] - c1[1]) * t,
        c1[2] + (c2[2] - c1[2]) * t,
    )


def evaluate_rgb_linear_timeline(
    timeline: Mapping[str, Any],
    cue_local_time: float,
) -> Tuple[float, float, float]:
    """Evaluate a validated authored ``color_timeline`` at cue-local time.

    The V1 timeline format supports only RGB linear interpolation between
    monotonically increasing keyframes. Times outside the authored range clamp
    to the nearest endpoint.
    """

    if timeline.get("interpolation") != "rgb_linear":
        raise ValueError("color_timeline.interpolation must be 'rgb_linear'")
    keyframes = timeline.get("keyframes")
    if not isinstance(keyframes, Sequence) or isinstance(keyframes, (str, bytes)):
        raise TypeError("color_timeline.keyframes must be a sequence")
    if len(keyframes) < 2:
        raise ValueError("color_timeline.keyframes must contain at least two items")

    if cue_local_time <= float(keyframes[0]["time"]):
        return tuple(keyframes[0]["color"])  # type: ignore[return-value]
    if cue_local_time >= float(keyframes[-1]["time"]):
        return tuple(keyframes[-1]["color"])  # type: ignore[return-value]

    for index in range(1, len(keyframes)):
        previous = keyframes[index - 1]
        current = keyframes[index]
        start_time = float(previous["time"])
        end_time = float(current["time"])
        if cue_local_time <= end_time:
            span = end_time - start_time
            if span <= 0.0:
                raise ValueError("color_timeline keyframe times must increase")
            t = (cue_local_time - start_time) / span
            return lerp_color(
                tuple(previous["color"]),  # type: ignore[arg-type]
                tuple(current["color"]),  # type: ignore[arg-type]
                t,
            )

    return tuple(keyframes[-1]["color"])  # type: ignore[return-value]


def hsv_lerp(
    c1: Tuple[float, float, float],
    c2: Tuple[float, float, float],
    t: float,
) -> Tuple[float, float, float]:
    """Interpolate two RGB colors in HSV space for more natural transitions.

    Handles hue wrap-around correctly (shortest path around the color wheel).
    """
    h1, s1, v1 = rgb_to_hsv(*c1)
    h2, s2, v2 = rgb_to_hsv(*c2)

    # Shortest path for hue
    dh = h2 - h1
    if abs(dh) > 180.0:
        if dh > 0:
            dh -= 360.0
        else:
            dh += 360.0

    t = max(0.0, min(1.0, t))
    h = (h1 + dh * t) % 360.0
    s = s1 + (s2 - s1) * t
    v = v1 + (v2 - v1) * t

    return hsv_to_rgb(h, s, v)


def clamp_to_uint8(value: float) -> int:
    """Clamp a float [0,1] and convert to uint8 [0,255]."""
    return max(0, min(255, round(value * 255)))


def rgb_to_uint8(r: float, g: float, b: float) -> Tuple[int, int, int]:
    """Convert RGB [0,1] to uint8 [0,255]."""
    return (clamp_to_uint8(r), clamp_to_uint8(g), clamp_to_uint8(b))
