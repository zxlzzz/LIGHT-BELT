"""Tests for strict Phase 8 configuration validation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

import pytest

from light_engine.config import Config, ConfigError, validate_config
from light_engine.outputs import create_outputs
from light_engine.outputs.udp_output import UdpOutputV3


def _default_data() -> dict:
    Config.reset()
    return Config().to_dict()


def test_validate_config_accepts_default_config() -> None:
    validate_config(_default_data())


def test_project_declares_pyserial_for_production_rs485_installation() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "pyserial>=3.5" in metadata["project"]["dependencies"]


def _cabin_v3_data() -> dict:
    return Config(Path("config/profiles/cabin-lighting-v3-production.yaml")).to_dict()


PHASE31_PROFILES = (
    Path("config/profiles/cabin-lighting-v3-production.yaml"),
    Path("config/profiles/cabin-lighting-v3-site-local.yaml"),
    Path("config/profiles/ws2811-installed-one-esp-per-strip.yaml"),
)
ALL_PROFILES = tuple(sorted(Path("config/profiles").glob("*.yaml")))


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_every_checked_in_profile_loads(profile: Path) -> None:
    Config.reset()
    Config(profile)


@pytest.mark.parametrize(
    "enabled",
    [
        [],
        ["udp_v33"],
        ["udp_v3", "udp_v3"],
    ],
)
def test_outputs_enabled_rejects_empty_unknown_or_duplicate_names(
    enabled: list[str],
) -> None:
    data = deepcopy(_default_data())
    data["outputs"]["enabled"] = enabled

    with pytest.raises(ConfigError):
        validate_config(data)


def test_topology_v3_production_requires_udp_v3_output() -> None:
    data = deepcopy(_cabin_v3_data())
    data["outputs"]["enabled"] = ["rs485_v2"]

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    assert exc_info.value.path == "outputs"
    assert exc_info.value.field == "enabled"
    assert "udp_v3" in exc_info.value.expected


def test_topology_v3_production_requires_explicit_output_policy() -> None:
    data = deepcopy(_cabin_v3_data())
    data["layout"].pop("digital_output_policy")

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    assert exc_info.value.path == "layout"
    assert exc_info.value.field == "digital_output_policy"
    assert "explicit" in exc_info.value.expected


def test_one_output_gpio4_production_requires_scheduled_presentation() -> None:
    data = deepcopy(_cabin_v3_data())
    data["outputs"]["udp_v3"]["presentation"] = {"mode": "immediate"}

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    error = exc_info.value
    assert error.path == "outputs.udp_v3.presentation"
    assert error.field == "mode"
    assert "scheduled" in error.expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lead_us", 0),
        ("lead_us", 100_001),
        ("session_start_repeats", 1),
        ("session_start_repeats", 11),
        ("session_start_spacing_us", -1),
        ("session_start_spacing_us", 10_001),
    ],
)
def test_scheduled_presentation_rejects_invalid_timing(
    field: str, value: int
) -> None:
    data = deepcopy(_cabin_v3_data())
    data["outputs"]["udp_v3"]["presentation"][field] = value

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    assert exc_info.value.path == "outputs.udp_v3.presentation"
    assert exc_info.value.field == field


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("interval_us", 0),
        ("interval_us", 1_000_001),
        ("startup_count", 2),
        ("startup_count", 33),
        ("startup_spacing_us", 0),
        ("startup_spacing_us", 100_001),
    ],
)
def test_scheduled_presentation_rejects_invalid_beacon_window(
    field: str, value: int
) -> None:
    data = deepcopy(_cabin_v3_data())
    data["outputs"]["udp_v3"]["presentation"]["beacon"][field] = value

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    assert exc_info.value.path == "outputs.udp_v3.presentation.beacon"
    assert exc_info.value.field == field


def test_create_outputs_wires_production_schedule_from_profile() -> None:
    Config.reset()
    config = Config(Path("config/profiles/cabin-lighting-v3-site-local.yaml"))

    outputs = create_outputs(config)
    udp = outputs["udp_v3"]

    assert isinstance(udp, UdpOutputV3)
    capabilities = udp.capabilities()
    assert capabilities["scheduled_apply_enabled"] is True
    assert capabilities["schedule_lead_us"] == 20_000
    assert capabilities["session_start_repeats"] == 3
    assert capabilities["session_start_spacing_us"] == 2_000
    assert capabilities["clock_beacon_interval_us"] == 500_000
    assert capabilities["clock_beacon_targets"] == 13


@pytest.mark.parametrize(
    "host",
    [
        "999.168.31.201",
        "192.168.31",
        "bad_host",
        "-bad.example",
        "bad-.example",
        "2001:db8::1",
    ],
)
def test_digital_node_host_rejects_invalid_ipv4_or_hostname(host: str) -> None:
    data = deepcopy(_cabin_v3_data())
    data["layout"]["digital_nodes"][0]["host"] = host

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    assert exc_info.value.path == "layout.digital_nodes[0]"
    assert exc_info.value.field == "host"


def test_digital_node_accepts_valid_hostname() -> None:
    data = deepcopy(_cabin_v3_data())
    data["layout"]["digital_nodes"][0]["host"] = "controller-01.example.local"

    validate_config(data)


def test_digital_node_port_rejects_values_above_udp_limit() -> None:
    data = deepcopy(_cabin_v3_data())
    data["layout"]["digital_nodes"][0]["port"] = 65536

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    assert exc_info.value.path == "layout.digital_nodes[0]"
    assert exc_info.value.field == "port"
    assert "65535" in exc_info.value.expected


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda data: (
                data["layout"].update(
                    {"digital_output_policy": "multi_output_diagnostic"}
                ),
                data["layout"]["digital_outputs"].pop(),
            ),
            "every logical strip",
        ),
        (
            lambda data: (
                data["layout"].update(
                    {"digital_output_policy": "multi_output_diagnostic"}
                ),
                data["layout"]["digital_outputs"][1].update(
                    {"node_id": 1, "output_id": 1, "gpio": 5}
                ),
            ),
            "unique within node",
        ),
        (
            lambda data: (
                data["layout"].update(
                    {"digital_output_policy": "multi_output_diagnostic"}
                ),
                data["layout"]["digital_outputs"][1].update(
                    {"node_id": 1, "output_id": 2, "gpio": 4}
                ),
            ),
            "unique within node",
        ),
        (lambda data: data["layout"]["digital_nodes"][1].update({"pixel_count": 1}), "output pixel total 10"),
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


def test_digital_nodes_reject_duplicate_udp_endpoint() -> None:
    data = deepcopy(_cabin_v3_data())
    first = data["layout"]["digital_nodes"][0]
    duplicate = data["layout"]["digital_nodes"][1]
    duplicate.update({"host": first["host"], "port": first["port"]})

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    error = exc_info.value
    assert error.path == "layout.digital_nodes[1]"
    assert error.field == "endpoint"
    assert error.value == (first["host"], first["port"])
    assert "unique digital node UDP (host, port) endpoint" in error.expected


@pytest.mark.parametrize(
    ("mutate", "field", "value"),
    [
        (
            lambda data: data["layout"]["digital_outputs"][0].update(
                {"output_id": 2}
            ),
            "output_id",
            2,
        ),
        (
            lambda data: data["layout"]["digital_outputs"][0].update(
                {"gpio": 5}
            ),
            "gpio",
            5,
        ),
        (
            lambda data: data["layout"]["digital_outputs"][1].update(
                {"node_id": 1}
            ),
            "node_id",
            1,
        ),
        (
            lambda data: data["layout"]["digital_outputs"].pop(),
            "node_id",
            13,
        ),
    ],
)
def test_one_output_gpio4_policy_rejects_nonconforming_node_outputs(
    mutate, field, value
) -> None:
    data = deepcopy(_cabin_v3_data())
    mutate(data)

    with pytest.raises(ConfigError) as exc_info:
        validate_config(data)

    error = exc_info.value
    assert error.field == field
    assert error.value == value
    assert "one_output_gpio4" in error.expected


@pytest.mark.parametrize("profile", PHASE31_PROFILES)
def test_phase31_profiles_enable_one_output_gpio4_policy(profile: Path) -> None:
    Config.reset()
    config = Config(profile)
    assert config.get("layout.digital_output_policy") == "one_output_gpio4"
    nodes = config.get("layout.digital_nodes")
    outputs = config.get("layout.digital_outputs")
    assert len(nodes) == len(outputs)
    assert all(output["output_id"] == 1 and output["gpio"] == 4 for output in outputs)
    assert config.get("outputs.udp_v3.presentation.mode") == "scheduled"
    assert config.get("outputs.udp_v3.presentation.lead_us") == 20_000
    assert config.get("outputs.udp_v3.presentation.session_start_repeats") == 3
    assert config.get("outputs.udp_v3.presentation.session_start_spacing_us") == 2_000
    assert config.get("outputs.udp_v3.presentation.beacon.startup_count") >= 3


@pytest.mark.parametrize(
    ("profile", "expected_outputs"),
    [
        (
            Path("config/profiles/node2-effects-demo.yaml"),
            [(1, 4), (2, 5), (3, 6)],
        ),
        (
            Path("config/profiles/node2-strip42-gpio4-diagnostic.yaml"),
            [(1, 4)],
        ),
    ],
)
def test_udp_v3_diagnostic_profiles_retain_explicit_output_flexibility(
    profile: Path, expected_outputs: list[tuple[int, int]]
) -> None:
    Config.reset()
    config = Config(profile)
    assert config.get("layout.digital_output_policy") == "multi_output_diagnostic"
    assert config.get("outputs.udp_v3.presentation.mode") == "immediate"
    assert [
        (output["output_id"], output["gpio"])
        for output in config.get("layout.digital_outputs")
    ] == expected_outputs


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
