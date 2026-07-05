"""Tests for strict Phase 8 configuration validation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from light_engine.config import Config, ConfigError, validate_config


def _default_data() -> dict:
    Config.reset()
    return Config().to_dict()


def test_validate_config_accepts_default_config() -> None:
    validate_config(_default_data())


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
