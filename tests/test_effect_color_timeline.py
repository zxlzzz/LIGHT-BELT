from __future__ import annotations

import pytest

from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import Cue, EffectSpec, TargetResolver, TargetSelector, TransitionSpec
from light_engine.show.compositor import CueRenderJob


def _assert_pixels(pixels, expected) -> None:
    assert len(pixels) == len(expected)
    for pixel, expected_pixel in zip(pixels, expected):
        assert pixel == pytest.approx(expected_pixel)


def _timeline():
    return {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (1.0, 0.0, 0.0)},
            {"time": 10.0, "color": (0.0, 0.0, 1.0)},
        ),
    }


def _resolver(pixel_count: int = 4) -> TargetResolver:
    return TargetResolver(
        analog_zones=(ZoneDef(id="zone"),),
        digital_strips=(ZoneDef(id="strip", pixel_count=pixel_count),),
    )


def _cue(effect_name: str, parameters: dict, *, start: float = 0.0) -> Cue:
    return Cue(
        id=f"{effect_name}-timeline",
        start=start,
        end=start + 20.0,
        target=TargetSelector("all"),
        effect=EffectSpec(mode="fixed", name=effect_name, parameters=parameters),
        transition=TransitionSpec(blend="replace"),
    )


def _render(
    effect_name: str,
    parameters: dict,
    *,
    timestamp: float,
    delta_time: float = 0.1,
    start: float = 0.0,
    audio_features: AudioFeatures | None = None,
):
    job = CueRenderJob(_cue(effect_name, parameters, start=start), 0, _resolver())
    return job.render(
        EffectContext(
            timestamp=timestamp,
            delta_time=delta_time,
            sequence=9,
            audio_features=audio_features,
        )
    )


def test_static_color_timeline_matches_exact_keyframes_and_midpoint() -> None:
    params = {"color": [0.0, 1.0, 0.0], "color_timeline": _timeline()}

    first = _render("static", params, timestamp=0.0)
    middle = _render("static", params, timestamp=5.0)
    last = _render("static", params, timestamp=10.0)

    _assert_pixels(first.digital[0].pixels, ((1.0, 0.0, 0.0),) * 4)
    _assert_pixels(middle.digital[0].pixels, ((0.5, 0.0, 0.5),) * 4)
    _assert_pixels(last.digital[0].pixels, ((0.0, 0.0, 1.0),) * 4)
    assert middle.analog[0].color.r == pytest.approx(0.5)
    assert middle.analog[0].color.b == pytest.approx(0.5)


def test_static_color_parameter_still_works_without_timeline() -> None:
    contribution = _render("static", {"color": [0.2, 0.4, 0.6]}, timestamp=5.0)

    _assert_pixels(contribution.digital[0].pixels, ((0.2, 0.4, 0.6),) * 4)


def test_late_cue_uses_cue_local_time_for_color_timeline() -> None:
    contribution = _render(
        "static",
        {"color_timeline": _timeline()},
        start=20.0,
        timestamp=25.0,
    )

    _assert_pixels(contribution.digital[0].pixels, ((0.5, 0.0, 0.5),) * 4)


def test_repeated_static_timeline_renders_are_deterministic() -> None:
    params = {"color_timeline": _timeline()}

    first = _render("static", params, timestamp=2.5)
    second = _render("static", params, timestamp=2.5)

    _assert_pixels(second.digital[0].pixels, first.digital[0].pixels)
    assert second.analog[0].color == first.analog[0].color


def test_breath_uses_timeline_color_before_brightness_envelope() -> None:
    contribution = _render(
        "breath",
        {
            "period": 4.0,
            "min_brightness": 0.0,
            "color": [0.0, 1.0, 0.0],
            "color_timeline": _timeline(),
        },
        timestamp=1.0,
    )

    assert contribution.digital[0].pixels[0] == pytest.approx((0.9, 0.0, 0.1))


def test_audio_pulse_uses_timeline_color_and_preserves_audio_envelope() -> None:
    contribution = _render(
        "audio_pulse",
        {
            "attack": 1.0,
            "release": 0.1,
            "color": [0.0, 1.0, 0.0],
            "color_timeline": _timeline(),
        },
        timestamp=5.0,
        audio_features=AudioFeatures(timestamp=5.0, rms=0.5, silence=False),
    )

    assert contribution.digital[0].pixels[0] == pytest.approx((0.25, 0.0, 0.25))
