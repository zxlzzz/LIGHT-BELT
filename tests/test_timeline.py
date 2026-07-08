import json
from pathlib import Path

import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import DigitalStrip, EffectContext, PixelFrame
from light_engine.show import (
    Cue,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    TargetResolver,
    TargetSelector,
    TransitionSpec,
    black_base_frame,
    transition_weight,
)


TOL = 1e-9


class RecordingSolidEffect(BaseEffect):
    contexts = []

    def __init__(self, name="solid"):
        super().__init__(name)

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.contexts.append(ctx)
        color = tuple(ctx.mode_parameters.get("color", (1.0, 0.0, 0.0)))
        strip_defs = ctx.mode_parameters.get("strip_defs", [])
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=strip["pixel_count"],
                    pixels=[color] * strip["pixel_count"],
                )
                for strip in strip_defs
            ],
        )


class CountingEffect(BaseEffect):
    def __init__(self, name="counting"):
        super().__init__(name)
        self.count = 0

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.count += 1
        value = self.count / 10.0
        strip_defs = ctx.mode_parameters.get("strip_defs", [])
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=strip["pixel_count"],
                    pixels=[(value, 0.0, 0.0)] * strip["pixel_count"],
                )
                for strip in strip_defs
            ],
        )


def _resolver():
    return TargetResolver(
        analog_zones=(),
        digital_strips=(ZoneDef(id="strip", pixel_count=1),),
    )


def _base(timestamp, sequence=1):
    return black_base_frame(
        timestamp=timestamp,
        sequence=sequence,
        analog_zones=(),
        digital_strips=(ZoneDef(id="strip", pixel_count=1),),
    )


def _ctx(timestamp, sequence=1, delta=0.1):
    return EffectContext(timestamp=timestamp, delta_time=delta, sequence=sequence)


def _runtime(cues, factory=None, duration=300.0):
    show = ShowDefinition(
        schema_version=1,
        id="timeline-test",
        duration=duration,
        cues=tuple(cues),
    )
    return ShowRuntime(
        show,
        _resolver(),
        effect_factory=factory or (lambda _name: RecordingSolidEffect()),
    )


def _cue(
    *,
    cue_id="cue",
    start=10.0,
    end=20.0,
    fade_in=2.0,
    fade_out=2.0,
    color=(1.0, 0.0, 0.0),
):
    return Cue(
        id=cue_id,
        start=start,
        end=end,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(mode="fixed", name="solid", parameters={"color": color}),
        transition=TransitionSpec(
            fade_in=fade_in,
            fade_out=fade_out,
            blend="replace",
        ),
    )


def _pixel(frame):
    return frame.strips[0].pixels[0]


def test_locked_g5_g6_time_golden_boundary_weight_local_time_and_grid():
    data = json.loads(Path("tests/goldens/show_orchestration/v1/G5_G6_time.json").read_text(encoding="utf-8"))
    cue_data = data["cue"]
    cue = _cue(
        start=cue_data["start"],
        end=cue_data["end"],
        fade_in=cue_data["fade_in"],
        fade_out=cue_data["fade_out"],
    )

    for case in data["active_cases"]:
        active = cue.start <= case["t"] < cue.end
        assert active is case["active"]

    for case in data["weight_cases"]:
        assert transition_weight(cue, case["t"]) == pytest.approx(case["weight"], abs=TOL)

    local = data["local_time"]
    assert local["show_time"] - local["cue_start"] == pytest.approx(local["expected"], abs=TOL)

    grid = data["offline_grid"]
    times = [n / grid["fps"] for n in range(grid["first_n"], grid["last_n"] + 1)]
    assert len(times) == grid["frame_count"] == 9000
    assert times[0] == 0.0
    assert times[-1] == pytest.approx((grid["frame_count"] - 1) / grid["fps"], abs=TOL)
    assert times[-1] < grid["duration"]


def test_half_open_boundaries_and_required_fade_samples():
    RecordingSolidEffect.contexts = []
    cue = _cue()
    runtime = _runtime([cue])

    cases = [
        (cue.start - 0.001, (0.0, 0.0, 0.0), 0),
        (cue.start, (0.0, 0.0, 0.0), 1),
        (cue.start + cue.transition.fade_in / 2.0, (0.5, 0.0, 0.0), 2),
        (cue.start + cue.transition.fade_in, (1.0, 0.0, 0.0), 3),
        (cue.end - cue.transition.fade_out, (1.0, 0.0, 0.0), 4),
        (cue.end - 0.001, (0.0005, 0.0, 0.0), 5),
        (cue.end, (0.0, 0.0, 0.0), 5),
    ]

    for sequence, (timestamp, expected_pixel, expected_active_count) in enumerate(cases, start=1):
        frame = runtime.render(_ctx(timestamp, sequence=sequence), _base(timestamp, sequence=sequence))
        assert _pixel(frame) == pytest.approx(expected_pixel, abs=TOL)
        assert len(RecordingSolidEffect.contexts) == expected_active_count


def test_two_second_fade_midpoint_weight_is_exact_half():
    cue = _cue(fade_in=2.0, fade_out=0.0)
    assert transition_weight(cue, cue.start + 1.0) == pytest.approx(0.5, abs=TOL)


def test_cue_starting_late_receives_show_time_and_zero_cue_local_time():
    RecordingSolidEffect.contexts = []
    cue = _cue(start=120.0, end=130.0, fade_in=0.0, fade_out=0.0)
    runtime = _runtime([cue])

    runtime.render(_ctx(120.0), _base(120.0))

    params = RecordingSolidEffect.contexts[-1].mode_parameters
    assert params["show_time"] == 120.0
    assert params["cue_local_time"] == 0.0


def test_consecutive_cues_have_no_duplicate_endpoint_or_gap():
    RecordingSolidEffect.contexts = []
    first = _cue(cue_id="first", start=0.0, end=1.0, fade_in=0.0, fade_out=0.0, color=(1.0, 0.0, 0.0))
    second = _cue(cue_id="second", start=1.0, end=2.0, fade_in=0.0, fade_out=0.0, color=(0.0, 1.0, 0.0))
    runtime = _runtime([first, second])

    before = runtime.render(_ctx(0.999, sequence=1), _base(0.999, sequence=1))
    boundary = runtime.render(_ctx(1.0, sequence=2), _base(1.0, sequence=2))

    assert _pixel(before) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)
    assert _pixel(boundary) == pytest.approx((0.0, 1.0, 0.0), abs=TOL)
    assert [ctx.mode_parameters["cue_id"] for ctx in RecordingSolidEffect.contexts] == ["first", "second"]


def test_reset_with_same_seed_reproduces_first_frames():
    cue = Cue(
        id="stateful",
        start=0.0,
        end=10.0,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(mode="fixed", name="counting"),
        transition=TransitionSpec(blend="replace"),
    )
    runtime = _runtime([cue], factory=lambda _name: CountingEffect())

    first_run = [
        _pixel(runtime.render(_ctx(t, sequence=i), _base(t, sequence=i)))
        for i, t in enumerate((0.0, 0.1, 0.2), start=1)
    ]
    runtime.reset()
    second_run = [
        _pixel(runtime.render(_ctx(t, sequence=i), _base(t, sequence=i)))
        for i, t in enumerate((0.0, 0.1, 0.2), start=1)
    ]

    assert second_run == first_run


def test_repeating_timestamp_pause_does_not_advance_state():
    cue = Cue(
        id="stateful",
        start=0.0,
        end=10.0,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(mode="fixed", name="counting"),
        transition=TransitionSpec(blend="replace"),
    )
    runtime = _runtime([cue], factory=lambda _name: CountingEffect())

    first = runtime.render(_ctx(0.5, sequence=1), _base(0.5, sequence=1))
    second = runtime.render(_ctx(0.5, sequence=2), _base(0.5, sequence=2))

    assert _pixel(second) == _pixel(first)
    assert second.sequence == 2


def test_backward_time_requires_explicit_reset():
    runtime = _runtime([_cue(start=0.0, end=10.0, fade_in=0.0, fade_out=0.0)])
    runtime.render(_ctx(2.0, sequence=1), _base(2.0, sequence=1))

    with pytest.raises(RuntimeError, match="backward timestamp"):
        runtime.render(_ctx(1.0, sequence=2), _base(1.0, sequence=2))

    runtime.reset()
    frame = runtime.render(_ctx(1.0, sequence=3), _base(1.0, sequence=3))
    assert _pixel(frame) == pytest.approx((1.0, 0.0, 0.0), abs=TOL)
