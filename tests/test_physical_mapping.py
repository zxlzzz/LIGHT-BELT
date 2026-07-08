"""Tests for Phase 3 physical mapping from logical frames to node frames."""

from __future__ import annotations

import pytest

from light_engine.config import Config, ConfigError
from light_engine.mapping import Layout, ZoneDef
from light_engine.mapping.physical import (
    AnalogNodeMapping,
    DigitalNodeMapping,
    DigitalSegmentMapping,
    PhysicalMapping,
)
from light_engine.models import DigitalStrip, PixelFrame, RGBCCTColor, ZoneOutput


def _six_analog_nodes() -> list[AnalogNodeMapping]:
    return [
        AnalogNodeMapping(node_id=idx, zone_id=f"zone_{idx}")
        for idx in range(1, 7)
    ]


def _layout(
    digital_nodes: list[DigitalNodeMapping],
    digital_segments: list[DigitalSegmentMapping],
) -> Layout:
    return Layout(
        zones=[ZoneDef(id=f"zone_{idx}") for idx in range(1, 7)],
        strips=[
            ZoneDef(id="strip_a", pixel_count=2),
            ZoneDef(id="strip_b", pixel_count=2, direction="reverse"),
        ],
        analog_nodes=_six_analog_nodes(),
        digital_nodes=digital_nodes,
        digital_segments=digital_segments,
    )


def _base_config_data() -> dict:
    return {
        "layout": {
            "zones": [
                {
                    "id": f"zone_{idx}",
                    "type": "rgbcct",
                    "video_zone": "center",
                    "direction": "forward",
                }
                for idx in range(1, 7)
            ],
            "analog_nodes": [
                {
                    "node_id": idx,
                    "zone_id": f"zone_{idx}",
                    "video_zone": "center",
                    "channel_order": "RGBWC",
                    "fade_ms": 0,
                }
                for idx in range(1, 7)
            ],
            "strips": [
                {
                    "id": "strip_a",
                    "type": "digital",
                    "pixel_count": 2,
                    "video_zone": "center",
                    "direction": "forward",
                }
            ],
            "digital_nodes": [
                {
                    "node_id": 7,
                    "host": "10.0.0.10",
                    "port": 9001,
                    "pixel_count": 2,
                    "max_udp_payload": 6,
                }
            ],
            "digital_segments": [
                {
                    "segment_id": "segment_a",
                    "strip_id": "strip_a",
                    "node_id": 7,
                    "offset": 0,
                    "pixel_count": 2,
                    "direction": "forward",
                    "video_zone": "center",
                }
            ],
            "video_zone_map": {},
        }
    }


def _layout_from_data(data: dict) -> Layout:
    Config.reset()
    config = Config()
    config._data = data
    return Layout.from_config(config)


def test_default_config_maps_six_analog_nodes_and_one_digital_node() -> None:
    Config.reset()
    layout = Layout.from_config(Config())
    mapping = PhysicalMapping(layout)
    frame = PixelFrame(
        timestamp=1.25,
        sequence=42,
        zones=[
            ZoneOutput(zone.id, RGBCCTColor(r=0.1, g=0.2, b=0.3))
            for zone in layout.zones
        ],
        strips=[
            DigitalStrip(
                strip_id=strip.id,
                pixel_count=strip.pixel_count,
                pixels=[(0.1, 0.2, 0.3)] * strip.pixel_count,
            )
            for strip in layout.strips
        ],
    )

    physical = mapping.map(frame)

    assert physical.sequence == 42
    assert physical.timestamp == 1.25
    assert len(physical.analog_commands) == 6
    assert [command.node_id for command in physical.analog_commands] == [1, 2, 3, 4, 5, 6]
    assert len(physical.digital_frames) == 1
    assert len(physical.digital_frames[0].pixels) == 632
    assert layout.get_virtual_path_ids() == ["screen_to_wall"]
    assert layout.get_virtual_path("screen_to_wall").total_length == 172


def test_physical_mapping_places_forward_and_reverse_segments() -> None:
    layout = _layout(
        digital_nodes=[
            DigitalNodeMapping(
                node_id=7,
                host="10.0.0.10",
                port=9001,
                pixel_count=4,
                max_udp_payload=12,
            )
        ],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            ),
            DigitalSegmentMapping(
                segment_id="strip_b_main",
                strip_id="strip_b",
                node_id=7,
                offset=2,
                pixel_count=2,
                direction="reverse",
            ),
        ],
    )
    frame = PixelFrame(
        timestamp=0.0,
        sequence=7,
        strips=[
            DigitalStrip(
                strip_id="strip_a",
                pixel_count=2,
                pixels=[(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            ),
            DigitalStrip(
                strip_id="strip_b",
                pixel_count=2,
                pixels=[(0.0, 0.0, 1.0), (0.5, 0.5, 0.5)],
            ),
        ],
    )

    physical = PhysicalMapping(layout).map(frame)

    assert physical.digital_frames[0].pixels == [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.5, 0.5, 0.5),
        (0.0, 0.0, 1.0),
    ]


def test_physical_mapping_splits_segments_across_multiple_nodes() -> None:
    layout = _layout(
        digital_nodes=[
            DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=2),
            DigitalNodeMapping(node_id=8, host="10.0.0.11", port=9002, pixel_count=2),
        ],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            ),
            DigitalSegmentMapping(
                segment_id="strip_b_main",
                strip_id="strip_b",
                node_id=8,
                offset=0,
                pixel_count=2,
            ),
        ],
    )
    frame = PixelFrame(
        timestamp=0.0,
        sequence=9,
        strips=[
            DigitalStrip("strip_a", 2, [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]),
            DigitalStrip("strip_b", 2, [(0.0, 0.0, 1.0), (1.0, 1.0, 1.0)]),
        ],
    )

    physical = PhysicalMapping(layout).map(frame)

    assert [node.node_id for node in physical.digital_frames] == [7, 8]
    assert physical.digital_frames[0].pixels == [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    assert physical.digital_frames[1].pixels == [(0.0, 0.0, 1.0), (1.0, 1.0, 1.0)]


def test_missing_logical_inputs_map_to_black_physical_outputs() -> None:
    layout = _layout(
        digital_nodes=[DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=4)],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            ),
            DigitalSegmentMapping(
                segment_id="strip_b_main",
                strip_id="strip_b",
                node_id=7,
                offset=2,
                pixel_count=2,
            ),
        ],
    )

    physical = PhysicalMapping(layout).map(PixelFrame(timestamp=0.0, sequence=3))

    assert all(command.color == RGBCCTColor() for command in physical.analog_commands)
    assert physical.digital_frames[0].pixels == [(0.0, 0.0, 0.0)] * 4


def test_physical_mapping_rejects_duplicate_node_ids() -> None:
    layout = _layout(
        digital_nodes=[
            DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=2),
            DigitalNodeMapping(node_id=7, host="10.0.0.11", port=9002, pixel_count=2),
        ],
        digital_segments=[],
    )

    with pytest.raises(ValueError, match="node_id"):
        PhysicalMapping(layout)


def test_physical_mapping_rejects_overlapping_segments() -> None:
    layout = _layout(
        digital_nodes=[DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=4)],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            ),
            DigitalSegmentMapping(
                segment_id="strip_b_main",
                strip_id="strip_b",
                node_id=7,
                offset=1,
                pixel_count=2,
            ),
        ],
    )

    with pytest.raises(ValueError, match="overlaps"):
        PhysicalMapping(layout)


def test_physical_mapping_rejects_segments_outside_node_bounds() -> None:
    layout = _layout(
        digital_nodes=[DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=3)],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=2,
                pixel_count=2,
            ),
        ],
    )

    with pytest.raises(ValueError, match=r"physical range \[2, 4\)"):
        PhysicalMapping(layout)


def test_physical_mapping_rejects_udp_payload_over_limit() -> None:
    layout = _layout(
        digital_nodes=[
            DigitalNodeMapping(
                node_id=7,
                host="10.0.0.10",
                port=9001,
                pixel_count=4,
                max_udp_payload=11,
            )
        ],
        digital_segments=[],
    )

    with pytest.raises(ValueError, match="payload"):
        PhysicalMapping(layout)


def test_analog_mapping_rejects_unknown_zone_reference() -> None:
    data = _base_config_data()
    data["layout"]["analog_nodes"][0]["zone_id"] = "missing_zone"

    with pytest.raises(ValueError, match="zone_id.*missing_zone"):
        _layout_from_data(data)


def test_digital_segment_rejects_unknown_strip_reference() -> None:
    data = _base_config_data()
    data["layout"]["digital_segments"][0]["strip_id"] = "missing_strip"

    with pytest.raises(ValueError, match="strip_id.*missing_strip"):
        _layout_from_data(data)


def test_digital_segment_rejects_source_range_beyond_logical_strip() -> None:
    data = _base_config_data()
    data["layout"]["digital_segments"][0]["pixel_count"] = 3
    data["layout"]["digital_nodes"][0]["pixel_count"] = 3
    data["layout"]["digital_nodes"][0]["max_udp_payload"] = 9

    with pytest.raises(ValueError, match=r"source range \[0, 3\)"):
        _layout_from_data(data)


def test_digital_segment_rejects_unknown_direction() -> None:
    data = _base_config_data()
    data["layout"]["digital_segments"][0]["direction"] = "sideways"

    with pytest.raises(ValueError, match="direction.*sideways"):
        _layout_from_data(data)


@pytest.mark.parametrize("section", ["analog_nodes", "digital_nodes"])
def test_mapping_rejects_bool_node_id(section: str) -> None:
    data = _base_config_data()
    data["layout"][section][0]["node_id"] = True

    with pytest.raises(ConfigError, match="node_id"):
        _layout_from_data(data)


def test_mapping_rejects_bool_pixel_count() -> None:
    data = _base_config_data()
    data["layout"]["digital_segments"][0]["pixel_count"] = True

    with pytest.raises(ConfigError, match="pixel_count"):
        _layout_from_data(data)


@pytest.mark.parametrize("value", [0, -1])
def test_mapping_rejects_non_positive_node_id(value: int) -> None:
    data = _base_config_data()
    data["layout"]["digital_nodes"][0]["node_id"] = value
    data["layout"]["digital_segments"][0]["node_id"] = value

    with pytest.raises(ConfigError, match="node_id"):
        _layout_from_data(data)


@pytest.mark.parametrize("value", [0, -1])
def test_mapping_rejects_non_positive_segment_pixel_count(value: int) -> None:
    data = _base_config_data()
    data["layout"]["digital_segments"][0]["pixel_count"] = value

    with pytest.raises(ConfigError, match="pixel_count"):
        _layout_from_data(data)


def test_mapping_rejects_cross_type_duplicate_node_id() -> None:
    data = _base_config_data()
    data["layout"]["digital_nodes"][0]["node_id"] = 1
    data["layout"]["digital_segments"][0]["node_id"] = 1

    with pytest.raises(ValueError, match="globally unique node id"):
        _layout_from_data(data)


def test_mapping_rejects_duplicate_segment_id() -> None:
    data = _base_config_data()
    data["layout"]["digital_nodes"][0]["pixel_count"] = 4
    data["layout"]["digital_nodes"][0]["max_udp_payload"] = 12
    data["layout"]["digital_segments"].append(
        {
            "segment_id": "segment_a",
            "strip_id": "strip_a",
            "node_id": 7,
            "offset": 2,
            "pixel_count": 2,
            "direction": "forward",
            "video_zone": "center",
        }
    )

    with pytest.raises(ValueError, match="segment_id.*segment_a"):
        _layout_from_data(data)


def test_mapping_rejects_empty_segment_id() -> None:
    data = _base_config_data()
    data["layout"]["digital_segments"][0]["segment_id"] = ""

    with pytest.raises(ConfigError, match="segment_id"):
        _layout_from_data(data)


def test_analog_commands_copy_colors_for_shared_zone_references() -> None:
    layout = _layout(
        digital_nodes=[DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=2)],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            )
        ],
    )
    layout.analog_nodes[1] = AnalogNodeMapping(node_id=2, zone_id="zone_1")
    logical_color = RGBCCTColor(
        r=0.1, g=0.2, b=0.3, warm_white=0.4, cool_white=0.5
    )
    frame = PixelFrame(
        timestamp=0.0,
        sequence=1,
        zones=[ZoneOutput("zone_1", logical_color)],
    )

    physical = PhysicalMapping(layout).map(frame)
    first = physical.analog_commands[0].color
    second = physical.analog_commands[1].color

    assert first == logical_color
    assert second == logical_color
    assert first is not logical_color
    assert second is not logical_color
    assert first is not second


def test_missing_runtime_zone_maps_to_black_without_config_error() -> None:
    layout = _layout(
        digital_nodes=[DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=2)],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            )
        ],
    )

    physical = PhysicalMapping(layout).map(PixelFrame(timestamp=0.0, sequence=1))

    assert physical.analog_commands[0].color == RGBCCTColor()


def test_missing_runtime_strip_maps_to_black_without_config_error() -> None:
    layout = _layout(
        digital_nodes=[DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=2)],
        digital_segments=[
            DigitalSegmentMapping(
                segment_id="strip_a_main",
                strip_id="strip_a",
                node_id=7,
                offset=0,
                pixel_count=2,
            )
        ],
    )

    physical = PhysicalMapping(layout).map(PixelFrame(timestamp=0.0, sequence=1))

    assert physical.digital_frames[0].pixels == [(0.0, 0.0, 0.0)] * 2
