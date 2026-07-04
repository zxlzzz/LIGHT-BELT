"""Tests for minimal Phase 1 OutputTransform."""

import json

import pytest

from light_engine.models import DigitalStrip, PixelFrame, RGBCCTColor, ZoneOutput
from light_engine.outputs.json_output import JsonOutput
from light_engine.outputs.transform import OutputTransform


def test_global_brightness_applies_once_to_zone() -> None:
    transform = OutputTransform(global_brightness=0.5)
    color = RGBCCTColor(
        r=0.8, g=0.6, b=0.4, warm_white=0.2, cool_white=0.1
    )

    out = transform.apply_to_zone(color)

    assert out == RGBCCTColor(
        r=0.4, g=0.3, b=0.2, warm_white=0.1, cool_white=0.05
    )


def test_global_brightness_applies_once_to_digital_pixels() -> None:
    transform = OutputTransform(global_brightness=0.25)
    frame = PixelFrame(
        timestamp=1.0,
        strips=[
            DigitalStrip(
                strip_id="s1",
                pixel_count=1,
                pixels=[(0.8, 0.4, 0.2)],
            )
        ],
        zones=[
            ZoneOutput(
                zone_id="z1",
                color=RGBCCTColor(r=0.8, g=0.4, b=0.2),
            )
        ],
        metadata={"effect": "test"},
    )

    out = transform.apply_to_frame(frame)

    assert out.timestamp == frame.timestamp
    assert out.metadata == frame.metadata
    assert out.strips[0].pixels == [(0.2, 0.1, 0.05)]
    assert out.zones[0].color == RGBCCTColor(r=0.2, g=0.1, b=0.05)
    assert frame.strips[0].pixels == [(0.8, 0.4, 0.2)]
    assert frame.zones[0].color == RGBCCTColor(r=0.8, g=0.4, b=0.2)


def test_to_uint8_is_pure_quantization_after_transform() -> None:
    transform = OutputTransform(global_brightness=0.5)
    color = transform.apply_to_zone(
        RGBCCTColor(r=1.0, g=0.5, b=0.0, warm_white=0.25, cool_white=0.125)
    )

    assert color.to_uint8() == {
        "r": 128,
        "g": 64,
        "b": 0,
        "warm_white": 32,
        "cool_white": 16,
    }


def test_rejects_invalid_global_brightness() -> None:
    with pytest.raises(ValueError):
        OutputTransform(global_brightness=-0.1)
    with pytest.raises(ValueError):
        OutputTransform(global_brightness=1.1)


def test_json_output_emits_warm_and_cool_white_fields(tmp_path) -> None:
    path = tmp_path / "frames.jsonl"
    output = JsonOutput(path=str(path))
    frame = PixelFrame(
        timestamp=0.0,
        zones=[
            ZoneOutput(
                zone_id="z1",
                color=RGBCCTColor(
                    r=0.1, g=0.2, b=0.3, warm_white=0.4, cool_white=0.5
                ),
            )
        ],
    )

    output.open()
    try:
        output.send_frame(frame)
    finally:
        output.close()

    data = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    zone = data["zones"][0]
    assert zone["warm_white"] == 102
    assert zone["cool_white"] == 128
    assert "w" not in zone
    assert "brightness" not in zone
