"""Tests for JSON physical-frame output."""

from __future__ import annotations

import json

from light_engine.mapping.physical import (
    AnalogNodeCommand,
    DigitalNodeFrame,
    PhysicalFrame,
)
from light_engine.models import RGBCCTColor
from light_engine.outputs.json_output import JsonOutput


def test_json_output_serializes_physical_node_grouping(tmp_path) -> None:
    output_path = tmp_path / "frames.jsonl"
    output = JsonOutput(str(output_path))
    frame = PhysicalFrame(
        sequence=12,
        timestamp=3.5,
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="127.0.0.1",
                port=9001,
                pixels=[(0.1, 0.2, 0.3), (1.0, 0.0, 0.5)],
            )
        ],
        analog_commands=[
            AnalogNodeCommand(
                node_id=1,
                zone_id="ceiling_left",
                color=RGBCCTColor(
                    r=0.25,
                    g=0.5,
                    b=0.75,
                    warm_white=0.1,
                    cool_white=0.2,
                ),
            )
        ],
        metadata={"logical_regions": {"ceiling_left": "top"}},
    )

    output.open()
    output.send_frame(frame)
    output.close()

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["sequence"] == 12
    assert data["digital_nodes"][0]["node_id"] == 7
    assert data["digital_nodes"][0]["pixel_count"] == 2
    assert data["digital_nodes"][0]["pixels"] == [[26, 51, 76], [255, 0, 128]]
    assert data["analog_nodes"][0]["node_id"] == 1
    assert data["analog_nodes"][0]["zone_id"] == "ceiling_left"
    assert data["analog_nodes"][0]["warm_white"] == 26
    assert data["analog_nodes"][0]["cool_white"] == 51
    assert data["metadata"]["logical_regions"]["ceiling_left"] == "top"
