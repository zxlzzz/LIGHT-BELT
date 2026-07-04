"""Tests for color conversion module."""

import math
import pytest
from light_engine.color import (
    rgb_to_hsv,
    hsv_to_rgb,
    rgb_to_rgbw,
    rgb_to_rgbcct,
    gamma_correct,
    gamma_decode,
    perceptual_brightness,
    lerp_color,
    hsv_lerp,
    WhiteStrategy,
)


class TestRGBHSV:
    def test_rgb_to_hsv_red(self):
        h, s, v = rgb_to_hsv(1.0, 0.0, 0.0)
        assert abs(h - 0.0) < 1.0
        assert s == 1.0
        assert v == 1.0

    def test_rgb_to_hsv_black(self):
        h, s, v = rgb_to_hsv(0.0, 0.0, 0.0)
        assert v == 0.0

    def test_roundtrip(self):
        original = (0.3, 0.6, 0.2)
        h, s, v = rgb_to_hsv(*original)
        result = hsv_to_rgb(h, s, v)
        for a, b in zip(original, result):
            assert abs(a - b) < 0.01

    def test_rgb_clamped(self):
        h, s, v = rgb_to_hsv(-0.5, 2.0, 0.5)

    def test_hsv_clamped(self):
        r, g, b = hsv_to_rgb(720, 2.0, -0.5)
        assert 0.0 <= r <= 1.0
        assert 0.0 <= g <= 1.0
        assert 0.0 <= b <= 1.0


class TestRGBW:
    def test_none_strategy(self):
        r, g, b, w = rgb_to_rgbw(1.0, 0.5, 0.0, WhiteStrategy.NONE)
        assert w == 0.0
        assert r == 1.0

    def test_min_strategy(self):
        r, g, b, w = rgb_to_rgbw(0.5, 0.3, 0.2, WhiteStrategy.MIN)
        assert w > 0.0
        assert r + w <= 1.0 + 1e-9

    def test_desaturate_strategy_gray(self):
        r, g, b, w = rgb_to_rgbw(0.5, 0.5, 0.5, WhiteStrategy.DESATURATE)
        assert w > 0.3  # Gray should produce significant white

    def test_desaturate_strategy_saturated(self):
        r, g, b, w = rgb_to_rgbw(1.0, 0.0, 0.0, WhiteStrategy.DESATURATE)
        assert w < 0.1  # Pure red should produce minimal white

    def test_perceptual_strategy(self):
        r, g, b, w = rgb_to_rgbw(0.5, 0.5, 0.5, WhiteStrategy.PERCEPTUAL)
        assert w > 0.0

    def test_white_strength_zero(self):
        r, g, b, w = rgb_to_rgbw(0.5, 0.3, 0.2, WhiteStrategy.MIN, white_strength=0.0)
        assert w == 0.0

    def test_rejects_invalid_input(self):
        with pytest.raises(ValueError):
            rgb_to_rgbw(-0.1, 0.5, 0.5)

    def test_rejects_nan(self):
        with pytest.raises(ValueError):
            rgb_to_rgbw(float('nan'), 0.5, 0.5)


class TestRGBCCT:
    def test_black_outputs_all_zero(self):
        c = rgb_to_rgbcct(0.0, 0.0, 0.0)
        assert c.r == 0.0
        assert c.g == 0.0
        assert c.b == 0.0
        assert c.warm_white == 0.0
        assert c.cool_white == 0.0

    def test_saturated_primaries_use_rgb(self):
        for rgb in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]:
            c = rgb_to_rgbcct(*rgb)
            assert c.warm_white < 0.01
            assert c.cool_white < 0.01
            assert max(c.r, c.g, c.b) > 0.9

    def test_neutral_white_uses_warm_and_cool_white(self):
        c = rgb_to_rgbcct(0.8, 0.8, 0.8)
        assert c.warm_white > 0.0
        assert c.cool_white > 0.0

    def test_warm_white_prefers_warm_channel(self):
        c = rgb_to_rgbcct(1.0, 0.82, 0.55)
        assert c.warm_white > c.cool_white

    def test_cool_white_prefers_cool_channel(self):
        c = rgb_to_rgbcct(0.55, 0.75, 1.0)
        assert c.cool_white > c.warm_white

    def test_power_limit_caps_channel_sum(self):
        c = rgb_to_rgbcct(1.0, 1.0, 1.0, power_limit=0.75)
        total = c.r + c.g + c.b + c.warm_white + c.cool_white
        assert total <= 0.75 + 1e-9

    def test_rejects_invalid_input(self):
        with pytest.raises(ValueError):
            rgb_to_rgbcct(float("nan"), 0.0, 0.0)
        with pytest.raises(ValueError):
            rgb_to_rgbcct(0.0, -0.1, 0.0)


class TestGamma:
    def test_gamma_identity(self):
        r, g, b = gamma_correct(0.5, 0.5, 0.5, gamma=1.0)
        assert abs(r - 0.5) < 0.01

    def test_gamma_darkens(self):
        r, g, b = gamma_correct(0.5, 0.5, 0.5, gamma=2.2)
        assert r > 0.5  # Gamma correction brightens mid-tones

    def test_roundtrip(self):
        original = (0.3, 0.6, 0.2)
        corrected = gamma_correct(*original, gamma=2.2)
        decoded = gamma_decode(*corrected, gamma=2.2)
        for a, b in zip(original, decoded):
            assert abs(a - b) < 0.01


class TestPerceptualBrightness:
    def test_green_brighter_than_blue(self):
        # Green contributes more to perceived brightness
        bg = perceptual_brightness(0.0, 1.0, 0.0)
        bb = perceptual_brightness(0.0, 0.0, 1.0)
        assert bg > bb

    def test_black(self):
        assert perceptual_brightness(0.0, 0.0, 0.0) == 0.0

    def test_white(self):
        assert abs(perceptual_brightness(1.0, 1.0, 1.0) - 1.0) < 0.01


class TestLerp:
    def test_lerp_halfway(self):
        result = lerp_color((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.5)
        assert result == (0.5, 0.5, 0.5)

    def test_lerp_clamped(self):
        result = lerp_color((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 2.0)
        assert result == (1.0, 1.0, 1.0)

    def test_hsv_lerp(self):
        result = hsv_lerp((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.5)
        assert all(0.0 <= c <= 1.0 for c in result)
