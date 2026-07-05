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


def test_power_limit_clamps_total_zone_power() -> None:
    transform = OutputTransform(global_brightness=1.0, power_limit=1.0)

    out = transform.apply_to_zone(
        RGBCCTColor(
            r=1.0, g=1.0, b=1.0, warm_white=1.0, cool_white=1.0
        )
    )

    total = out.r + out.g + out.b + out.warm_white + out.cool_white
    assert total == pytest.approx(1.0)
    assert out == RGBCCTColor(
        r=0.2, g=0.2, b=0.2, warm_white=0.2, cool_white=0.2
    )


def test_gamma_correction_is_monotonic() -> None:
    transform = OutputTransform(gamma=2.2)

    values = [0.0, 0.25, 0.5, 0.75, 1.0]
    corrected = [transform.gamma_correct(value) for value in values]

    assert corrected == sorted(corrected)
    assert corrected[0] == 0.0
    assert corrected[-1] == 1.0


def test_per_zone_warm_and_cool_bias_are_applied() -> None:
    transform = OutputTransform(
        power_limit=5.0,
        per_zone_warm_bias={"front": 0.5},
        per_zone_cool_bias={"front": 2.0},
    )

    out = transform.apply_to_zone(
        RGBCCTColor(warm_white=0.6, cool_white=0.2),
        zone_id="front",
    )

    assert out.warm_white == pytest.approx(0.3)
    assert out.cool_white == pytest.approx(0.4)


def test_global_brightness_applies_once_to_digital_pixels() -> None:
    transform = OutputTransform(global_brightness=0.25)
    frame = PixelFrame(
        timestamp=1.0,
        sequence=12,
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
    assert out.sequence == 12
    assert out.metadata == frame.metadata
    assert out.strips[0].pixels == [(0.2, 0.1, 0.05)]
    assert out.zones[0].color == RGBCCTColor(r=0.2, g=0.1, b=0.05)
    assert frame.strips[0].pixels == [(0.8, 0.4, 0.2)]
    assert frame.zones[0].color == RGBCCTColor(r=0.8, g=0.4, b=0.2)


def test_extended_transform_does_not_mutate_input_frame() -> None:
    transform = OutputTransform(
        global_brightness=0.5,
        power_limit=0.5,
        gamma=2.0,
        per_zone_warm_bias={"z1": 0.25},
    )
    frame = PixelFrame(
        timestamp=2.0,
        sequence=9,
        strips=[
            DigitalStrip(
                strip_id="s1",
                pixel_count=2,
                pixels=[(1.0, 0.5, 0.25), (0.25, 0.5, 1.0)],
            )
        ],
        zones=[
            ZoneOutput(
                zone_id="z1",
                color=RGBCCTColor(
                    r=1.0, g=0.5, b=0.25, warm_white=0.75, cool_white=0.5
                ),
            )
        ],
        metadata={"effect": "test"},
    )

    out = transform.apply_to_frame(frame)

    assert out is not frame
    assert out.strips[0] is not frame.strips[0]
    assert out.zones[0] is not frame.zones[0]
    assert frame.strips[0].pixels == [(1.0, 0.5, 0.25), (0.25, 0.5, 1.0)]
    assert frame.zones[0].color == RGBCCTColor(
        r=1.0, g=0.5, b=0.25, warm_white=0.75, cool_white=0.5
    )


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


def test_generate_safe_frame_is_all_black_with_metadata() -> None:
    frame = OutputTransform.generate_safe_frame(
        timestamp=1.25,
        sequence=77,
        zone_ids=["front", "rear"],
        strips=[{"id": "strip_a", "pixel_count": 3}],
        metadata={"reason": "shutdown"},
    )

    assert frame.timestamp == 1.25
    assert frame.sequence == 77
    assert frame.metadata["SAFE_STATE"] is True
    assert frame.metadata["safe_state"] is True
    assert frame.metadata["reason"] == "shutdown"
    assert [zone.zone_id for zone in frame.zones] == ["front", "rear"]
    assert all(zone.color == RGBCCTColor() for zone in frame.zones)
    assert frame.strips[0].pixels == [(0.0, 0.0, 0.0)] * 3


def test_json_output_emits_warm_and_cool_white_fields(tmp_path) -> None:
    path = tmp_path / "frames.jsonl"
    output = JsonOutput(path=str(path))
    frame = PixelFrame(
        timestamp=0.0,
        sequence=44,
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
    assert data["sequence"] == 44
    zone = data["zones"][0]
    assert zone["warm_white"] == 102
    assert zone["cool_white"] == 128
    assert "w" not in zone
    assert "brightness" not in zone
