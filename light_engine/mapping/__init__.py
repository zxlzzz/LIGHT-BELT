"""Mapping: abstract lighting zones to physical strips."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from light_engine.config import Config, ConfigError
from light_engine.mapping.physical import (
    AnalogNodeMapping,
    DigitalNodeMapping,
    DigitalOutputMapping,
    DigitalSegmentMapping,
    PhysicalMapping,
)
from light_engine.mapping.resolve import (
    validate_video_zone,
    validate_direction,
    VALID_VIDEO_ZONES,
)
from light_engine.mapping.virtual import VirtualPath, build_virtual_paths

logger = logging.getLogger(__name__)
_MISSING = object()


def _require_int(
    item: dict[str, Any],
    field_name: str,
    path: str,
    min_value: int,
) -> int:
    value = item.get(field_name, _MISSING)
    if type(value) is not int or value < min_value:
        raise ConfigError(path, field_name, value, f"integer >= {min_value}")
    return value


def _require_str(item: dict[str, Any], field_name: str, path: str) -> str:
    value = item.get(field_name, _MISSING)
    if not isinstance(value, str) or not value:
        raise ConfigError(path, field_name, value, "non-empty string")
    return value


def _optional_str(
    item: dict[str, Any],
    field_name: str,
    path: str,
    default: str,
) -> str:
    value = item.get(field_name, default)
    if not isinstance(value, str) or not value:
        raise ConfigError(path, field_name, value, "non-empty string")
    return value


def _optional_int(
    item: dict[str, Any], field_name: str, path: str, default: int, min_value: int
) -> int:
    value = item.get(field_name, default)
    if type(value) is not int or value < min_value:
        raise ConfigError(path, field_name, value, f"integer >= {min_value}")
    return value


@dataclass
class ZoneDef:
    """Definition of a lighting zone."""

    id: str
    label: str = ""
    zone_type: str = "digital"  # "digital" or "rgbcct"
    pixel_count: int = 0
    direction: str = "forward"  # "forward" or "reverse"
    video_zone: str = "center"

    def __post_init__(self) -> None:
        self.video_zone = validate_video_zone(self.video_zone, self.id)
        self.direction = validate_direction(self.direction, self.id)


@dataclass
class Layout:
    """Complete lighting layout with zones and strips."""

    zones: list[ZoneDef] = field(default_factory=list)
    strips: list[ZoneDef] = field(default_factory=list)
    analog_nodes: list[AnalogNodeMapping] = field(default_factory=list)
    digital_nodes: list[DigitalNodeMapping] = field(default_factory=list)
    digital_segments: list[DigitalSegmentMapping] = field(default_factory=list)
    digital_outputs: list[DigitalOutputMapping] = field(default_factory=list)
    topology_version: int = 2
    virtual_paths: tuple[VirtualPath, ...] = ()
    video_zone_map: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Optional[Config] = None) -> "Layout":
        """Create Layout from configuration."""
        if config is None:
            config = Config.get_instance()
        layout = cls()
        layout.topology_version = config.get("layout.topology_version", 2)

        # Load digital strips
        strips_data = config.get("layout.strips", [])
        for idx, s in enumerate(strips_data):
            path = f"layout.strips[{idx}]"
            vz = s.get("video_zone", "center")
            if vz not in VALID_VIDEO_ZONES:
                raise ValueError(
                    f"Strip '{s.get('id','?')}': invalid video_zone '{vz}'."
                    f" Must be one of {sorted(VALID_VIDEO_ZONES)}."
                )
            layout.strips.append(ZoneDef(
                id=_require_str(s, "id", path),
                label=s.get("label", s.get("id", "")),
                zone_type=s.get("type", "digital"),
                pixel_count=_require_int(s, "pixel_count", path, 1),
                direction=s.get("direction", "forward"),
                video_zone=vz,
            ))
            logger.debug(
                "Digital strip '%s': video_zone='%s', direction='%s'",
                s.get("id", "?"), vz, s.get("direction", "forward"),
            )

        # Load RGB+CCT zones
        zones_data = config.get("layout.zones", [])
        for idx, z in enumerate(zones_data):
            path = f"layout.zones[{idx}]"
            vz = z.get("video_zone", "center")
            if vz not in VALID_VIDEO_ZONES:
                raise ValueError(
                    f"Zone '{z.get('id','?')}': invalid video_zone '{vz}'."
                    f" Must be one of {sorted(VALID_VIDEO_ZONES)}."
                )
            layout.zones.append(ZoneDef(
                id=_require_str(z, "id", path),
                label=z.get("label", z.get("id", "")),
                zone_type=z.get("type", "rgbcct"),
                pixel_count=1,
                direction=z.get("direction", "forward"),
                video_zone=vz,
            ))
            logger.debug(
                "RGB+CCT zone '%s': video_zone='%s', direction='%s'",
                z.get("id", "?"), vz, z.get("direction", "forward"),
            )

        # Load video zone map
        layout.video_zone_map = config.get("layout.video_zone_map", {})
        layout._load_physical_mapping(config)
        layout._load_virtual_paths(config)
        PhysicalMapping(layout)

        return layout

    def _load_physical_mapping(self, config: Config) -> None:
        analog_data = config.get("layout.analog_nodes", [])
        if analog_data:
            for idx, item in enumerate(analog_data):
                path = f"layout.analog_nodes[{idx}]"
                self.analog_nodes.append(AnalogNodeMapping(
                    node_id=_require_int(item, "node_id", path, 1),
                    zone_id=_require_str(item, "zone_id", path),
                    video_zone=_optional_str(item, "video_zone", path, "center"),
                    channel_order=_optional_str(
                        item, "channel_order", path, "RGBWC"
                    ),
                    fade_ms=_require_int(item, "fade_ms", path, 0),
                ))
        elif self.topology_version != 3:
            for idx, zone in enumerate(self.zones, start=1):
                self.analog_nodes.append(AnalogNodeMapping(
                    node_id=idx,
                    zone_id=zone.id,
                    video_zone=zone.video_zone,
                ))

        digital_data = config.get("layout.digital_nodes", [])
        if digital_data:
            for idx, item in enumerate(digital_data):
                path = f"layout.digital_nodes[{idx}]"
                self.digital_nodes.append(DigitalNodeMapping(
                    node_id=_require_int(item, "node_id", path, 1),
                    host=_optional_str(item, "host", path, "127.0.0.1"),
                    port=_require_int(item, "port", path, 1),
                    pixel_count=_require_int(item, "pixel_count", path, 1),
                    max_udp_payload=_require_int(
                        item, "max_udp_payload", path, 1
                    ),
                    protocol_version=_optional_int(
                        item, "protocol_version", path, 2, 2
                    ),
                ))
        elif self.strips:
            port = config.get("outputs.udp.port", 9001)
            max_udp_payload = config.get("outputs.udp.max_packet_size", 4096)
            if type(port) is not int or port < 1:
                raise ConfigError("outputs.udp", "port", port, "integer >= 1")
            if type(max_udp_payload) is not int or max_udp_payload < 1:
                raise ConfigError(
                    "outputs.udp",
                    "max_packet_size",
                    max_udp_payload,
                    "integer >= 1",
                )
            self.digital_nodes.append(DigitalNodeMapping(
                node_id=max((node.node_id for node in self.analog_nodes), default=0) + 1,
                host=config.get("outputs.udp.host", "127.0.0.1"),
                port=port,
                pixel_count=sum(strip.pixel_count for strip in self.strips),
                max_udp_payload=max_udp_payload,
            ))

        segment_data = config.get("layout.digital_segments", [])
        if segment_data:
            for idx, item in enumerate(segment_data):
                path = f"layout.digital_segments[{idx}]"
                self.digital_segments.append(DigitalSegmentMapping(
                    segment_id=_require_str(item, "segment_id", path),
                    strip_id=_require_str(item, "strip_id", path),
                    node_id=_require_int(item, "node_id", path, 1),
                    offset=_require_int(item, "offset", path, 0),
                    pixel_count=_require_int(item, "pixel_count", path, 1),
                    direction=_optional_str(item, "direction", path, "forward"),
                    video_zone=_optional_str(item, "video_zone", path, "center"),
                ))
        elif self.topology_version != 3:
            offset = 0
            node_id = self.digital_nodes[0].node_id if self.digital_nodes else 1
            for strip in self.strips:
                self.digital_segments.append(DigitalSegmentMapping(
                    segment_id=strip.id,
                    strip_id=strip.id,
                    node_id=node_id,
                    offset=offset,
                    pixel_count=strip.pixel_count,
                    direction=strip.direction,
                    video_zone=strip.video_zone,
                ))
                offset += strip.pixel_count

        output_data = config.get("layout.digital_outputs", [])
        for idx, item in enumerate(output_data):
            path = f"layout.digital_outputs[{idx}]"
            self.digital_outputs.append(DigitalOutputMapping(
                node_id=_require_int(item, "node_id", path, 1),
                output_id=_require_int(item, "output_id", path, 1),
                gpio=_require_int(item, "gpio", path, 0),
                strip_id=_require_str(item, "strip_id", path),
                pixel_count=_require_int(item, "pixel_count", path, 1),
                direction=_optional_str(item, "direction", path, "forward"),
            ))

    def _load_virtual_paths(self, config: Config) -> None:
        virtual_paths_data = config.get("layout.virtual_paths", [])
        strip_lengths = {strip.id: strip.pixel_count for strip in self.strips}
        self.virtual_paths = build_virtual_paths(
            virtual_paths_data,
            strip_lengths,
            base_path="layout.virtual_paths",
        )

    def get_zone_ids(self) -> list[str]:
        """Get all RGB+CCT zone IDs."""
        return [z.id for z in self.zones]

    def get_strip_ids(self) -> list[str]:
        """Get all digital strip IDs."""
        return [s.id for s in self.strips]

    def get_strip(self, strip_id: str) -> Optional[ZoneDef]:
        """Get a digital strip by ID."""
        for s in self.strips:
            if s.id == strip_id:
                return s
        return None

    def get_virtual_path_ids(self) -> list[str]:
        """Get all virtual path IDs."""
        return [path.id for path in self.virtual_paths]

    def get_virtual_path(self, path_id: str) -> Optional[VirtualPath]:
        """Get a virtual path by ID."""
        for path in self.virtual_paths:
            if path.id == path_id:
                return path
        return None

    def get_zone(self, zone_id: str) -> Optional[ZoneDef]:
        """Get an RGB+CCT zone by ID."""
        for z in self.zones:
            if z.id == zone_id:
                return z
        return None

    def get_zones_for_video_region(self, region: str) -> list[str]:
        """Get zone/strip IDs mapped to a video region."""
        return self.video_zone_map.get(region, [])

    def total_digital_pixels(self) -> int:
        """Total pixel count across all digital strips."""
        return sum(s.pixel_count for s in self.strips)

    def total_zones(self) -> int:
        """Total number of RGB+CCT zones."""
        return len(self.zones)
