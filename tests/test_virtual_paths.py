"""Tests for continuous virtual digital-strip paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_engine.config import ConfigError
from light_engine.mapping import Layout, ZoneDef
from light_engine.mapping.physical import (
    AnalogNodeMapping,
    DigitalNodeMapping,
    DigitalSegmentMapping,
)
from light_engine.mapping.virtual import build_virtual_paths, render_virtual_path


GOLDEN_PATH = Path("tests/goldens/show_orchestration/v1/G3_virtual_path.json")


def _locked_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _split_by_strip(contributions) -> dict[str, list[str]]:
    return {
        contribution.strip_id: list(contribution.pixels)
        for contribution in contributions
    }


def _layout_with_node_assignment(
    digital_nodes: list[DigitalNodeMapping],
    digital_segments: list[DigitalSegmentMapping],
) -> Layout:
    return Layout(
        zones=[ZoneDef(id=f"zone_{idx}") for idx in range(1, 7)],
        strips=[
            ZoneDef(id="strip_a", pixel_count=2),
            ZoneDef(id="strip_b", pixel_count=2),
        ],
        analog_nodes=[
            AnalogNodeMapping(node_id=idx, zone_id=f"zone_{idx}")
            for idx in range(1, 7)
        ],
        digital_nodes=digital_nodes,
        digital_segments=digital_segments,
        virtual_paths=build_virtual_paths(
            [
                {
                    "id": "screen_to_wall",
                    "segments": [
                        {
                            "strip_id": "strip_a",
                            "source_start": 0,
                            "pixel_count": 2,
                            "direction": "forward",
                        },
                        {
                            "strip_id": "strip_b",
                            "source_start": 0,
                            "pixel_count": 2,
                            "direction": "reverse",
                        },
                    ],
                }
            ],
            {"strip_a": 2, "strip_b": 2},
        ),
    )


def test_locked_g3_gold_vector_splits_forward_and_reverse_segments() -> None:
    golden = _locked_golden()
    path = build_virtual_paths(
        [{"id": "gold", "segments": golden["segments"]}],
        {"strip_a": 3, "strip_b": 2},
    )[0]

    contributions = path.split(golden["path_buffer"])

    assert path.total_length == 5
    assert [(segment.global_start, segment.global_end) for segment in path.segments] == [
        (0, 3),
        (3, 5),
    ]
    assert _split_by_strip(contributions) == golden["expected"]


def test_one_pixel_head_crosses_seam_without_restart() -> None:
    golden = _locked_golden()
    path = build_virtual_paths(
        [{"id": "gold", "segments": golden["segments"]}],
        {"strip_a": 3, "strip_b": 2},
    )[0]

    for frame in golden["seam_frames"]:
        buffer = ["."] * path.total_length
        buffer[frame["global_head"]] = "H"
        contributions = path.split(buffer)
        lit = [
            (contribution.strip_id, contribution.source_start + pixel_index)
            for contribution in contributions
            for pixel_index, value in enumerate(contribution.pixels)
            if value == "H"
        ]

        assert len(lit) == frame["lit_count"]
        assert lit == [
            (frame["expected_target"], frame["expected_destination_index"])
        ]


def test_reverse_changes_destination_order_not_global_phase() -> None:
    path = build_virtual_paths(
        [
            {
                "id": "reverse",
                "segments": [
                    {
                        "strip_id": "strip_a",
                        "source_start": 0,
                        "pixel_count": 1,
                        "direction": "forward",
                    },
                    {
                        "strip_id": "strip_b",
                        "source_start": 0,
                        "pixel_count": 2,
                        "direction": "reverse",
                    },
                ],
            }
        ],
        {"strip_a": 1, "strip_b": 2},
    )[0]

    contributions = path.split(["A0", "B0", "B1"])

    assert path.segments[1].global_start == 1
    assert path.segments[1].global_end == 3
    assert _split_by_strip(contributions)["strip_b"] == ["B1", "B0"]


def test_partial_strip_segment_stays_sparse_not_black_padded() -> None:
    path = build_virtual_paths(
        [
            {
                "id": "partial",
                "segments": [
                    {
                        "strip_id": "strip_a",
                        "source_start": 2,
                        "pixel_count": 2,
                        "direction": "forward",
                    }
                ],
            }
        ],
        {"strip_a": 5},
    )[0]

    contribution = path.split(["R", "G"])[0]

    assert contribution.strip_id == "strip_a"
    assert contribution.source_start == 2
    assert contribution.source_end == 4
    assert list(contribution.pixels) == ["R", "G"]


def test_locked_g3_two_coordinate_gap_extends_virtual_space_only() -> None:
    golden = _locked_golden()
    gap_case = golden["gap_case"]
    path = build_virtual_paths(
        [{"id": "gap", "segments": gap_case["segments"]}],
        {"strip_a": 2, "strip_b": 2},
    )[0]

    mapped_coordinates = [
        coord
        for segment in path.segments
        for coord in range(segment.global_start, segment.global_end)
    ]
    unmapped_gap_coordinates = [
        coord
        for gap in path.gaps
        for coord in range(gap.global_start, gap.global_end)
    ]
    contributions = path.split(["A0", "A1", "gap0", "gap1", "B0", "B1"])

    assert path.total_length == gap_case["total_virtual_length"]
    assert mapped_coordinates == gap_case["mapped_coordinates"]
    assert unmapped_gap_coordinates == gap_case["unmapped_gap_coordinates"]
    assert _split_by_strip(contributions) == {
        "strip_a": ["A0", "A1"],
        "strip_b": ["B0", "B1"],
    }


def test_overlapping_source_ranges_in_one_path_fail() -> None:
    with pytest.raises(ConfigError, match="non-overlapping source pixels"):
        build_virtual_paths(
            [
                {
                    "id": "bad",
                    "segments": [
                        {
                            "strip_id": "strip_a",
                            "source_start": 0,
                            "pixel_count": 2,
                            "direction": "forward",
                        },
                        {
                            "strip_id": "strip_a",
                            "source_start": 1,
                            "pixel_count": 2,
                            "direction": "forward",
                        },
                    ],
                }
            ],
            {"strip_a": 4},
        )


def test_render_virtual_path_calls_renderer_once_for_complete_path_buffer() -> None:
    calls: list[int] = []
    path = build_virtual_paths(
        [
            {
                "id": "once",
                "segments": [
                    {
                        "strip_id": "strip_a",
                        "source_start": 0,
                        "pixel_count": 2,
                        "direction": "forward",
                    },
                    {
                        "strip_id": "strip_b",
                        "source_start": 0,
                        "pixel_count": 1,
                        "direction": "forward",
                    },
                ],
            }
        ],
        {"strip_a": 2, "strip_b": 1},
    )[0]

    contributions = render_virtual_path(
        path,
        lambda total_length: calls.append(total_length) or ["R", "G", "B"],
    )

    assert calls == [3]
    assert _split_by_strip(contributions) == {
        "strip_a": ["R", "G"],
        "strip_b": ["B"],
    }


def test_virtual_path_result_is_independent_of_esp32_node_assignments() -> None:
    single_node_layout = _layout_with_node_assignment(
        [DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=4)],
        [
            DigitalSegmentMapping("a", "strip_a", node_id=7, offset=0, pixel_count=2),
            DigitalSegmentMapping("b", "strip_b", node_id=7, offset=2, pixel_count=2),
        ],
    )
    split_node_layout = _layout_with_node_assignment(
        [
            DigitalNodeMapping(node_id=7, host="10.0.0.10", port=9001, pixel_count=2),
            DigitalNodeMapping(node_id=8, host="10.0.0.11", port=9001, pixel_count=2),
        ],
        [
            DigitalSegmentMapping("a", "strip_a", node_id=7, offset=0, pixel_count=2),
            DigitalSegmentMapping("b", "strip_b", node_id=8, offset=0, pixel_count=2),
        ],
    )
    single_node = single_node_layout.get_virtual_path("screen_to_wall")
    split_nodes = split_node_layout.get_virtual_path("screen_to_wall")

    assert single_node.summary() == split_nodes.summary()
    assert single_node.split(["R", "G", "B", "Y"]) == split_nodes.split(
        ["R", "G", "B", "Y"]
    )


def test_virtual_path_summary_is_deterministic() -> None:
    path = build_virtual_paths(
        [
            {
                "id": "summary",
                "segments": [
                    {
                        "strip_id": "strip_a",
                        "source_start": 1,
                        "pixel_count": 2,
                        "direction": "forward",
                        "gap_after_pixels": 1,
                    },
                    {
                        "strip_id": "strip_b",
                        "source_start": 0,
                        "pixel_count": 1,
                        "direction": "reverse",
                    },
                ],
            }
        ],
        {"strip_a": 4, "strip_b": 1},
    )[0]

    summary = path.summary()

    assert summary.mapped_pixel_count == 3
    assert summary.gap_coordinate_count == 1
    assert summary.total_virtual_length == 4
    assert summary.participating_strips == ("strip_a", "strip_b")
    assert summary.subranges == (
        {
            "strip_id": "strip_a",
            "source_start": 1,
            "source_end": 3,
            "global_start": 0,
            "global_end": 2,
            "direction": "forward",
            "gap_after_pixels": 1,
        },
        {
            "strip_id": "strip_b",
            "source_start": 0,
            "source_end": 1,
            "global_start": 3,
            "global_end": 4,
            "direction": "reverse",
            "gap_after_pixels": 0,
        },
    )
    assert summary.gaps == (
        {"global_start": 2, "global_end": 3, "pixel_count": 1},
    )
