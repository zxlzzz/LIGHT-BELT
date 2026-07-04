"""Mapping: abstract lighting zones to physical strips."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

from light_engine.config import Config
from light_engine.mapping.resolve import (
    validate_video_zone,
    validate_direction,
    VALID_VIDEO_ZONES,
)

logger = logging.getLogger(__name__)


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
    video_zone_map: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Optional[Config] = None) -> "Layout":
        """Create Layout from configuration."""
        if config is None:
            config = Config.get_instance()
        layout = cls()

        # Load digital strips
        strips_data = config.get("layout.strips", [])
        for s in strips_data:
            vz = s.get("video_zone", "center")
            if vz not in VALID_VIDEO_ZONES:
                raise ValueError(
                    f"Strip '{s.get('id','?')}': invalid video_zone '{vz}'."
                    f" Must be one of {sorted(VALID_VIDEO_ZONES)}."
                )
            layout.strips.append(ZoneDef(
                id=s.get("id", ""),
                label=s.get("label", s.get("id", "")),
                zone_type=s.get("type", "digital"),
                pixel_count=s.get("pixel_count", 0),
                direction=s.get("direction", "forward"),
                video_zone=vz,
            ))
            logger.debug(
                "Digital strip '%s': video_zone='%s', direction='%s'",
                s.get("id", "?"), vz, s.get("direction", "forward"),
            )

        # Load RGB+CCT zones
        zones_data = config.get("layout.zones", [])
        for z in zones_data:
            vz = z.get("video_zone", "center")
            if vz not in VALID_VIDEO_ZONES:
                raise ValueError(
                    f"Zone '{z.get('id','?')}': invalid video_zone '{vz}'."
                    f" Must be one of {sorted(VALID_VIDEO_ZONES)}."
                )
            layout.zones.append(ZoneDef(
                id=z.get("id", ""),
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

        return layout

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
