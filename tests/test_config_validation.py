"""Tests for strict Phase 8 configuration validation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from light_engine.config import Config, ConfigError, validate_config


def _default_data() -> dict:
    Config.reset()
    return Config().to_dict()


def test_validate_config_accepts_default_config() -> None:
    validate_config(_default_data())


def _cabin_v3_data() -> dict:
    return Config(Path("config/profiles/cabin_lighting_v3_production.yaml")).to_dict()


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda data: data["layout"]["digital_outputs"].pop(), "every logical strip"),
        (lambda data: data["layout"]["digital_outputs"][1].update({"output_id": 1}), "unique within node"),
        (lambda data: data["layout"]["digital_outputs"][1].update({"gpio": 4}), "unique within node"),
        (lambda data: data["layout"]["digital_nodes"][1].update({"pixel_count": 1}), "output pixel total 50"),
        (lambda data: data["layout"]["digital_outputs"][0].update({"pixel_count": 11}), "exact logical strip"),
        (
            lambda data: (
                data["layout"]["strips"][0].update({"pixel_count": 101}),
                data["layout"]["digital_outputs"][0].update({"pixel_count": 101}),
            ),
            "<= 100",
        ),
    ],
)
def test_cabin_v3_mapping_rejects_incomplete_or_conflicting_outputs(mutate, expected) -> None:
    data = deepcopy(_cabin_v3_data())
    mutate(data)
    with pytest.raises(ConfigError, match=expected):
        validate_config(data)


@pytest.mark.parametrize(
    ("mutate", "path", "field", "value", "expected"),
    [
        (
            lambda data: data["outputs"].update({"mode": "auto"}),
            "outputs",
            "mode",
            "auto",
            "one of",
        ),
        (
            lambda data: data["outputs"].update({"exit_safe_state": "yes"}),
            "outputs",
            "exit_safe_state",
            "yes",
            "boolean",
        ),
        (
            lambda data: data["system"]["smoothing"].update({"gamma": 0.0}),
            "system.smoothing",
            "gamma",
            0.0,
            "finite number > 0.0",
        ),
        (
            lambda data: data["outputs"]["transform"].update({"power_limit": -1.0}),
            "outputs.transform",
            "power_limit",
            -1.0,
            "finite number >= 0.0",
        ),
        (
            lambda data: data["outputs"]["transform"].update(
                {"per_zone_warm_bias": {"missing": 1.0}}
            ),
            "outputs.transform",
            "per_zone_warm_bias",
            "missing",
            "existing layout.zones id",
        ),
        (
            lambda data: data["system"].update({"platform": "rk3568"}),
            "system",
            "platform",
            "rk3568",
            "one of",
        ),
        (
            lambda data: data["layout"]["analog_nodes"].pop(),
            "layout",
            "analog_nodes",
            5,
            "exactly 6",
        ),
        (
            lambda data: data["layout"]["digital_segments"][0].update(
                {"node_id": 999}
            ),
            "layout.digital_segments[0]",
            "node_id",
            999,
            "existing layout.digital_nodes node_id",
        ),
        (
            lambda data: data["layout"].setdefault("virtual_paths", []).append(
                {
                    "id": "bad_path",
                    "segments": [
                        {
                            "strip_id": "missing",
                            "source_start": 0,
                            "pixel_count": 1,
                            "direction": "forward",
                        }
                    ],
                }
            ),
            "layout.virtual_paths[1].segments[0]",
            "strip_id",
            "missing",
            "existing layout.strips id",
        ),
        (
            lambda data: data["layout"].setdefault("virtual_paths", []).append(
                {
                    "id": "bad_path",
                    "segments": [
                        {
                            "strip_id": data["layout"]["strips"][0]["id"],
                            "source_start": 1,
                            "pixel_count": data["layout"]["strips"][0]["pixel_count"],
                            "direction": "forward",
                        }
                    ],
                }
            ),
            "layout.virtual_paths[1].segments[0]",
            "pixel_count",
            144,
            "source range",
        ),
        (
            lambda data: data["layout"].setdefault("virtual_paths", []).append(
                {
                    "id": "bad_path",
                    "segments": [
                        {
                            "strip_id": data["layout"]["strips"][0]["id"],
                            "source_start": 0,
                            "pixel_count": 1,
                            "direction": "sideways",
                        }
                    ],
                }
            ),
            "layout.virtual_paths[1].segments[0]",
            "direction",
            "sideways",
            "one of",
        ),
        (
            lambda data: data["layout"].setdefault("virtual_paths", []).append(
                {
                    "id": "bad_path",
                    "segments": [
                        {
                            "strip_id": data["layout"]["strips"][0]["id"],
                            "source_start": 0,
                            "pixel_count": 1,
                            "direction": "forward",
                        },
                        {
                            "strip_id": data["layout"]["strips"][0]["id"],
                            "source_start": 0,
                            "pixel_count": 1,
                            "direction": "reverse",
                        },
                    ],
                }
            ),
            "layout.virtual_paths[1].segments[1]",
            "source_start",
            0,
            "non-overlapping source pixels",
        ),
    ],
)
def test_invalid_config_errors_include_diagnostic_fields(
    mutate, path, field, value, expected
) -> None:
    data = deepcopy(_default_data())
    mutate(data)

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    error = exc_info.value
    assert error.path == path
    assert error.field == field
    assert error.value == value
    assert expected in error.expected
    message = str(error)
    assert path in message
    assert field in message
    assert repr(value) in message
    assert expected in message
