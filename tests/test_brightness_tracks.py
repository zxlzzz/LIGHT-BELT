"""Show v2 target-level brightness track validation and runtime behavior."""

from __future__ import annotations

from copy import deepcopy

import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)
from light_engine.outputs.transform import OutputTransform
from light_engine.show import (
    BrightnessKeyframe,
    BrightnessTrackSpec,
    Cue,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    ShowValidationError,
    TargetCatalog,
    TargetResolver,
    TargetSelector,
    black_base_frame,
    validate_show_data,
)


def _catalog() -> TargetCatalog:
    return TargetCatalog(
        analog_zones={"zone"},
        digital_strips={"left", "right", "untouched"},
    )


def _show_data() -> dict:
    return {
        "schema_version": 2,
        "show": {
            "id": "brightness-tracks",
            "duration": 10.0,
            "cues": [],
            "brightness_tracks": [
                {
                    "id": "left-level",
                    "target": {"type": "digital_strip", "id": "left"},
                    "interpolation": "linear",
                    "keyframes": [
                        {"time": 1.0, "value": 0.2},
                        {"time": 3.0, "value": 0.8},
                    ],
                },
                {
                    "id": "right-level",
                    "target": {"type": "digital_strip", "id": "right"},
                    "interpolation": "step",
                    "keyframes": [
                        {"time": 1.0, "value": 0.25},
                        {"time": 3.0, "value": 0.75},
                    ],
                },
            ],
        },
    }


def _assert_invalid(data: dict, path: str, reason: str | None = None) -> None:
    with pytest.raises(ShowValidationError) as exc_info:
        validate_show_data(data, _catalog())
    assert exc_info.value.path == path
    if reason is not None:
        assert reason in exc_info.value.reason


def test_v2_loader_normalizes_brightness_tracks_and_defaults_to_linear() -> None:
    data = _show_data()
    del data["show"]["brightness_tracks"][0]["interpolation"]

    show = validate_show_data(data, _catalog())

    assert [track.id for track in show.brightness_tracks] == [
        "left-level",
        "right-level",
    ]
    assert show.brightness_tracks[0].interpolation == "linear"
    assert show.brightness_tracks[0].start == 1.0
    assert show.brightness_tracks[0].end == 3.0
    assert show.brightness_tracks[0].target == TargetSelector(
        "digital_strip", id="left"
    )
    assert show.brightness_tracks[0].keyframes == (
        BrightnessKeyframe(1.0, 0.2),
        BrightnessKeyframe(3.0, 0.8),
    )


def test_missing_brightness_tracks_preserves_v1_and_v2_defaults() -> None:
    v2 = _show_data()
    del v2["show"]["brightness_tracks"]
    v1 = deepcopy(v2)
    v1["schema_version"] = 1

    assert validate_show_data(v2, _catalog()).brightness_tracks == ()
    assert validate_show_data(v1, _catalog()).brightness_tracks == ()


def test_v1_rejects_brightness_tracks_instead_of_changing_legacy_schema() -> None:
    data = _show_data()
    data["schema_version"] = 1

    _assert_invalid(data, "show.show.brightness_tracks", "unknown field")


@pytest.mark.parametrize(
    ("mutate", "path", "reason"),
    [
        (
            lambda data: data["show"]["brightness_tracks"][0].update(
                {"interpolation": "spline"}
            ),
            "show.brightness_tracks[0].interpolation",
            "must be one of",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0].update(
                {"keyframes": [{"time": 1.0, "value": 0.5}]}
            ),
            "show.brightness_tracks[0].keyframes",
            "at least two",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0]["keyframes"][1].update(
                {"time": 1.0}
            ),
            "show.brightness_tracks[0].keyframes[1].time",
            "strictly greater",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0]["keyframes"][1].update(
                {"value": 1.1}
            ),
            "show.brightness_tracks[0].keyframes[1].value",
            "must be <= 1.0",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0]["keyframes"][1].update(
                {"time": 10.1}
            ),
            "show.brightness_tracks[0].keyframes[1].time",
            "must be <= 10.0",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0].update(
                {"start": 2.0}
            ),
            "show.brightness_tracks[0].keyframes[0].time",
            "track start",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0].update(
                {"end": 2.0}
            ),
            "show.brightness_tracks[0].keyframes[1].time",
            "track end",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][1].update(
                {"id": "left-level"}
            ),
            "show.brightness_tracks[1].id",
            "duplicate",
        ),
        (
            lambda data: data["show"]["brightness_tracks"][0].update(
                {"unexpected": True}
            ),
            "show.brightness_tracks[0].unexpected",
            "unknown field",
        ),
    ],
)
def test_brightness_track_schema_is_strict(mutate, path: str, reason: str) -> None:
    data = _show_data()
    mutate(data)

    _assert_invalid(data, path, reason)


class _FullFrameEffect(BaseEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=strip["pixel_count"],
                    pixels=[(0.8, 0.4, 0.2)] * strip["pixel_count"],
                )
                for strip in ctx.mode_parameters["strip_defs"]
            ],
            zones=[
                ZoneOutput(
                    zone_id=zone["id"],
                    color=RGBCCTColor(0.8, 0.4, 0.2, 0.6, 1.0),
                )
                for zone in ctx.mode_parameters["zone_defs"]
            ],
        )


def _cue(target: TargetSelector, cue_id: str) -> Cue:
    return Cue(
        id=cue_id,
        start=0.0,
        end=10.0,
        target=target,
        effect=EffectSpec(mode="fixed", id="static"),
    )


def _track(
    track_id: str,
    target: TargetSelector,
    start: float,
    start_value: float,
    end: float,
    end_value: float,
    interpolation: str = "linear",
    active_end: float | None = None,
) -> BrightnessTrackSpec:
    return BrightnessTrackSpec(
        id=track_id,
        target=target,
        start=start,
        end=end if active_end is None else active_end,
        interpolation=interpolation,
        keyframes=(
            BrightnessKeyframe(start, start_value),
            BrightnessKeyframe(end, end_value),
        ),
    )


def _runtime(
    tracks: tuple[BrightnessTrackSpec, ...],
) -> tuple[ShowRuntime, tuple[ZoneDef, ...], ZoneDef]:
    strips = (
        ZoneDef(id="left", pixel_count=1),
        ZoneDef(id="right", pixel_count=1),
        ZoneDef(id="untouched", pixel_count=1),
    )
    zone = ZoneDef(id="zone")
    show = ShowDefinition(
        schema_version=2,
        id="runtime-brightness",
        duration=10.0,
        cues=(
            _cue(
                TargetSelector(
                    "digital_set", ids=tuple(strip.id for strip in strips)
                ),
                "digital",
            ),
            _cue(TargetSelector("analog_zone", id="zone"), "analog"),
        ),
        brightness_tracks=tracks,
    )
    return (
        ShowRuntime(
            show,
            TargetResolver((zone,), strips),
            effect_factory=_FullFrameEffect,
        ),
        strips,
        zone,
    )


def _render(
    runtime: ShowRuntime,
    strips: tuple[ZoneDef, ...],
    zone: ZoneDef,
    timestamp: float,
) -> PixelFrame:
    base = black_base_frame(
        timestamp=timestamp,
        sequence=int(timestamp * 10) + 1,
        analog_zones=(zone,),
        digital_strips=strips,
    )
    return runtime.render(
        EffectContext(
            timestamp=timestamp,
            delta_time=0.1,
            sequence=base.sequence,
        ),
        base,
    )


def _pixel(frame: PixelFrame, strip_id: str) -> tuple[float, float, float]:
    return next(
        strip.pixels[0] for strip in frame.strips if strip.strip_id == strip_id
    )


def test_multiple_targets_have_independent_linear_step_and_default_levels() -> None:
    tracks = (
        _track(
            "left",
            TargetSelector("digital_strip", id="left"),
            1.0,
            0.2,
            3.0,
            0.8,
        ),
        _track(
            "right",
            TargetSelector("digital_strip", id="right"),
            1.0,
            0.25,
            3.0,
            0.75,
            "step",
            4.0,
        ),
        _track(
            "zone",
            TargetSelector("analog_zone", id="zone"),
            1.0,
            0.5,
            3.0,
            0.5,
        ),
    )
    runtime, strips, zone = _runtime(tracks)

    before = _render(runtime, strips, zone, 0.5)
    active = _render(runtime, strips, zone, 2.0)
    step_change = _render(runtime, strips, zone, 3.0)
    step_hold = _render(runtime, strips, zone, 3.5)
    after = _render(runtime, strips, zone, 4.0)

    assert _pixel(before, "left") == pytest.approx((0.8, 0.4, 0.2))
    assert _pixel(active, "left") == pytest.approx((0.4, 0.2, 0.1))
    assert _pixel(active, "right") == pytest.approx((0.2, 0.1, 0.05))
    assert _pixel(step_change, "right") == pytest.approx((0.6, 0.3, 0.15))
    assert _pixel(step_hold, "right") == pytest.approx((0.6, 0.3, 0.15))
    assert _pixel(active, "untouched") == pytest.approx((0.8, 0.4, 0.2))
    assert active.zones[0].color == RGBCCTColor(0.4, 0.2, 0.1, 0.3, 0.5)
    assert _pixel(after, "left") == pytest.approx((0.8, 0.4, 0.2))
    assert after.zones[0].color == RGBCCTColor(0.8, 0.4, 0.2, 0.6, 1.0)


def test_disjoint_tracks_on_one_strip_leave_neutral_gap_between_them() -> None:
    tracks = (
        _track(
            "early",
            TargetSelector("digital_strip", id="left"),
            0.0,
            0.5,
            1.0,
            0.5,
        ),
        _track(
            "late",
            TargetSelector("digital_strip", id="left"),
            3.0,
            0.25,
            4.0,
            0.25,
        ),
    )
    runtime, strips, zone = _runtime(tracks)

    early = _render(runtime, strips, zone, 0.5)
    gap = _render(runtime, strips, zone, 2.0)
    late = _render(runtime, strips, zone, 3.5)

    assert _pixel(early, "left") == pytest.approx((0.4, 0.2, 0.1))
    assert _pixel(gap, "left") == pytest.approx((0.8, 0.4, 0.2))
    assert _pixel(late, "left") == pytest.approx((0.2, 0.1, 0.05))


def test_overlapping_tracks_for_one_concrete_target_fail_explicitly() -> None:
    tracks = (
        _track(
            "first",
            TargetSelector("digital_strip", id="left"),
            0.0,
            0.5,
            2.0,
            0.5,
        ),
        _track(
            "second",
            TargetSelector("digital_strip", id="left"),
            1.0,
            0.25,
            3.0,
            0.25,
        ),
    )

    with pytest.raises(ValueError, match="overlap.*left"):
        _runtime(tracks)


def test_show_without_tracks_keeps_existing_render_output_unchanged() -> None:
    runtime, strips, zone = _runtime(())

    frame = _render(runtime, strips, zone, 2.0)

    assert [_pixel(frame, strip.id) for strip in strips] == [
        pytest.approx((0.8, 0.4, 0.2)),
        pytest.approx((0.8, 0.4, 0.2)),
        pytest.approx((0.8, 0.4, 0.2)),
    ]
    assert frame.zones[0].color == RGBCCTColor(0.8, 0.4, 0.2, 0.6, 1.0)


def test_target_level_and_global_output_brightness_have_separate_ownership() -> None:
    tracks = (
        _track(
            "left",
            TargetSelector("digital_strip", id="left"),
            1.0,
            0.5,
            3.0,
            0.5,
        ),
    )
    runtime, strips, zone = _runtime(tracks)
    logical = _render(runtime, strips, zone, 2.0)

    physical = OutputTransform(
        global_brightness=0.5,
        power_limit=5.0,
        gamma=1.0,
    ).apply_to_frame(logical)

    assert _pixel(physical, "left") == pytest.approx((0.2, 0.1, 0.05))
    assert _pixel(physical, "untouched") == pytest.approx((0.4, 0.2, 0.1))
