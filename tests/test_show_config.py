"""Tests for strict versioned show schema loading."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from light_engine.config import Config
from light_engine.mapping import Layout
from light_engine.show import (
    ShowValidationError,
    TargetCatalog,
    load_show,
    validate_show_data,
)


def _catalog() -> TargetCatalog:
    return TargetCatalog(
        analog_zones={"wall_left", "ceiling_left", "ceiling_right"},
        digital_strips={"wall_left", "wall_right", "front"},
        analog_groups={"ceiling": {"ceiling_left", "ceiling_right"}},
        digital_groups={"walls": {"wall_left", "wall_right"}},
        virtual_paths={"screen_to_wall"},
    )


def _valid_show() -> dict:
    return {
        "schema_version": 1,
        "show": {
            "id": "valid-300s",
            "duration": 300.0,
            "defaults": {
                "fade_in": 1.0,
                "fade_out": 1.0,
                "blend": "replace",
                "min_effect_hold": 8.0,
                "switch_cooldown": 6.0,
            },
            "cues": [
                {
                    "id": "fixed-wall",
                    "start": 0.0,
                    "end": 30.0,
                    "priority": 10,
                    "target": {"type": "digital_strip", "id": "wall_left"},
                    "effect": {
                        "mode": "fixed",
                        "name": "chase",
                        "parameters": {
                            "speed": 9.0,
                            "width": 6,
                            "gap": 12,
                            "color_source": "video",
                        },
                    },
                    "transition": {"fade_in": 2.0, "fade_out": 2.0},
                },
                {
                    "id": "adaptive-walls",
                    "start": 30.0,
                    "end": 300.0,
                    "target": {"type": "digital_group", "ids": ["wall_left", "wall_right"]},
                    "effect": {
                        "mode": "adaptive",
                        "allowed": {
                            "silence": "calm",
                            "calm": "breath",
                            "flowing": "color_wave",
                            "ambient": "color_wave",
                            "rhythmic": "chase",
                            "energetic": "comet",
                            "impact": "comet",
                            "transition": "color_wave",
                        },
                        "fallback": "color_wave",
                    },
                    "audio_control": {
                        "tempo_sync": "auto",
                        "tempo_confidence_min": 0.75,
                        "beat_regularity_min": 0.70,
                        "no_beat_fallback": "auto",
                        "beats_per_cycle": 4.0,
                        "speed_smoothing_seconds": 2.0,
                        "state_confirmation_seconds": 1.5,
                        "min_effect_hold": 8.0,
                        "switch_cooldown": 6.0,
                    },
                },
            ],
        },
    }


def _assert_invalid(data: dict, path: str, reason: str | None = None) -> None:
    with pytest.raises(ShowValidationError) as exc_info:
        validate_show_data(data, _catalog())
    assert exc_info.value.path == path
    if reason is not None:
        assert reason in exc_info.value.reason
    assert path in str(exc_info.value)


def test_schema_version_one_succeeds_and_missing_or_unsupported_fails() -> None:
    show = validate_show_data(_valid_show(), _catalog())
    assert show.schema_version == 1
    assert show.id == "valid-300s"

    missing = deepcopy(_valid_show())
    del missing["schema_version"]
    _assert_invalid(missing, "show.schema_version")

    unsupported = deepcopy(_valid_show())
    unsupported["schema_version"] = 2
    _assert_invalid(unsupported, "show.schema_version", "must be 1")


@pytest.mark.parametrize(
    ("fixture", "path"),
    [
        ("G1_unknown_top_level.yaml", "show.show.unexpected_field"),
        ("G2_unknown_nested_parameter.yaml", "show.cues[0].effect.parameters.sped"),
    ],
)
def test_locked_golden_unknown_fields_fail_with_nested_paths(
    fixture: str, path: str
) -> None:
    with pytest.raises(ShowValidationError) as exc_info:
        load_show(Path("tests/goldens/show_orchestration/v1") / fixture, _catalog())

    assert exc_info.value.path == path
    assert "unknown field" in exc_info.value.reason


def test_misspelled_transition_key_fails() -> None:
    data = deepcopy(_valid_show())
    data["show"]["cues"][0]["transition"]["fade_int"] = 1.0

    _assert_invalid(data, "show.cues[0].transition.fade_int", "unknown field")


def test_same_text_id_resolves_as_distinct_analog_and_digital_targets() -> None:
    data = _valid_show()
    data["show"]["cues"][0]["target"] = {"type": "analog_zone", "id": "wall_left"}
    data["show"]["cues"][1]["target"] = {"type": "digital_strip", "id": "wall_left"}

    show = validate_show_data(data, _catalog())

    assert show.cues[0].target.kind == "analog_zone"
    assert show.cues[0].target.id == "wall_left"
    assert show.cues[1].target.kind == "digital_strip"
    assert show.cues[1].target.id == "wall_left"


@pytest.mark.parametrize(
    ("mutate", "path", "reason"),
    [
        (
            lambda data: data["show"]["cues"][0]["target"].update({"id": "missing"}),
            "show.cues[0].target.id",
            "unknown digital_strip",
        ),
        (
            lambda data: data["show"]["cues"][0]["effect"].update({"name": "chas"}),
            "show.cues[0].effect.name",
            "unknown effect",
        ),
        (
            lambda data: data["show"]["cues"][0]["effect"]["parameters"].update({"spede": 1.0}),
            "show.cues[0].effect.parameters.spede",
            "unknown field",
        ),
        (
            lambda data: data["show"]["cues"][0]["transition"].update({"blend": "screen"}),
            "show.cues[0].transition.blend",
            "must be one of",
        ),
        (
            lambda data: data["show"]["cues"][0]["transition"].update({"fade_in": -1.0}),
            "show.cues[0].transition.fade_in",
            "must be >=",
        ),
        (
            lambda data: data["show"]["cues"][1]["audio_control"].update({"tempo_confidence_min": 1.1}),
            "show.cues[1].audio_control.tempo_confidence_min",
            "must be <=",
        ),
    ],
)
def test_invalid_references_and_control_values_fail_with_exact_paths(
    mutate, path: str, reason: str
) -> None:
    data = deepcopy(_valid_show())
    mutate(data)

    _assert_invalid(data, path, reason)


@pytest.mark.parametrize(
    ("value", "path"),
    [
        (float("nan"), "show.cues[0].start"),
        (float("inf"), "show.cues[0].start"),
        (True, "show.cues[0].start"),
        ("10", "show.cues[0].start"),
    ],
)
def test_numeric_inputs_are_finite_and_type_strict(value, path: str) -> None:
    data = deepcopy(_valid_show())
    data["show"]["cues"][0]["start"] = value

    _assert_invalid(data, path)


@pytest.mark.parametrize(
    ("start", "end", "path"),
    [
        (0.0, 301.0, "show.cues[0].end"),
        (30.0, 30.0, "show.cues[0].end"),
    ],
)
def test_timestamps_must_fit_duration_and_have_positive_ranges(
    start: float, end: float, path: str
) -> None:
    data = deepcopy(_valid_show())
    data["show"]["cues"][0]["start"] = start
    data["show"]["cues"][0]["end"] = end

    _assert_invalid(data, path)


def test_duplicate_cue_ids_fail() -> None:
    data = deepcopy(_valid_show())
    data["show"]["cues"][1]["id"] = "fixed-wall"

    _assert_invalid(data, "show.cues[1].id", "duplicate cue id")


def test_valid_300_second_example_round_trips_to_typed_values() -> None:
    show = load_show(Path("config/show.example.yaml"), _catalog())

    assert show.schema_version == 1
    assert show.id == "teacher-demo-v1"
    assert show.duration == 300.0
    assert show.defaults.fade_in == 1.0
    assert show.cues[0].target.kind == "virtual_path"
    assert show.cues[0].effect.name == "chase"
    assert show.cues[0].effect.parameters["width"] == 6
    assert show.cues[2].effect.mode == "adaptive"
    assert show.cues[2].audio_control is not None
    assert show.cues[2].audio_control.tempo_confidence_min == 0.75


def test_example_show_resolves_virtual_paths_from_actual_layout() -> None:
    Config.reset()
    layout = Layout.from_config(Config())
    catalog = TargetCatalog.from_layout(layout)

    show = load_show(Path("config/show.example.yaml"), catalog)

    assert catalog.virtual_paths == frozenset({"screen_to_wall"})
    assert show.cues[0].target.kind == "virtual_path"
    assert show.cues[0].target.id == "screen_to_wall"


def test_missing_actual_virtual_path_reference_fails() -> None:
    data = deepcopy(_valid_show())
    data["show"]["cues"][0]["target"] = {
        "type": "virtual_path",
        "id": "missing_path",
    }

    _assert_invalid(data, "show.cues[0].target.id", "unknown virtual_path")
