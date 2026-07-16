"""Configuration loading and validation."""

from __future__ import annotations

import ipaddress
import math
import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

# Default config directory relative to project root
DEFAULT_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

_KNOWN_OUTPUTS = {
    "json",
    "null",
    "rs485_v2",
    "simulator",
    "udp_v2",
    "udp_v3",
}
_HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class ConfigError(Exception):
    """Configuration error with path, field, value, and expected info."""

    def __init__(self, path: str, field: str, value: Any, expected: str):
        self.path = path
        self.field = field
        self.value = value
        self.expected = expected
        super().__init__(
            f"Config error in {path}: field '{field}' = {value!r}, expected {expected}"
        )


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(path: Path) -> dict:
    """Load and parse a YAML file safely (no arbitrary code execution)."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_range(
    value: float,
    field: str,
    path: str,
    min_val: float = 0.0,
    max_val: float = 1.0,
) -> float:
    """Validate a float config value is within range."""
    if not isinstance(value, (int, float)):
        raise ConfigError(path, field, value, f"number in [{min_val}, {max_val}]")
    if value < min_val or value > max_val:
        raise ConfigError(path, field, value, f"number in [{min_val}, {max_val}]")
    return float(value)


def validate_choice(value: str, field: str, path: str, choices: list[str]) -> str:
    """Validate a string config value is one of allowed choices."""
    if value not in choices:
        raise ConfigError(path, field, value, f"one of {choices}")
    return value


def validate_positive_int(value: int, field: str, path: str) -> int:
    """Validate a positive integer config value."""
    if not isinstance(value, int) or value < 0:
        raise ConfigError(path, field, value, "non-negative integer")
    return value


def _require_mapping(value: Any, path: str, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(path, field, value, "mapping")
    return value


def _require_list(value: Any, path: str, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(path, field, value, "list")
    return value


def _require_bool(value: Any, path: str, field: str) -> bool:
    if type(value) is not bool:
        raise ConfigError(path, field, value, "boolean")
    return value


def _require_nonempty_str(value: Any, path: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(path, field, value, "non-empty string")
    return value


def _require_ipv4_or_hostname(value: Any, path: str, field: str) -> str:
    host = _require_nonempty_str(value, path, field)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if isinstance(address, ipaddress.IPv4Address):
            return host
        raise ConfigError(path, field, value, "valid IPv4 address or hostname")

    # Do not reinterpret a malformed dotted IPv4 address as a numeric hostname.
    if all(character.isdigit() or character == "." for character in host):
        raise ConfigError(path, field, value, "valid IPv4 address or hostname")
    hostname = host[:-1] if host.endswith(".") else host
    labels = hostname.split(".")
    if (
        not hostname
        or len(hostname) > 253
        or any(not _HOST_LABEL_RE.fullmatch(label) for label in labels)
    ):
        raise ConfigError(path, field, value, "valid IPv4 address or hostname")
    return host


def _require_int(value: Any, path: str, field: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ConfigError(path, field, value, f"integer >= {minimum}")
    return value


def _require_number(value: Any, path: str, field: str, minimum: float) -> float:
    if not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(path, field, value, f"number >= {minimum}")
    return float(value)


def _require_finite_number(
    value: Any,
    path: str,
    field: str,
    *,
    minimum: float,
    strictly_greater: bool = False,
) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ConfigError(path, field, value, "finite number")
    number = float(value)
    if number < minimum or (strictly_greater and number <= minimum):
        comparator = ">" if strictly_greater else ">="
        raise ConfigError(path, field, value, f"finite number {comparator} {minimum}")
    return number


def _validate_choice(value: Any, path: str, field: str, choices: list[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ConfigError(path, field, value, f"one of {choices}")
    return value


def validate_config(data: dict[str, Any]) -> None:
    """Validate the complete v2 configuration surface.

    Raises:
        ConfigError: includes path, field, value, and expected constraint.
    """
    root = _require_mapping(data, "config", "root")
    system = _require_mapping(root.get("system"), "system", "system")
    outputs = _require_mapping(root.get("outputs"), "outputs", "outputs")
    layout = _require_mapping(root.get("layout"), "layout", "layout")

    _validate_choice(
        system.get("platform"),
        "system",
        "platform",
        ["windows", "linux_arm64"],
    )
    clock = _require_mapping(system.get("clock"), "system.clock", "clock")
    _validate_choice(
        clock.get("mode"),
        "system.clock",
        "mode",
        ["internal", "offline", "fake", "mpv"],
    )
    _require_number(system.get("output_fps"), "system", "output_fps", 1.0)
    smoothing = _require_mapping(
        system.get("smoothing"), "system.smoothing", "smoothing"
    )
    _require_finite_number(
        smoothing.get("max_brightness"),
        "system.smoothing",
        "max_brightness",
        minimum=0.0,
    )
    _require_finite_number(
        smoothing.get("gamma"),
        "system.smoothing",
        "gamma",
        minimum=0.0,
        strictly_greater=True,
    )

    output_mode = _validate_choice(
        outputs.get("mode"),
        "outputs",
        "mode",
        ["memory", "fake", "production"],
    )
    _require_bool(outputs.get("exit_safe_state"), "outputs", "exit_safe_state")
    enabled = _require_list(outputs.get("enabled"), "outputs", "enabled")
    if not enabled:
        raise ConfigError("outputs", "enabled", enabled, "non-empty list of known outputs")
    seen_outputs: set[str] = set()
    for idx, value in enumerate(enabled):
        output_name = _require_nonempty_str(value, "outputs.enabled", str(idx))
        if output_name not in _KNOWN_OUTPUTS:
            raise ConfigError(
                "outputs.enabled", str(idx), value, f"one of {sorted(_KNOWN_OUTPUTS)}"
            )
        if output_name in seen_outputs:
            raise ConfigError(
                "outputs", "enabled", enabled, "unique known output names"
            )
        seen_outputs.add(output_name)

    udp_v3 = _require_mapping(
        outputs.get("udp_v3"), "outputs.udp_v3", "udp_v3"
    )
    udp_presentation = _require_mapping(
        udp_v3.get("presentation"),
        "outputs.udp_v3.presentation",
        "presentation",
    )
    udp_presentation_mode = _validate_choice(
        udp_presentation.get("mode"),
        "outputs.udp_v3.presentation",
        "mode",
        ["immediate", "scheduled"],
    )
    if udp_presentation_mode == "scheduled":
        lead_us = _require_int(
            udp_presentation.get("lead_us"),
            "outputs.udp_v3.presentation",
            "lead_us",
            1,
        )
        if lead_us > 100_000:
            raise ConfigError(
                "outputs.udp_v3.presentation",
                "lead_us",
                lead_us,
                "integer in [1, 100000]",
            )
        session_start_repeats = _require_int(
            udp_presentation.get("session_start_repeats"),
            "outputs.udp_v3.presentation",
            "session_start_repeats",
            2,
        )
        if session_start_repeats > 10:
            raise ConfigError(
                "outputs.udp_v3.presentation",
                "session_start_repeats",
                session_start_repeats,
                "integer in [2, 10]",
            )
        session_start_spacing_us = _require_int(
            udp_presentation.get("session_start_spacing_us"),
            "outputs.udp_v3.presentation",
            "session_start_spacing_us",
            0,
        )
        if session_start_spacing_us > 10_000:
            raise ConfigError(
                "outputs.udp_v3.presentation",
                "session_start_spacing_us",
                session_start_spacing_us,
                "integer in [0, 10000]",
            )
        beacon = _require_mapping(
            udp_presentation.get("beacon"),
            "outputs.udp_v3.presentation.beacon",
            "beacon",
        )
        _require_ipv4_or_hostname(
            beacon.get("host"), "outputs.udp_v3.presentation.beacon", "host"
        )
        beacon_port = _require_int(
            beacon.get("port"),
            "outputs.udp_v3.presentation.beacon",
            "port",
            1,
        )
        if beacon_port > 65535:
            raise ConfigError(
                "outputs.udp_v3.presentation.beacon",
                "port",
                beacon_port,
                "integer in [1, 65535]",
            )
        beacon_interval_us = _require_int(
            beacon.get("interval_us"),
            "outputs.udp_v3.presentation.beacon",
            "interval_us",
            1,
        )
        if beacon_interval_us > 1_000_000:
            raise ConfigError(
                "outputs.udp_v3.presentation.beacon",
                "interval_us",
                beacon_interval_us,
                "integer in [1, 1000000]",
            )
        startup_count = _require_int(
            beacon.get("startup_count"),
            "outputs.udp_v3.presentation.beacon",
            "startup_count",
            3,
        )
        if startup_count > 32:
            raise ConfigError(
                "outputs.udp_v3.presentation.beacon",
                "startup_count",
                startup_count,
                "integer in [3, 32]",
            )
        startup_spacing_us = _require_int(
            beacon.get("startup_spacing_us"),
            "outputs.udp_v3.presentation.beacon",
            "startup_spacing_us",
            1,
        )
        if startup_spacing_us > 100_000:
            raise ConfigError(
                "outputs.udp_v3.presentation.beacon",
                "startup_spacing_us",
                startup_spacing_us,
                "integer in [1, 100000]",
            )
    transform = _require_mapping(
        outputs.get("transform"), "outputs.transform", "transform"
    )
    _require_finite_number(
        transform.get("power_limit"),
        "outputs.transform",
        "power_limit",
        minimum=0.0,
    )
    warm_bias = _require_mapping(
        transform.get("per_zone_warm_bias"),
        "outputs.transform",
        "per_zone_warm_bias",
    )
    cool_bias = _require_mapping(
        transform.get("per_zone_cool_bias"),
        "outputs.transform",
        "per_zone_cool_bias",
    )

    zones = _require_list(layout.get("zones"), "layout", "zones")
    strips = _require_list(layout.get("strips"), "layout", "strips")
    analog_nodes = _require_list(
        layout.get("analog_nodes"), "layout", "analog_nodes"
    )
    digital_nodes = _require_list(
        layout.get("digital_nodes"), "layout", "digital_nodes"
    )
    digital_segments = _require_list(
        layout.get("digital_segments"), "layout", "digital_segments"
    )
    digital_outputs = _require_list(
        layout.get("digital_outputs", []), "layout", "digital_outputs"
    )
    virtual_paths = _require_list(
        layout.get("virtual_paths", []), "layout", "virtual_paths"
    )

    zone_ids: set[str] = set()
    for idx, item in enumerate(zones):
        path = f"layout.zones[{idx}]"
        zone = _require_mapping(item, path, "item")
        zone_id = _require_nonempty_str(zone.get("id"), path, "id")
        if zone_id in zone_ids:
            raise ConfigError(path, "id", zone_id, "unique zone id")
        zone_ids.add(zone_id)

    for field, biases in (
        ("per_zone_warm_bias", warm_bias),
        ("per_zone_cool_bias", cool_bias),
    ):
        for zone_id, bias in biases.items():
            _require_nonempty_str(zone_id, "outputs.transform", field)
            if zone_id not in zone_ids:
                raise ConfigError(
                    "outputs.transform",
                    field,
                    zone_id,
                    "existing layout.zones id",
                )
            _require_finite_number(
                bias,
                f"outputs.transform.{field}",
                zone_id,
                minimum=0.0,
            )

    strip_lengths: dict[str, int] = {}
    for idx, item in enumerate(strips):
        path = f"layout.strips[{idx}]"
        strip = _require_mapping(item, path, "item")
        strip_id = _require_nonempty_str(strip.get("id"), path, "id")
        if strip_id in strip_lengths:
            raise ConfigError(path, "id", strip_id, "unique strip id")
        strip_lengths[strip_id] = _require_int(
            strip.get("pixel_count"), path, "pixel_count", 1
        )

    topology_version = layout.get("topology_version", 2)
    if topology_version not in {2, 3}:
        raise ConfigError("layout", "topology_version", topology_version, "2 or 3")
    digital_output_policy: Optional[str] = None
    if "digital_output_policy" in layout:
        digital_output_policy = _validate_choice(
            layout.get("digital_output_policy"),
            "layout",
            "digital_output_policy",
            ["multi_output_diagnostic", "one_output_gpio4"],
        )
        if topology_version != 3:
            raise ConfigError(
                "layout",
                "digital_output_policy",
                digital_output_policy,
                "only with topology_version 3",
            )
    if topology_version == 3 and output_mode == "production":
        if digital_output_policy is None:
            raise ConfigError(
                "layout",
                "digital_output_policy",
                None,
                "explicit topology v3 production policy",
            )
        if "udp_v3" not in seen_outputs:
            raise ConfigError(
                "outputs",
                "enabled",
                enabled,
                "udp_v3 enabled for topology v3 production",
            )
        if (
            digital_output_policy == "one_output_gpio4"
            and udp_presentation_mode != "scheduled"
        ):
            raise ConfigError(
                "outputs.udp_v3.presentation",
                "mode",
                udp_presentation_mode,
                "scheduled for one_output_gpio4 production",
            )
    expected_analog_nodes = 1 if topology_version == 3 else 6
    if len(analog_nodes) != expected_analog_nodes:
        raise ConfigError(
            "layout", "analog_nodes", len(analog_nodes), f"exactly {expected_analog_nodes}"
        )

    used_node_ids: dict[int, str] = {}
    for idx, item in enumerate(analog_nodes):
        path = f"layout.analog_nodes[{idx}]"
        node = _require_mapping(item, path, "item")
        node_id = _require_int(node.get("node_id"), path, "node_id", 1)
        if node_id in used_node_ids:
            raise ConfigError(path, "node_id", node_id, "globally unique node id")
        used_node_ids[node_id] = path
        zone_id = _require_nonempty_str(node.get("zone_id"), path, "zone_id")
        if zone_id not in zone_ids:
            raise ConfigError(path, "zone_id", zone_id, "existing layout.zones id")
        _require_int(node.get("fade_ms"), path, "fade_ms", 0)
        _require_nonempty_str(node.get("channel_order"), path, "channel_order")

    digital_node_lengths: dict[int, int] = {}
    digital_node_versions: dict[int, int] = {}
    digital_node_payload_limits: dict[int, int] = {}
    digital_node_endpoints: dict[tuple[str, int], str] = {}
    for idx, item in enumerate(digital_nodes):
        path = f"layout.digital_nodes[{idx}]"
        node = _require_mapping(item, path, "item")
        node_id = _require_int(node.get("node_id"), path, "node_id", 1)
        if node_id in used_node_ids:
            raise ConfigError(path, "node_id", node_id, "globally unique node id")
        used_node_ids[node_id] = path
        host = _require_ipv4_or_hostname(node.get("host"), path, "host")
        port = _require_int(node.get("port"), path, "port", 1)
        if port > 65535:
            raise ConfigError(path, "port", port, "integer in [1, 65535]")
        endpoint = (host, port)
        if endpoint in digital_node_endpoints:
            raise ConfigError(
                path,
                "endpoint",
                endpoint,
                "unique digital node UDP (host, port) endpoint",
            )
        digital_node_endpoints[endpoint] = path
        pixel_count = _require_int(node.get("pixel_count"), path, "pixel_count", 1)
        protocol_version = node.get("protocol_version", 2)
        if protocol_version not in {2, 3}:
            raise ConfigError(path, "protocol_version", protocol_version, "2 or 3")
        max_udp_payload = _require_int(
            node.get("max_udp_payload"), path, "max_udp_payload", 1
        )
        if protocol_version == 2 and pixel_count * 3 > max_udp_payload:
            raise ConfigError(
                path,
                "max_udp_payload",
                max_udp_payload,
                f">= physical payload size {pixel_count * 3}",
            )
        digital_node_lengths[node_id] = pixel_count
        digital_node_versions[node_id] = protocol_version
        digital_node_payload_limits[node_id] = max_udp_payload

    occupied: dict[int, set[int]] = {
        node_id: set() for node_id in digital_node_lengths
    }
    segment_ids: set[str] = set()
    for idx, item in enumerate(digital_segments):
        path = f"layout.digital_segments[{idx}]"
        segment = _require_mapping(item, path, "item")
        segment_id = _require_nonempty_str(segment.get("segment_id"), path, "segment_id")
        if segment_id in segment_ids:
            raise ConfigError(path, "segment_id", segment_id, "unique segment id")
        segment_ids.add(segment_id)
        strip_id = _require_nonempty_str(segment.get("strip_id"), path, "strip_id")
        if strip_id not in strip_lengths:
            raise ConfigError(path, "strip_id", strip_id, "existing layout.strips id")
        node_id = _require_int(segment.get("node_id"), path, "node_id", 1)
        if node_id not in digital_node_lengths:
            raise ConfigError(
                path, "node_id", node_id, "existing layout.digital_nodes node_id"
            )
        offset = _require_int(segment.get("offset"), path, "offset", 0)
        pixel_count = _require_int(segment.get("pixel_count"), path, "pixel_count", 1)
        _validate_choice(
            segment.get("direction"),
            path,
            "direction",
            ["forward", "reverse"],
        )
        if pixel_count > strip_lengths[strip_id]:
            raise ConfigError(
                path,
                "pixel_count",
                pixel_count,
                f"<= logical strip {strip_id!r} length {strip_lengths[strip_id]}",
            )
        end = offset + pixel_count
        if end > digital_node_lengths[node_id]:
            raise ConfigError(
                path,
                "offset",
                offset,
                f"range end <= digital node {node_id} length {digital_node_lengths[node_id]}",
            )
        for pixel in range(offset, end):
            if pixel in occupied[node_id]:
                raise ConfigError(
                    path,
                    "offset",
                    offset,
                    f"non-overlapping segment pixels on node {node_id}",
                )
            occupied[node_id].add(pixel)

    if topology_version == 3:
        if any(version != 3 for version in digital_node_versions.values()):
            raise ConfigError("layout.digital_nodes", "protocol_version", 2, "UDP v3 for every cabin digital node")
        if digital_segments:
            raise ConfigError("layout", "digital_segments", digital_segments, "empty for UDP v3 topology")
        if not digital_outputs:
            raise ConfigError("layout", "digital_outputs", digital_outputs, "non-empty complete output mapping")
        seen_strips: set[str] = set()
        by_node: dict[int, list[dict[str, Any]]] = {}
        for idx, item in enumerate(digital_outputs):
            path = f"layout.digital_outputs[{idx}]"
            output = _require_mapping(item, path, "item")
            node_id = _require_int(output.get("node_id"), path, "node_id", 1)
            output_id = _require_int(output.get("output_id"), path, "output_id", 1)
            gpio = _require_int(output.get("gpio"), path, "gpio", 0)
            if digital_output_policy == "one_output_gpio4" and output_id != 1:
                raise ConfigError(
                    path,
                    "output_id",
                    output_id,
                    "1 under layout.digital_output_policy 'one_output_gpio4'",
                )
            if digital_output_policy == "one_output_gpio4" and gpio != 4:
                raise ConfigError(
                    path,
                    "gpio",
                    gpio,
                    "4 under layout.digital_output_policy 'one_output_gpio4'",
                )
            strip_id = _require_nonempty_str(output.get("strip_id"), path, "strip_id")
            pixel_count = _require_int(output.get("pixel_count"), path, "pixel_count", 1)
            _validate_choice(output.get("direction", "forward"), path, "direction", ["forward", "reverse"])
            if node_id not in digital_node_lengths:
                raise ConfigError(path, "node_id", node_id, "existing layout.digital_nodes node_id")
            if digital_node_versions[node_id] != 3:
                raise ConfigError(path, "node_id", node_id, "UDP v3 digital node")
            if strip_id not in strip_lengths:
                raise ConfigError(path, "strip_id", strip_id, "existing layout.strips id")
            if pixel_count != strip_lengths[strip_id]:
                raise ConfigError(path, "pixel_count", pixel_count, f"exact logical strip {strip_id!r} length {strip_lengths[strip_id]}")
            if pixel_count > 100:
                raise ConfigError(path, "pixel_count", pixel_count, "<= 100 per physical output")
            if strip_id in seen_strips:
                raise ConfigError(path, "strip_id", strip_id, "unique complete strip mapping")
            seen_strips.add(strip_id)
            by_node.setdefault(node_id, []).append({"output_id": output_id, "gpio": gpio, "pixel_count": pixel_count})
        if digital_output_policy == "one_output_gpio4":
            for node_id in digital_node_lengths:
                if len(by_node.get(node_id, ())) != 1:
                    raise ConfigError(
                        "layout.digital_outputs",
                        "node_id",
                        node_id,
                        "exactly one output per digital node under "
                        "layout.digital_output_policy 'one_output_gpio4'",
                    )
        if seen_strips != set(strip_lengths):
            raise ConfigError("layout", "digital_outputs", sorted(set(strip_lengths) - seen_strips), "every logical strip mapped exactly once")
        for node_id, outputs_for_node in by_node.items():
            if len(outputs_for_node) > 3:
                raise ConfigError("layout.digital_outputs", "node_id", node_id, "at most 3 independent outputs")
            output_ids = [item["output_id"] for item in outputs_for_node]
            gpios = [item["gpio"] for item in outputs_for_node]
            if len(output_ids) != len(set(output_ids)):
                raise ConfigError("layout.digital_outputs", "output_id", node_id, "unique within node")
            if len(gpios) != len(set(gpios)):
                raise ConfigError("layout.digital_outputs", "gpio", node_id, "unique within node")
            mapped_pixel_count = sum(item["pixel_count"] for item in outputs_for_node)
            if mapped_pixel_count != digital_node_lengths[node_id]:
                raise ConfigError(
                    "layout.digital_outputs",
                    "node_id",
                    node_id,
                    f"output pixel total {mapped_pixel_count} matching digital node pixel_count",
                )
            encoded_size = 29 + sum(6 + item["pixel_count"] * 3 for item in outputs_for_node) + 4
            if encoded_size > digital_node_payload_limits[node_id]:
                raise ConfigError("layout.digital_outputs", "node_id", node_id, "one complete UDP v3 datagram within max_udp_payload")
        for node_id, protocol_version in digital_node_versions.items():
            if protocol_version == 3 and node_id not in by_node:
                raise ConfigError("layout.digital_outputs", "node_id", node_id, "at least one output for each UDP v3 node")

    virtual_path_ids: set[str] = set()
    for path_idx, item in enumerate(virtual_paths):
        path = f"layout.virtual_paths[{path_idx}]"
        virtual_path = _require_mapping(item, path, "item")
        path_id = _require_nonempty_str(virtual_path.get("id"), path, "id")
        if path_id in virtual_path_ids:
            raise ConfigError(path, "id", path_id, "unique virtual path id")
        virtual_path_ids.add(path_id)
        segments = _require_list(virtual_path.get("segments"), path, "segments")
        if not segments:
            raise ConfigError(path, "segments", segments, "non-empty list")
        occupied_sources: dict[str, set[int]] = {}
        for segment_idx, item in enumerate(segments):
            segment_path = f"{path}.segments[{segment_idx}]"
            segment = _require_mapping(item, segment_path, "item")
            strip_id = _require_nonempty_str(
                segment.get("strip_id"), segment_path, "strip_id"
            )
            if strip_id not in strip_lengths:
                raise ConfigError(
                    segment_path, "strip_id", strip_id, "existing layout.strips id"
                )
            source_start = _require_int(
                segment.get("source_start", 0),
                segment_path,
                "source_start",
                0,
            )
            pixel_count = _require_int(
                segment.get("pixel_count"), segment_path, "pixel_count", 1
            )
            _validate_choice(
                segment.get("direction"),
                segment_path,
                "direction",
                ["forward", "reverse"],
            )
            _require_int(
                segment.get("gap_after_pixels", 0),
                segment_path,
                "gap_after_pixels",
                0,
            )
            source_end = source_start + pixel_count
            if source_end > strip_lengths[strip_id]:
                raise ConfigError(
                    segment_path,
                    "pixel_count",
                    pixel_count,
                    f"source range [{source_start}, {source_end}) within "
                    f"logical strip {strip_id!r} length {strip_lengths[strip_id]}",
                )
            occupied = occupied_sources.setdefault(strip_id, set())
            for source_pixel in range(source_start, source_end):
                if source_pixel in occupied:
                    raise ConfigError(
                        segment_path,
                        "source_start",
                        source_start,
                        "non-overlapping source pixels within virtual path",
                    )
                occupied.add(source_pixel)


class Config:
    """Application configuration loaded from YAML files.

    Loads system.yaml, layout.yaml, effects.yaml, outputs.yaml.
    Supports optional overrides via environment variable LIGHT_ENGINE_CONFIG_DIR.
    """

    _instance: Optional["Config"] = None

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(
                os.environ.get("LIGHT_ENGINE_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))
            )
        self.profile_path: Optional[Path] = None
        self.config_dir = Path(config_dir)
        if self.config_dir.is_file():
            self.profile_path = self.config_dir
            self.config_dir = self.profile_path.parent.parent
        self._data: dict[str, Any] = {}
        self._load_all()
        validate_config(self._data)

    def _load_all(self) -> None:
        """Load all default config files and merge."""
        files = ["system.yaml", "layout.yaml", "effects.yaml", "outputs.yaml"]
        for fname in files:
            fpath = self.config_dir / fname
            if fpath.exists():
                loaded = load_yaml(fpath)
                self._data = _deep_merge(self._data, loaded)
        if self.profile_path is not None:
            loaded = load_yaml(self.profile_path)
            self._data = _deep_merge(self._data, loaded)

    @classmethod
    def get_instance(cls, config_dir: Optional[Path] = None) -> "Config":
        """Get or create singleton config instance."""
        if cls._instance is None or config_dir is not None:
            cls._instance = cls(config_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dotted key path."""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_or_raise(self, key: str) -> Any:
        """Get a config value, raising if missing."""
        value = self.get(key, _SENTINEL)
        if value is _SENTINEL:
            raise KeyError(f"Required config key not found: {key}")
        return value

    def to_dict(self) -> dict:
        """Return full config as dict."""
        return self._data.copy()


_SENTINEL = object()
