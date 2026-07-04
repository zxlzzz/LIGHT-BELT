"""Tests for RGB to RGB+CCT mapping."""

from light_engine.color import rgb_to_rgbcct
from light_engine.models import RGBCCTColor


def _channel_sum(color: RGBCCTColor) -> float:
    return color.r + color.g + color.b + color.warm_white + color.cool_white


def test_black_field_is_all_zero() -> None:
    color = rgb_to_rgbcct(0.0, 0.0, 0.0)
    assert color == RGBCCTColor()


def test_rgb_primaries_keep_white_channels_near_zero() -> None:
    red = rgb_to_rgbcct(1.0, 0.0, 0.0)
    green = rgb_to_rgbcct(0.0, 1.0, 0.0)
    blue = rgb_to_rgbcct(0.0, 0.0, 1.0)

    for color in [red, green, blue]:
        assert color.warm_white < 0.01
        assert color.cool_white < 0.01


def test_neutral_white_splits_between_warm_and_cool() -> None:
    color = rgb_to_rgbcct(1.0, 1.0, 1.0)
    assert color.warm_white > 0.0
    assert color.cool_white > 0.0


def test_warm_and_cool_white_biases() -> None:
    warm = rgb_to_rgbcct(1.0, 0.82, 0.55)
    cool = rgb_to_rgbcct(0.55, 0.75, 1.0)

    assert warm.warm_white > warm.cool_white
    assert cool.cool_white > cool.warm_white


def test_power_limit_caps_total_channel_output() -> None:
    color = rgb_to_rgbcct(1.0, 1.0, 1.0, power_limit=0.5)
    assert _channel_sum(color) <= 0.5 + 1e-9


def test_zero_power_limit_produces_black() -> None:
    assert rgb_to_rgbcct(
        1.0, 1.0, 1.0, power_limit=0.0
    ) == RGBCCTColor()


def test_neutral_brightness_is_monotonic_until_power_limit() -> None:
    values = [0.0, 0.2, 0.4, 0.6]
    sums = [_channel_sum(rgb_to_rgbcct(v, v, v, power_limit=1.0)) for v in values]
    assert sums == sorted(sums)
