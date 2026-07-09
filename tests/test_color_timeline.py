from __future__ import annotations

from copy import deepcopy

import pytest

from light_engine.color import evaluate_rgb_linear_timeline
from light_engine.show import ShowValidationError, TargetCatalog, validate_show_data


def _timeline():
    return {
        "interpolation": "rgb_linear",
        "keyframes": [
            {"time": 0.0, "color": [1.0, 0.0, 0.0]},
            {"time": 10.0, "color": [0.0, 0.0, 1.0]},
        ],
    }


def _catalog() -> TargetCatalog:
    return TargetCatalog(analog_zones={"zone"}, digital_strips={"strip"})


def _show_with_timeline(timeline: dict) -> dict:
    return {
        "schema_version": 1,
        "show": {
            "id": "timeline-show",
            "duration": 20.0,
            "cues": [
                {
                    "id": "timeline-cue",
                    "start": 0.0,
                    "end": 20.0,
                    "target": {"type": "digital_strip", "id": "strip"},
                    "effect": {
                        "mode": "fixed",
                        "name": "static",
                        "parameters": {"color_timeline": timeline},
                    },
                }
            ],
        },
    }


def _assert_invalid(data: dict, path: str, reason: str | None = None) -> None:
    with pytest.raises(ShowValidationError) as exc_info:
        validate_show_data(data, _catalog())
    assert exc_info.value.path == path
    if reason is not None:
        assert reason in exc_info.value.reason


def test_rgb_linear_keyframes_midpoints_and_clamps_are_exact() -> None:
    timeline = _timeline()

    assert evaluate_rgb_linear_timeline(timeline, 0.0) == pytest.approx((1.0, 0.0, 0.0))
    assert evaluate_rgb_linear_timeline(timeline, 5.0) == pytest.approx((0.5, 0.0, 0.5))
    assert evaluate_rgb_linear_timeline(timeline, -1.0) == pytest.approx((1.0, 0.0, 0.0))
    assert evaluate_rgb_linear_timeline(timeline, 11.0) == pytest.approx((0.0, 0.0, 1.0))


def test_valid_color_timeline_loads_as_normalized_tuples() -> None:
    show = validate_show_data(_show_with_timeline(_timeline()), _catalog())

    timeline = show.cues[0].effect.parameters["color_timeline"]
    assert timeline["interpolation"] == "rgb_linear"
    assert timeline["keyframes"][0]["time"] == 0.0
    assert timeline["keyframes"][1]["color"] == (0.0, 0.0, 1.0)


@pytest.mark.parametrize(
    ("mutate", "path", "reason"),
    [
        (
            lambda timeline: timeline.update({"gradient": []}),
            "show.cues[0].effect.parameters.color_timeline.gradient",
            "unknown field",
        ),
        (
            lambda timeline: timeline.update({"interpolation": "hsv"}),
            "show.cues[0].effect.parameters.color_timeline.interpolation",
            "must be one of",
        ),
        (
            lambda timeline: timeline.update({"keyframes": [{"time": 0.0, "color": [1.0, 0.0, 0.0]}]}),
            "show.cues[0].effect.parameters.color_timeline.keyframes",
            "at least 2",
        ),
        (
            lambda timeline: timeline["keyframes"][1].update({"time": 0.0}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[1].time",
            "must be > previous",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"time": -0.1}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].time",
            "must be >=",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"time": True}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].time",
            "finite number",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"time": "0.0"}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].time",
            "finite number",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"time": float("nan")}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].time",
            "finite",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"color": [1.1, 0.0, 0.0]}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].color[0]",
            "must be <=",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"color": [True, 0.0, 0.0]}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].color[0]",
            "finite number",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"color": ["1.0", 0.0, 0.0]}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].color[0]",
            "finite number",
        ),
        (
            lambda timeline: timeline["keyframes"][0].update({"color": [float("inf"), 0.0, 0.0]}),
            "show.cues[0].effect.parameters.color_timeline.keyframes[0].color[0]",
            "finite",
        ),
    ],
)
def test_invalid_color_timeline_values_fail_with_exact_paths(mutate, path: str, reason: str) -> None:
    timeline = deepcopy(_timeline())
    mutate(timeline)

    _assert_invalid(_show_with_timeline(timeline), path, reason)


def test_color_timeline_is_rejected_for_unsupported_effects() -> None:
    data = _show_with_timeline(_timeline())
    data["show"]["cues"][0]["effect"]["name"] = "comet"

    _assert_invalid(
        data,
        "show.cues[0].effect.parameters.color_timeline",
        "unknown field",
    )
