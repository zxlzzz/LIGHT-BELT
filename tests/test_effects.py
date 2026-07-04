"""Tests for lighting effects."""

import pytest
from light_engine.effects import create_effect, list_effects, BaseEffect
from light_engine.effects.base import _EFFECT_REGISTRY
from light_engine.models import EffectContext, RGBCCTColor


def _assert_rgbcct_zones(frame):
    for zone in frame.zones:
        assert isinstance(zone.color, RGBCCTColor)


class TestEffectRegistry:
    def test_all_12_effects_registered(self):
        effects = list_effects()
        assert len(effects) == 12
        required = [
            "static", "breath", "color_wave", "chase", "comet",
            "audio_pulse", "bass_pulse", "spectrum",
            "video_ambient", "video_audio_fusion", "calm", "demo",
        ]
        for name in required:
            assert name in effects, f"Missing effect: {name}"

    def test_create_effect(self):
        for name in list_effects():
            eff = create_effect(name)
            assert isinstance(eff, BaseEffect)
            assert eff.name == name

    def test_unknown_effect(self):
        with pytest.raises(KeyError):
            create_effect("nonexistent")


class TestAllEffects:
    """Verify all effects can process a frame without crashing."""

    @pytest.fixture
    def ctx(self):
        return EffectContext(
            timestamp=1.0,
            delta_time=0.033,
            mode_parameters={
                "strip_defs": [
                    {"id": "s1", "pixel_count": 10, "video_zone": "center"},
                    {"id": "s2", "pixel_count": 5, "video_zone": "left"},
                ],
                "zone_defs": [
                    {"id": "z1", "video_zone": "center"},
                    {"id": "z2", "video_zone": "left"},
                ],
            },
        )

    def test_static(self, ctx):
        eff = create_effect("static")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_breath(self, ctx):
        eff = create_effect("breath")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_color_wave(self, ctx):
        eff = create_effect("color_wave")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_chase(self, ctx):
        eff = create_effect("chase")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_comet(self, ctx):
        eff = create_effect("comet")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_audio_pulse(self, ctx):
        eff = create_effect("audio_pulse")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_bass_pulse(self, ctx):
        eff = create_effect("bass_pulse")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_spectrum(self, ctx):
        eff = create_effect("spectrum")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_video_ambient(self, ctx):
        eff = create_effect("video_ambient")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_video_audio_fusion(self, ctx):
        eff = create_effect("video_audio_fusion")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_calm(self, ctx):
        eff = create_effect("calm")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)

    def test_demo(self, ctx):
        eff = create_effect("demo")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        assert "demo_current" in frame.metadata

    def test_chase_position_changes(self, ctx):
        eff = create_effect("chase")
        p1 = eff.get_parameters()["position"]
        eff.process(ctx)
        p2 = eff.get_parameters()["position"]
        assert p2 != p1  # Position should change

    def test_chase_respects_delta_time(self, ctx):
        eff = create_effect("chase")
        # Use larger delta_times to avoid rounding issues
        eff.process(ctx)
        p1 = eff._position  # raw position, not rounded
        eff.reset()
        ctx2 = EffectContext(timestamp=2.0, delta_time=0.33, mode_parameters=ctx.mode_parameters)
        eff.process(ctx2)
        p2 = eff._position
        # 10x delta_time should give ~10x movement (allow 15% variance)
        ratio = p2 / max(0.001, p1)
        assert 8.5 < ratio < 11.5, f"Expected ~10x movement, got {ratio:.2f}x (p1={p1:.3f}, p2={p2:.3f})"

    def test_demo_cycles_effects(self, ctx):
        eff = create_effect("demo")
        names = set()
        for _ in range(100):  # Run many frames to see cycle
            ctx2 = EffectContext(
                timestamp=ctx.timestamp, delta_time=0.5,
                mode_parameters=ctx.mode_parameters,
            )
            frame = eff.process(ctx2)
            names.add(frame.metadata.get("demo_current", ""))
            ctx = ctx2
        # Should have seen at least 2 different effects
        assert len(names) >= 2
