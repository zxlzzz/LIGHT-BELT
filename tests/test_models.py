"""Tests for data models."""

import math
import pytest
from light_engine.models import (
    VideoFeatures,
    AudioFeatures,
    EffectContext,
    PixelFrame,
    DigitalStrip,
    ZoneOutput,
    RGBCCTColor,
    clamp_rgb,
    is_valid_rgb,
)


class TestClamp:
    def test_clamp_within_range(self):
        assert clamp_rgb(0.5, 0.3, 0.7) == (0.5, 0.3, 0.7)

    def test_clamp_below_zero(self):
        assert clamp_rgb(-0.1, 0.5, 0.5) == (0.0, 0.5, 0.5)

    def test_clamp_above_one(self):
        assert clamp_rgb(1.5, 0.5, 0.5) == (1.0, 0.5, 0.5)

    def test_is_valid_rgb_true(self):
        assert is_valid_rgb(0.5, 0.5, 0.5) is True

    def test_is_valid_rgb_nan(self):
        assert is_valid_rgb(float('nan'), 0.5, 0.5) is False

    def test_is_valid_rgb_inf(self):
        assert is_valid_rgb(float('inf'), 0.5, 0.5) is False

    def test_is_valid_rgb_oor(self):
        assert is_valid_rgb(1.5, 0.5, 0.5) is False


class TestVideoFeatures:
    def test_valid_construction(self):
        vf = VideoFeatures(
            timestamp=1.0,
            average_rgb=(0.5, 0.3, 0.2),
            dominant_rgb=(0.8, 0.1, 0.1),
            brightness=0.7,
            saturation=0.6,
        )
        assert vf.timestamp == 1.0
        assert vf.brightness == 0.7

    def test_clamps_rgb(self):
        vf = VideoFeatures(
            timestamp=0.0,
            average_rgb=(2.0, -0.5, 0.5),
            dominant_rgb=(0.5, 0.5, 0.5),
        )
        assert vf.average_rgb == (1.0, 0.0, 0.5)

    def test_rejects_nan_timestamp(self):
        with pytest.raises(ValueError):
            VideoFeatures(timestamp=float('nan'), average_rgb=(0.5, 0.5, 0.5), dominant_rgb=(0.5, 0.5, 0.5))

    def test_zone_colors_clamped(self):
        vf = VideoFeatures(
            timestamp=0.0,
            average_rgb=(0.5, 0.5, 0.5),
            dominant_rgb=(0.5, 0.5, 0.5),
            zone_colors={"left": (2.0, -0.5, 0.5)},
        )
        assert vf.zone_colors["left"] == (1.0, 0.0, 0.5)


class TestAudioFeatures:
    def test_valid_construction(self):
        af = AudioFeatures(timestamp=2.0, rms=0.5, bass=0.3, silence=False)
        assert af.timestamp == 2.0
        assert af.rms == 0.5
        assert af.silence is False

    def test_rms_clamped(self):
        with pytest.raises(ValueError):
            AudioFeatures(timestamp=0.0, rms=2.0)

    def test_silence(self):
        af = AudioFeatures(timestamp=0.0, rms=0.001)
        assert af.silence


class TestEffectContext:
    def test_valid(self):
        ctx = EffectContext(timestamp=1.0, delta_time=0.033)
        assert ctx.timestamp == 1.0

    def test_rejects_zero_delta(self):
        with pytest.raises(ValueError):
            EffectContext(timestamp=0.0, delta_time=0.0)

    def test_rejects_negative_delta(self):
        with pytest.raises(ValueError):
            EffectContext(timestamp=0.0, delta_time=-0.1)


class TestDigitalStrip:
    def test_creation(self):
        strip = DigitalStrip(
            strip_id="test", pixel_count=3,
            pixels=[(0.1, 0.2, 0.3), (0.4, 0.5, 0.6), (0.7, 0.8, 0.9)]
        )
        assert strip.pixel_count == 3
        assert strip.pixels[0] == (0.1, 0.2, 0.3)

    def test_pads_pixels(self):
        strip = DigitalStrip(strip_id="test", pixel_count=5, pixels=[(0.5, 0.5, 0.5)])
        assert strip.pixel_count == 5
        assert len(strip.pixels) == 5
        assert strip.pixels[-1] == (0.0, 0.0, 0.0)

    def test_trims_pixels(self):
        strip = DigitalStrip(strip_id="test", pixel_count=2,
                             pixels=[(0.1, 0.1, 0.1), (0.2, 0.2, 0.2), (0.3, 0.3, 0.3)])
        assert strip.pixel_count == 2
        assert len(strip.pixels) == 2

    def test_to_uint8(self):
        strip = DigitalStrip(strip_id="test", pixel_count=1, pixels=[(1.0, 0.5, 0.0)])
        uint8 = strip.to_uint8()
        assert uint8 == [(255, 128, 0)]


class TestRGBCCTColor:
    def test_default(self):
        c = RGBCCTColor()
        assert c.r == 0.0
        assert c.g == 0.0
        assert c.b == 0.0
        assert c.warm_white == 0.0
        assert c.cool_white == 0.0

    def test_to_uint8(self):
        c = RGBCCTColor(
            r=1.0, g=0.5, b=0.0, warm_white=0.25, cool_white=0.125
        )
        u = c.to_uint8()
        assert u == {
            "r": 255,
            "g": 128,
            "b": 0,
            "warm_white": 64,
            "cool_white": 32,
        }


class TestPixelFrame:
    def test_creation(self):
        frame = PixelFrame(timestamp=1.0)
        assert frame.timestamp == 1.0

    def test_all_pixels_valid(self):
        strip = DigitalStrip(strip_id="s1", pixel_count=1, pixels=[(0.5, 0.5, 0.5)])
        frame = PixelFrame(timestamp=0.0, strips=[strip])
        assert frame.all_pixels_valid() is True

    def test_all_pixels_valid_oor(self):
        # Clamp clamps to valid range, so pixels are valid after construction
        strip = DigitalStrip(strip_id="s1", pixel_count=1, pixels=[(2.0, 0.5, 0.5)])
        frame = PixelFrame(timestamp=0.0, strips=[strip])
        # The pixel was clamped to (1.0, 0.5, 0.5) which IS valid
        assert frame.all_pixels_valid() is True
        # Verify clamping happened
        assert strip.pixels[0] == (1.0, 0.5, 0.5)
