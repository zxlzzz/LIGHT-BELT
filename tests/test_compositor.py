"""Tests for Phase 13 deterministic target-scoped composition."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import DigitalStrip, PixelFrame, RGBCCTColor, ZoneOutput
from light_engine.show import (
    AnalogContribution,
    DigitalContribution,
    FrameContribution,
    TargetResolver,
    TargetSelector,
    black_base_frame,
    compose_frame,
    frame_to_contribution,
)


G4_PATH = Path("tests/goldens/show_orchestration/v1/G4_compositor.json")


def _frame(*, pixels=((0.8, 0.2, 0.1),), color=None) -> PixelFrame:
    return PixelFrame(
        timestamp=2.0,
        sequence=7,
        strips=[DigitalStrip(strip_id="strip_a", pixel_count=len(pixels), pixels=list(pixels))],
        zones=[
            ZoneOutput(
                zone_id="zone_a",
                color=color
                or RGBCCTColor(r=0.2, g=0.3, b=0.4, warm_white=0.5, cool_white=0.6),
            )
        ],
    )


def _contribution(
    *,
    pixels,
    blend="replace",
    priority=0,
    declaration_index=0,
    analog_color=None,
) -> FrameContribution:
    analog = ()
    if analog_color is not None:
        analog = (AnalogContribution(zone_id="zone_a", color=analog_color),)
    return FrameContribution(
        cue_id=f"cue-{priority}-{declaration_index}",
        priority=priority,
        declaration_index=declaration_index,
        blend=blend,
        timestamp=2.0,
        sequence=7,
        digital=(DigitalContribution(strip_id="strip_a", source_start=0, pixels=tuple(pixels)),),
        analog=analog,
    )


def test_base_strip_red_absent_contribution_leaves_red_unchanged() -> None:
    base = _frame(pixels=((1.0, 0.0, 0.0),))
    result = compose_frame(base, [_contribution(pixels=(None,))])

    assert result.strips[0].pixels == [(1.0, 0.0, 0.0)]


def test_base_strip_red_explicit_black_replace_yields_black() -> None:
    base = _frame(pixels=((1.0, 0.0, 0.0),))
    result = compose_frame(base, [_contribution(pixels=((0.0, 0.0, 0.0),))])

    assert result.strips[0].pixels == [(0.0, 0.0, 0.0)]


def test_add_rgb_clamps_exact_per_channel() -> None:
    base = _frame(pixels=((0.8, 0.2, 0.1),))
    result = compose_frame(base, [_contribution(pixels=((0.5, 0.9, 0.0),), blend="add")])

    assert result.strips[0].pixels == [(1.0, 1.0, 0.1)]


def test_rgbcct_addition_clamps_all_five_channels_independently() -> None:
    base = _frame(
        color=RGBCCTColor(r=0.8, g=0.2, b=0.1, warm_white=0.7, cool_white=0.05)
    )
    result = compose_frame(
        base,
        [
            _contribution(
                pixels=(),
                blend="add",
                analog_color=RGBCCTColor(
                    r=0.5, g=0.9, b=0.0, warm_white=0.4, cool_white=0.98
                ),
            )
        ],
    )

    assert result.zones[0].color == RGBCCTColor(
        r=1.0, g=1.0, b=0.1, warm_white=1.0, cool_white=1.0
    )


def test_deterministic_order_uses_priority_then_declaration_index() -> None:
    base = _frame(pixels=((0.0, 0.0, 0.0),))
    first = _contribution(
        pixels=((0.0, 1.0, 0.0),), priority=10, declaration_index=3
    )
    later = _contribution(
        pixels=((0.0, 0.0, 1.0),), priority=10, declaration_index=4
    )
    higher_priority_earlier_application = _contribution(
        pixels=((1.0, 0.0, 0.0),), priority=1, declaration_index=99
    )

    result_a = compose_frame(
        base, [later, first, higher_priority_earlier_application]
    )
    result_b = compose_frame(
        base, [higher_priority_earlier_application, first, later]
    )

    assert result_a.strips[0].pixels == [(0.0, 0.0, 1.0)]
    assert result_b.strips[0].pixels == [(0.0, 0.0, 1.0)]


def test_inputs_are_unchanged_after_composition() -> None:
    base = _frame(pixels=((0.2, 0.3, 0.4), (0.5, 0.6, 0.7)))
    contribution = _contribution(
        pixels=(None, (0.0, 0.0, 0.0)),
        analog_color=RGBCCTColor(r=0.0, g=0.0, b=0.0),
    )
    base_before = deepcopy(base)
    contribution_before = deepcopy(contribution)

    compose_frame(base, [contribution])

    assert base == base_before
    assert contribution == contribution_before


def test_locked_g4_compositor_vector_is_authoritative() -> None:
    vector = json.loads(G4_PATH.read_text(encoding="utf-8"))
    base = _frame(pixels=(tuple(vector["replace_absent"]["base"]),))

    absent = compose_frame(base, [_contribution(pixels=(None,))])
    black = compose_frame(
        base,
        [_contribution(pixels=(tuple(vector["replace_black"]["incoming"]),))],
    )
    added = compose_frame(
        _frame(pixels=(tuple(vector["add_rgb"]["base"]),)),
        [_contribution(pixels=(tuple(vector["add_rgb"]["incoming"]),), blend="add")],
    )

    assert absent.strips[0].pixels[0] == tuple(vector["replace_absent"]["expected"])
    assert black.strips[0].pixels[0] == tuple(vector["replace_black"]["expected"])
    assert added.strips[0].pixels[0] == tuple(vector["add_rgb"]["expected"])
    assert vector["order"] == "priority ascending, declaration_index ascending"


def test_non_finite_incoming_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        compose_frame(_frame(), [_contribution(pixels=((float("nan"), 0.0, 0.0),))])


def test_virtual_path_frame_splits_to_sparse_digital_contributions() -> None:
    strips = (
        ZoneDef(id="strip_a", pixel_count=3),
        ZoneDef(id="strip_b", pixel_count=2),
    )
    path = build_virtual_paths(
        [
            {
                "id": "path_ab",
                "segments": [
                    {
                        "strip_id": "strip_a",
                        "source_start": 0,
                        "pixel_count": 3,
                        "direction": "forward",
                        "gap_after_pixels": 0,
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
        {"strip_a": 3, "strip_b": 2},
    )[0]
    resolved = TargetResolver((), strips, virtual_paths=(path,)).resolve(
        TargetSelector("virtual_path", id="path_ab")
    )
    virtual_frame = PixelFrame(
        timestamp=2.0,
        sequence=7,
        strips=[
            DigitalStrip(
                strip_id="__virtual_path__:path_ab",
                pixel_count=5,
                pixels=[
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                    (1.0, 1.0, 0.0),
                    (1.0, 0.0, 1.0),
                ],
            )
        ],
    )

    contribution = frame_to_contribution(
        virtual_frame,
        resolved=resolved,
        cue_id="virtual",
        priority=0,
        declaration_index=0,
        blend="replace",
    )
    result = compose_frame(
        black_base_frame(
            timestamp=2.0,
            sequence=7,
            analog_zones=(),
            digital_strips=strips,
        ),
        [contribution],
    )

    assert result.strips[0].pixels == [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]
    assert result.strips[1].pixels == [(1.0, 0.0, 1.0), (1.0, 1.0, 0.0)]
