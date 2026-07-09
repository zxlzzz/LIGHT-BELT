"""Tests for lighting effects."""

import pytest
from light_engine.effects.comet import CometEffect
from light_engine.effects import create_effect, list_effects, BaseEffect
from light_engine.effects.base import _EFFECT_REGISTRY
from light_engine.mapping import ZoneDef
from light_engine.models import (
    AudioFeatures,
    EffectContext,
    MusicControlState,
    RGBCCTColor,
    VideoFeatures,
)
from light_engine.show import Cue, EffectSpec, TargetResolver, TargetSelector, TransitionSpec
from light_engine.show.compositor import CueRenderJob


def _assert_rgbcct_zones(frame):
    for zone in frame.zones:
        assert isinstance(zone.color, RGBCCTColor)


def _assert_sequence(frame, ctx):
    assert frame.sequence == ctx.sequence


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
        _assert_sequence(frame, ctx)

    def test_breath(self, ctx):
        eff = create_effect("breath")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_color_wave(self, ctx):
        eff = create_effect("color_wave")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_chase(self, ctx):
        eff = create_effect("chase")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_comet(self, ctx):
        eff = create_effect("comet")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_audio_pulse(self, ctx):
        eff = create_effect("audio_pulse")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_bass_pulse(self, ctx):
        eff = create_effect("bass_pulse")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_spectrum(self, ctx):
        eff = create_effect("spectrum")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_video_ambient(self, ctx):
        eff = create_effect("video_ambient")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_video_audio_fusion(self, ctx):
        eff = create_effect("video_audio_fusion")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_calm(self, ctx):
        eff = create_effect("calm")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)

    def test_demo(self, ctx):
        eff = create_effect("demo")
        frame = eff.process(ctx)
        assert frame.all_pixels_valid()
        _assert_rgbcct_zones(frame)
        _assert_sequence(frame, ctx)
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


def test_two_comet_cues_with_same_effect_name_have_independent_state(monkeypatch):
    hues = iter([15.0, 195.0])
    monkeypatch.setattr("light_engine.effects.comet.random.uniform", lambda _a, _b: next(hues))
    resolver = TargetResolver(
        (),
        (
            ZoneDef(id="strip_a", pixel_count=8),
            ZoneDef(id="strip_b", pixel_count=8),
        ),
    )
    cue_a = Cue(
        id="comet-a",
        start=0.0,
        end=10.0,
        target=TargetSelector("digital_strip", id="strip_a"),
        effect=EffectSpec(mode="fixed", name="comet"),
        transition=TransitionSpec(blend="replace"),
    )
    cue_b = Cue(
        id="comet-b",
        start=0.0,
        end=10.0,
        target=TargetSelector("digital_strip", id="strip_b"),
        effect=EffectSpec(mode="fixed", name="comet"),
        transition=TransitionSpec(blend="replace"),
    )
    job_a = CueRenderJob(cue_a, 0, resolver, effect=CometEffect("comet"))
    job_b = CueRenderJob(cue_b, 1, resolver, effect=CometEffect("comet"))
    ctx = EffectContext(timestamp=1.0, delta_time=0.25, sequence=4)

    contribution_a = job_a.render(ctx)
    contribution_b = job_b.render(ctx)

    assert job_a.effect is not job_b.effect
    assert job_a.effect._positions == {"strip_a": pytest.approx(0.375)}
    assert job_b.effect._positions == {"strip_b": pytest.approx(0.375)}
    assert contribution_a.digital[0].strip_id == "strip_a"
    assert contribution_b.digital[0].strip_id == "strip_b"


def _single_strip_resolver(pixel_count: int = 8) -> TargetResolver:
    return TargetResolver(
        (ZoneDef(id="zone"),),
        (ZoneDef(id="strip", pixel_count=pixel_count),),
    )


def _fixed_cue(effect_name: str, parameters=None) -> Cue:
    return Cue(
        id=f"{effect_name}-cue",
        start=0.0,
        end=10.0,
        target=TargetSelector("all"),
        effect=EffectSpec(
            mode="fixed",
            name=effect_name,
            parameters=parameters or {},
        ),
        transition=TransitionSpec(blend="replace"),
    )


def _render_fixed(effect_name: str, parameters=None, *, timestamp=1.0, delta_time=1.0):
    job = CueRenderJob(_fixed_cue(effect_name, parameters), 0, _single_strip_resolver())
    return job.render(EffectContext(timestamp=timestamp, delta_time=delta_time, sequence=7))


def test_static_cue_color_overrides_default_rendered_channels():
    default = _render_fixed("static")
    overridden = _render_fixed("static", {"color": [1.0, 0.0, 0.0]})

    assert default.digital[0].pixels[0] != overridden.digital[0].pixels[0]
    assert overridden.digital[0].pixels == ((1.0, 0.0, 0.0),) * 8
    assert overridden.analog[0].color.r == pytest.approx(1.0)
    assert overridden.analog[0].color.g == pytest.approx(0.0)
    assert overridden.analog[0].color.b == pytest.approx(0.0)


def test_breath_period_uses_cue_local_time_and_omitted_period_keeps_default():
    default = _render_fixed("breath", {"color": [1.0, 0.0, 0.0]}, timestamp=1.0)
    explicit_default = _render_fixed(
        "breath",
        {"period": 4.0, "color": [1.0, 0.0, 0.0]},
        timestamp=1.0,
    )
    faster = _render_fixed(
        "breath",
        {"period": 2.0, "color": [1.0, 0.0, 0.0]},
        timestamp=1.0,
    )

    assert default.digital[0].pixels[0] == pytest.approx(explicit_default.digital[0].pixels[0])
    assert default.digital[0].pixels[0][0] == pytest.approx(1.0)
    assert faster.digital[0].pixels[0][0] == pytest.approx(0.525)


def test_chase_runtime_speed_width_gap_and_direction_change_pixel_placement():
    forward = _render_fixed(
        "chase",
        {
            "speed": 2.0,
            "width": 1,
            "gap": 2,
            "direction": "forward",
            "trail": 1.0,
            "color_source": "solid",
        },
    )
    reverse = _render_fixed(
        "chase",
        {
            "speed": 2.0,
            "width": 1,
            "gap": 2,
            "direction": "reverse",
            "trail": 1.0,
            "color_source": "solid",
        },
    )
    wider_gap = _render_fixed(
        "chase",
        {
            "speed": 1.0,
            "width": 2,
            "gap": 4,
            "direction": "forward",
            "trail": 1.0,
            "color_source": "solid",
        },
    )

    def lit_indexes(contribution):
        return [
            index
            for index, pixel in enumerate(contribution.digital[0].pixels)
            if max(pixel) > 0.0
        ]

    assert lit_indexes(forward) == [0, 2, 3, 5, 6]
    assert lit_indexes(reverse) == [0, 1, 3, 4, 6, 7]
    assert lit_indexes(wider_gap) == [1, 2, 3, 7]


def test_comet_runtime_speed_tail_length_and_decay_change_head_tail_output(monkeypatch):
    monkeypatch.setattr("light_engine.effects.comet.random.uniform", lambda _a, _b: 0.0)
    short_tail = _render_fixed(
        "comet",
        {"speed": 1.0, "tail_length": 0.25, "decay": 1.0},
    )
    long_tail = _render_fixed(
        "comet",
        {"speed": 1.0, "tail_length": 0.75, "decay": 1.0},
    )
    dim_head = _render_fixed(
        "comet",
        {"speed": 3.0, "tail_length": 0.25, "decay": 0.5},
    )

    short_pixels = short_tail.digital[0].pixels
    long_pixels = long_tail.digital[0].pixels
    assert [index for index, pixel in enumerate(short_pixels) if pixel[0] > 0.0] == [0, 1]
    assert [index for index, pixel in enumerate(long_pixels) if pixel[0] > 0.0] == [
        0,
        1,
        4,
        5,
        6,
        7,
    ]
    assert dim_head.digital[0].pixels[3][0] == pytest.approx(0.5)


def test_video_ambient_smoothing_parameter_changes_deterministic_video_output():
    effect = create_effect("video_ambient")
    first = EffectContext(
        timestamp=0.0,
        delta_time=0.1,
        video_features=VideoFeatures(
            timestamp=0.0,
            average_rgb=(1.0, 0.0, 0.0),
            dominant_rgb=(1.0, 0.0, 0.0),
            brightness=1.0,
            zone_colors={"center": (1.0, 0.0, 0.0)},
        ),
        mode_parameters={
            "strip_defs": [{"id": "strip", "pixel_count": 1, "video_zone": "center"}],
            "smoothing": 0.0,
        },
    )
    second = EffectContext(
        timestamp=0.1,
        delta_time=0.1,
        video_features=VideoFeatures(
            timestamp=0.1,
            average_rgb=(0.0, 0.0, 1.0),
            dominant_rgb=(0.0, 0.0, 1.0),
            brightness=1.0,
            zone_colors={"center": (0.0, 0.0, 1.0)},
        ),
        mode_parameters={
            "strip_defs": [{"id": "strip", "pixel_count": 1, "video_zone": "center"}],
            "smoothing": 0.9,
        },
    )

    effect.process(first)
    smoothed = effect.process(second)
    instant = create_effect("video_ambient").process(
        EffectContext(
            timestamp=0.1,
            delta_time=0.1,
            video_features=second.video_features,
            mode_parameters={**second.mode_parameters, "smoothing": 0.0},
        )
    )

    assert smoothed.strips[0].pixels[0] == pytest.approx((0.9, 0.0, 0.1))
    assert instant.strips[0].pixels[0] == pytest.approx((0.0, 0.0, 1.0))


def test_video_audio_fusion_runtime_weights_change_rendered_pixels():
    video = VideoFeatures(
        timestamp=0.0,
        average_rgb=(1.0, 0.0, 0.0),
        dominant_rgb=(1.0, 0.0, 0.0),
        brightness=1.0,
        zone_colors={"center": (1.0, 0.0, 0.0)},
    )
    audio = AudioFeatures(timestamp=0.0, rms=0.0, silence=False)
    base_params = {
        "strip_defs": [{"id": "strip", "pixel_count": 1, "video_zone": "center"}],
        "audio_weight": 0.0,
        "bass_boost": 0.0,
        "treble_limit": 0.0,
    }

    video_driven = create_effect("video_audio_fusion").process(
        EffectContext(
            timestamp=0.0,
            delta_time=0.1,
            video_features=video,
            audio_features=audio,
            mode_parameters={**base_params, "video_weight": 1.0},
        )
    )
    audio_driven = create_effect("video_audio_fusion").process(
        EffectContext(
            timestamp=0.0,
            delta_time=0.1,
            video_features=video,
            audio_features=audio,
            mode_parameters={**base_params, "video_weight": 0.0},
        )
    )

    assert video_driven.strips[0].pixels[0][0] > 0.1
    assert audio_driven.strips[0].pixels[0] == pytest.approx((0.0, 0.0, 0.0))


def test_adaptive_render_path_preserves_runtime_parameters_for_selected_effect():
    cue = Cue(
        id="adaptive-static",
        start=0.0,
        end=10.0,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(
            mode="adaptive",
            allowed={"silence": "static"},
            fallback="static",
        ),
    )
    job = CueRenderJob(cue, 0, _single_strip_resolver())

    contribution = job.render(
        EffectContext(
            timestamp=1.0,
            delta_time=0.1,
            music_control_state=MusicControlState(timestamp=1.0, energy=0.0),
            mode_parameters={"color": [0.0, 1.0, 0.0]},
        )
    )

    assert contribution.digital[0].pixels == ((0.0, 1.0, 0.0),) * 8


def test_color_wave_runtime_speed_width_and_hue_cycle_rate_change_pixels():
    baseline = create_effect("color_wave").process(
        EffectContext(
            timestamp=0.0,
            delta_time=0.5,
            mode_parameters={
                "strip_defs": [{"id": "strip", "pixel_count": 3}],
                "speed": 1.0,
                "width": 0.3,
                "hue_cycle_rate": 0.1,
            },
        )
    )
    overridden = create_effect("color_wave").process(
        EffectContext(
            timestamp=0.0,
            delta_time=0.5,
            mode_parameters={
                "strip_defs": [{"id": "strip", "pixel_count": 3}],
                "speed": 3.0,
                "width": 0.8,
                "hue_cycle_rate": 0.4,
            },
        )
    )

    assert overridden.strips[0].pixels != pytest.approx(baseline.strips[0].pixels)


@pytest.mark.parametrize(
    ("effect_name", "feature_kwargs"),
    [
        ("audio_pulse", {"rms": 1.0}),
        ("bass_pulse", {"bass": 1.0}),
    ],
)
def test_audio_pulse_runtime_attack_release_and_color_change_channels(effect_name, feature_kwargs):
    fast_attack = create_effect(effect_name)
    slow_attack = create_effect(effect_name)
    attack_ctx = EffectContext(
        timestamp=0.0,
        delta_time=0.1,
        audio_features=AudioFeatures(timestamp=0.0, silence=False, **feature_kwargs),
        mode_parameters={
            "strip_defs": [{"id": "strip", "pixel_count": 1}],
            "attack": 1.0,
            "release": 0.1,
            "color": [0.0, 1.0, 0.0],
        },
    )
    slow_ctx = EffectContext(
        timestamp=0.0,
        delta_time=0.1,
        audio_features=attack_ctx.audio_features,
        mode_parameters={**attack_ctx.mode_parameters, "attack": 0.1},
    )

    fast_frame = fast_attack.process(attack_ctx)
    slow_frame = slow_attack.process(slow_ctx)
    assert fast_frame.strips[0].pixels[0][1] > slow_frame.strips[0].pixels[0][1]
    assert fast_frame.strips[0].pixels[0][0] == pytest.approx(0.0)

    release_fast = create_effect(effect_name)
    release_slow = create_effect(effect_name)
    release_fast.process(attack_ctx)
    release_slow.process(attack_ctx)
    silent = AudioFeatures(timestamp=0.1, silence=False, **{key: 0.0 for key in feature_kwargs})
    fast_release_frame = release_fast.process(
        EffectContext(
            timestamp=0.1,
            delta_time=0.1,
            audio_features=silent,
            mode_parameters={**attack_ctx.mode_parameters, "release": 1.0},
        )
    )
    slow_release_frame = release_slow.process(
        EffectContext(
            timestamp=0.1,
            delta_time=0.1,
            audio_features=silent,
            mode_parameters={**attack_ctx.mode_parameters, "release": 0.01},
        )
    )
    assert fast_release_frame.strips[0].pixels[0][1] < slow_release_frame.strips[0].pixels[0][1]


def test_spectrum_runtime_zone_lists_route_bands_to_outputs():
    audio = AudioFeatures(
        timestamp=0.0,
        bass=1.0,
        mid=0.5,
        treble=0.25,
        silence=False,
    )
    frame = create_effect("spectrum").process(
        EffectContext(
            timestamp=0.0,
            delta_time=0.1,
            audio_features=audio,
            mode_parameters={
                "strip_defs": [
                    {"id": "bass_strip", "pixel_count": 1},
                    {"id": "mid_strip", "pixel_count": 1},
                    {"id": "treble_strip", "pixel_count": 1},
                ],
                "bass_zones": ["bass_strip"],
                "mid_zones": ["mid_strip"],
                "treble_zones": ["treble_strip"],
            },
        )
    )

    pixels = {strip.strip_id: strip.pixels[0] for strip in frame.strips}
    assert pixels["bass_strip"][0] > pixels["bass_strip"][1]
    assert pixels["mid_strip"][1] > pixels["mid_strip"][0]
    assert pixels["treble_strip"][2] > pixels["treble_strip"][0]


def test_calm_runtime_period_and_color_change_rendered_channels():
    red_slow = create_effect("calm").process(
        EffectContext(
            timestamp=0.0,
            delta_time=1.0,
            mode_parameters={
                "strip_defs": [{"id": "strip", "pixel_count": 1}],
                "period": 12.0,
                "color": [1.0, 0.0, 0.0],
            },
        )
    )
    blue_fast = create_effect("calm").process(
        EffectContext(
            timestamp=0.0,
            delta_time=1.0,
            mode_parameters={
                "strip_defs": [{"id": "strip", "pixel_count": 1}],
                "period": 2.0,
                "color": [0.0, 0.0, 1.0],
            },
        )
    )

    assert blue_fast.strips[0].pixels[0] != pytest.approx(red_slow.strips[0].pixels[0])
    assert blue_fast.strips[0].pixels[0][2] > blue_fast.strips[0].pixels[0][0]


def test_demo_runtime_cycle_interval_and_effects_change_selected_effect():
    frame = create_effect("demo").process(
        EffectContext(
            timestamp=0.0,
            delta_time=0.01,
            mode_parameters={
                "strip_defs": [{"id": "strip", "pixel_count": 1}],
                "cycle_interval": 0.001,
                "effects": ["static", "breath"],
            },
        )
    )

    assert frame.metadata["demo_current"] == "breath"
