"""Tests for video zone mapping, direction reverse, and RGB+CCT channels."""

import numpy as np
import pytest
from light_engine.mapping.resolve import (
    resolve_video_color, validate_video_zone, validate_direction,
    VALID_VIDEO_ZONES,
)
from light_engine.models import VideoFeatures
from light_engine.config import Config
from light_engine.mapping import Layout, ZoneDef


class TestVideoZoneValidation:
    def test_valid_zones(self):
        for vz in VALID_VIDEO_ZONES:
            assert validate_video_zone(vz, "test") == vz

    def test_invalid_zone_raises(self):
        with pytest.raises(ValueError, match="invalid video_zone"):
            validate_video_zone("north", "test")

    def test_direction_forward_ok(self):
        assert validate_direction("forward", "test") == "forward"

    def test_direction_reverse_ok(self):
        assert validate_direction("reverse", "test") == "reverse"

    def test_direction_invalid_raises(self):
        with pytest.raises(ValueError):
            validate_direction("backward", "test")


class TestResolveVideoColor:
    @pytest.fixture
    def vf(self):
        return VideoFeatures(
            timestamp=0.0,
            average_rgb=(0.1, 0.2, 0.3),
            dominant_rgb=(0.9, 0.8, 0.7),
            zone_colors={
                "left": (1.0, 0.0, 0.0),
                "center": (0.0, 1.0, 0.0),
                "right": (0.0, 0.0, 1.0),
                "top": (1.0, 1.0, 0.0),
                "bottom": (0.5, 0.0, 0.5),
            },
        )

    def test_left(self, vf):
        r, g, b = resolve_video_color("left", vf, "test")
        assert r > 0.9 and g < 0.1 and b < 0.1

    def test_center(self, vf):
        r, g, b = resolve_video_color("center", vf, "test")
        assert g > 0.9

    def test_right(self, vf):
        r, g, b = resolve_video_color("right", vf, "test")
        assert b > 0.9

    def test_top(self, vf):
        r, g, b = resolve_video_color("top", vf, "test")
        assert r > 0.9 and g > 0.9

    def test_bottom(self, vf):
        r, g, b = resolve_video_color("bottom", vf, "test")
        assert abs(r - 0.5) < 0.1 and abs(b - 0.5) < 0.1

    def test_average(self, vf):
        r, g, b = resolve_video_color("average", vf, "test")
        assert abs(r - 0.1) < 0.01 and abs(g - 0.2) < 0.01

    def test_dominant(self, vf):
        r, g, b = resolve_video_color("dominant", vf, "test")
        assert abs(r - 0.9) < 0.01 and abs(g - 0.8) < 0.01

    def test_missing_zone_fallback(self, vf):
        vf2 = VideoFeatures(timestamp=0, average_rgb=(0.3, 0.3, 0.3),
                            dominant_rgb=(0.5, 0.5, 0.5), zone_colors={})
        r, g, b = resolve_video_color("left", vf2, "test")
        assert abs(r - 0.3) < 0.01

    def test_no_video_features(self):
        r, g, b = resolve_video_color("center", None, "test")
        assert r == 0.02 and g == 0.02 and b == 0.05

    def test_no_nan_or_inf(self, vf):
        for vz in VALID_VIDEO_ZONES:
            r, g, b = resolve_video_color(vz, vf, "test")
            assert not np.isnan(r) and not np.isinf(r)
            assert not np.isnan(g) and not np.isinf(g)
            assert not np.isnan(b) and not np.isinf(b)


class TestLayoutZoneVideoZone:
    def test_zone_def_rejects_invalid(self):
        with pytest.raises(ValueError):
            ZoneDef(id="test", video_zone="invalid")

    def test_zone_def_accepts_valid(self):
        z = ZoneDef(id="test", video_zone="top")
        assert z.video_zone == "top"

    def test_zone_def_default_center(self):
        z = ZoneDef(id="test")
        assert z.video_zone == "center"

    def test_rgbcct_zones_have_direction(self):
        Config.reset()
        layout = Layout.from_config()
        for z in layout.zones:
            assert z.direction in ("forward", "reverse")

    def test_layout_produces_distinct_video_zones(self):
        Config.reset()
        layout = Layout.from_config()
        zones_by_vz = {}
        for z in layout.zones:
            zones_by_vz.setdefault(z.video_zone, []).append(z.id)
        assert "top" in zones_by_vz
        assert "left" in zones_by_vz
        assert "right" in zones_by_vz
        assert "center" in zones_by_vz


class TestDirection:
    def test_reverse_pixels(self):
        pixels = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        reversed_pixels = list(reversed(pixels))
        assert reversed_pixels == [(0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]


class TestRGBCCTChannel:
    def test_conversion_exists_and_produces_warm_and_cool_white(self):
        from light_engine.color import rgb_to_rgbcct
        c = rgb_to_rgbcct(0.5, 0.5, 0.5)
        assert c.warm_white > 0.0
        assert c.cool_white > 0.0

    def test_pure_red_no_white(self):
        from light_engine.color import rgb_to_rgbcct
        c = rgb_to_rgbcct(1.0, 0.0, 0.0)
        assert c.warm_white < 0.1
        assert c.cool_white < 0.1

    def test_pure_green_no_white(self):
        from light_engine.color import rgb_to_rgbcct
        c = rgb_to_rgbcct(0.0, 1.0, 0.0)
        assert c.warm_white < 0.1
        assert c.cool_white < 0.1

    def test_pure_blue_no_white(self):
        from light_engine.color import rgb_to_rgbcct
        c = rgb_to_rgbcct(0.0, 0.0, 1.0)
        assert c.warm_white < 0.1
        assert c.cool_white < 0.1


class TestVideoAmbientMapping:
    def test_five_color_map(self):
        import cv2
        from light_engine.analysis.video import VideoAnalyzer
        from light_engine.effects import create_effect
        from light_engine.models import EffectContext

        Config.reset()
        H, W = 180, 320
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[0:36, :] = (0, 255, 255)
        frame[36:144, 0:106] = (0, 0, 255)
        frame[36:144, 214:320] = (255, 0, 0)
        frame[36:144, 106:214] = (0, 255, 0)
        frame[144:180, :] = (128, 0, 128)

        analyzer = VideoAnalyzer(Config())
        vf = analyzer.analyze(frame, 0.0)
        effect = create_effect("video_ambient")
        ctx = EffectContext(
            timestamp=0.0, delta_time=0.033, video_features=vf,
            mode_parameters={
                "strip_defs": [
                    {"id": "ceiling_left", "pixel_count": 3, "video_zone": "top", "direction": "forward"},
                    {"id": "ceiling_right", "pixel_count": 3, "video_zone": "top", "direction": "forward"},
                    {"id": "wall_left", "pixel_count": 3, "video_zone": "left", "direction": "forward"},
                    {"id": "wall_right", "pixel_count": 3, "video_zone": "right", "direction": "forward"},
                    {"id": "front", "pixel_count": 3, "video_zone": "center", "direction": "forward"},
                    {"id": "rear", "pixel_count": 3, "video_zone": "center", "direction": "reverse"},
                ],
                "zone_defs": [
                    {"id": "ceiling_left", "video_zone": "top"},
                    {"id": "ceiling_right", "video_zone": "top"},
                    {"id": "wall_left", "video_zone": "left"},
                    {"id": "wall_right", "video_zone": "right"},
                    {"id": "front", "video_zone": "center"},
                    {"id": "rear", "video_zone": "center"},
                ],
            },
        )
        result = effect.process(ctx)

        def avg_color(strip):
            p = strip.to_uint8()
            return tuple(int(np.mean([px[i] for px in p])) for i in range(3))

        colors = {s.strip_id: avg_color(s) for s in result.strips}
        assert colors["ceiling_left"] == colors["ceiling_right"]
        assert colors["wall_left"] != colors["wall_right"]
        assert colors["front"] == colors["rear"]
        assert len(set(colors.values())) >= 3


class TestVideoAudioFusionMapping:
    def test_zones_different(self):
        import cv2
        from light_engine.analysis.video import VideoAnalyzer
        from light_engine.effects import create_effect
        from light_engine.models import EffectContext

        Config.reset()
        H, W = 180, 320
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[0:36, :] = (0, 255, 255)
        frame[36:144, 0:106] = (0, 0, 255)
        frame[36:144, 214:320] = (255, 0, 0)
        frame[36:144, 106:214] = (0, 255, 0)

        analyzer = VideoAnalyzer(Config())
        vf = analyzer.analyze(frame, 0.0)
        effect = create_effect("video_audio_fusion")
        ctx = EffectContext(
            timestamp=0.0, delta_time=0.033, video_features=vf,
            mode_parameters={
                "strip_defs": [
                    {"id": "wall_left", "pixel_count": 5, "video_zone": "left", "direction": "forward"},
                    {"id": "wall_right", "pixel_count": 5, "video_zone": "right", "direction": "forward"},
                    {"id": "front", "pixel_count": 5, "video_zone": "center", "direction": "forward"},
                    {"id": "rear", "pixel_count": 5, "video_zone": "center", "direction": "forward"},
                ],
                "zone_defs": [
                    {"id": "wall_left", "video_zone": "left"},
                    {"id": "wall_right", "video_zone": "right"},
                    {"id": "front", "video_zone": "center"},
                    {"id": "rear", "video_zone": "center"},
                ],
            },
        )
        result = effect.process(ctx)
        def ac(s):
            p = s.to_uint8()
            return tuple(int(np.mean([px[i] for px in p])) for i in range(3))
        colors = {s.strip_id: ac(s) for s in result.strips}
        assert colors["wall_left"] != colors["wall_right"]
        assert colors["front"] == colors["rear"]

    def test_no_audio_produces_video_colors(self):
        from light_engine.effects import create_effect
        from light_engine.models import EffectContext, VideoFeatures
        Config.reset()
        vf = VideoFeatures(timestamp=0, average_rgb=(1.0, 0.0, 0.0),
                           dominant_rgb=(1.0, 0.0, 0.0),
                           zone_colors={"left": (1.0, 0.0, 0.0), "center": (0.0, 1.0, 0.0)})
        effect = create_effect("video_audio_fusion")
        ctx = EffectContext(
            timestamp=0.0, delta_time=0.033, video_features=vf, audio_features=None,
            mode_parameters={
                "strip_defs": [
                    {"id": "s1", "pixel_count": 3, "video_zone": "left", "direction": "forward"},
                    {"id": "s2", "pixel_count": 3, "video_zone": "center", "direction": "forward"},
                ],
                "zone_defs": [],
            },
        )
        result = effect.process(ctx)
        assert result.all_pixels_valid()

    def test_no_video_safe_fallback(self):
        from light_engine.effects import create_effect
        from light_engine.models import EffectContext
        Config.reset()
        effect = create_effect("video_audio_fusion")
        ctx = EffectContext(
            timestamp=0.0, delta_time=0.033, video_features=None, audio_features=None,
            mode_parameters={
                "strip_defs": [
                    {"id": "s1", "pixel_count": 3, "video_zone": "center", "direction": "forward"},
                ],
                "zone_defs": [],
            },
        )
        result = effect.process(ctx)
        assert result.all_pixels_valid()
