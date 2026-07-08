import json
from pathlib import Path

import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    MusicControlState,
    PixelFrame,
)
from light_engine.show import (
    AudioControlSpec,
    Cue,
    CueRenderJob,
    EffectSpec,
    TargetResolver,
    TargetSelector,
    TransitionSpec,
)
from light_engine.show.adaptive_selector import (
    REASON_CODES,
    AdaptiveEffectSelector,
    SelectionDecision,
)


G7_PATH = Path("tests/goldens/show_orchestration/v1/G7_music_expectations.json")


class RecordingEffect(BaseEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=strip["pixel_count"],
                    pixels=[(ctx.speed / 4.0, 0.0, 0.0)] * strip["pixel_count"],
                )
                for strip in ctx.mode_parameters["strip_defs"]
            ],
            metadata={"decision": ctx.mode_parameters.get("selection_decision")},
        )


def _state(**kwargs) -> MusicControlState:
    values = {"timestamp": 0.0}
    values.update(kwargs)
    return MusicControlState(**values)


def _cue(
    *,
    allowed=None,
    fallback="color_wave",
    confirmation=0.0,
    hold=0.0,
    cooldown=0.0,
    beat_subdivision=1.0,
) -> Cue:
    return Cue(
        id="adaptive",
        start=0.0,
        end=30.0,
        target=TargetSelector(kind="digital_strip", id="strip"),
        effect=EffectSpec(
            mode="adaptive",
            allowed=allowed
            or {
                "silence": "calm",
                "calm": "breath",
                "flowing": "color_wave",
                "ambient": "color_wave",
                "rhythmic": "chase",
                "energetic": "comet",
                "impact": "comet",
                "transition": "color_wave",
            },
            fallback=fallback,
        ),
        audio_control=AudioControlSpec(
            tempo_sync="auto",
            tempo_confidence_min=0.70,
            beat_regularity_min=0.70,
            beats_per_cycle=4.0,
            beat_subdivision=beat_subdivision,
            speed_smoothing_seconds=1.0,
            state_confirmation_seconds=confirmation,
            min_effect_hold=hold,
            switch_cooldown=cooldown,
        ),
    )


def _selector(**kwargs) -> AdaptiveEffectSelector:
    return AdaptiveEffectSelector(_cue(**kwargs))


def test_rhythmic_high_confidence_uses_beat_sync_and_declared_effect():
    selector = _selector()

    decision = selector.evaluate(
        4.0,
        _state(
            timestamp=4.0,
            tempo_bpm=120.0,
            tempo_confidence=0.95,
            beat_strength=0.8,
            beat_regularity=0.9,
            energy=0.5,
        ),
    )

    assert decision.music_state == "rhythmic"
    assert decision.sync_mode == "beat_sync"
    assert decision.reason_code == "BEAT_CONFIDENT"
    assert decision.selected_effect == "chase"
    assert decision.tempo_period == pytest.approx(2.0)
    assert decision.speed > 0.0


def test_piano_irregular_uses_event_fallback_without_bpm_lock():
    decision = _selector().evaluate(
        1.0,
        _state(timestamp=1.0, transient=0.7, energy=0.4, tempo_confidence=0.1),
    )

    assert decision.sync_mode == "event_sync"
    assert decision.reason_code == "EVENT_FALLBACK"
    assert decision.selected_effect == "color_wave"
    assert decision.speed > 0.0


def test_string_crescendo_uses_envelope_behavior():
    decision = _selector().evaluate(
        1.0,
        _state(timestamp=1.0, energy=0.35, energy_trend=0.4, spectral_motion=0.2),
    )

    assert decision.music_state == "transition"
    assert decision.sync_mode == "envelope_sync"
    assert decision.reason_code == "ENVELOPE_FALLBACK"
    assert decision.selected_effect == "color_wave"


def test_sustained_bass_ambient_does_not_repeatedly_enter_impact():
    selector = _selector()
    attack = selector.evaluate(
        0.0,
        _state(timestamp=0.0, energy=0.6, bass_ambient=0.9, bass_pulse=0.8),
    )
    steady = [
        selector.evaluate(
            t,
            _state(timestamp=t, energy=0.5, bass_ambient=0.9, bass_pulse=0.05),
        )
        for t in (0.3, 0.6, 0.9)
    ]

    assert attack.music_state == "impact"
    assert [item.music_state for item in steady] == ["ambient", "ambient", "ambient"]
    assert [item.selected_effect for item in steady] == ["color_wave"] * 3


def test_near_static_uses_free_run_and_continues_animating():
    decision = _selector().evaluate(
        1.0,
        _state(timestamp=1.0, energy=0.02, tempo_confidence=0.0),
    )

    assert decision.music_state == "silence"
    assert decision.sync_mode == "free_run"
    assert decision.reason_code == "FREE_RUN_FALLBACK"
    assert decision.speed > 0.0


def test_threshold_noise_does_not_chatter_before_confirmation():
    selector = _selector(confirmation=1.0)
    timeline = [
        selector.evaluate(0.0, _state(timestamp=0.0, energy=0.02)),
        selector.evaluate(0.2, _state(timestamp=0.2, energy=0.19)),
        selector.evaluate(0.4, _state(timestamp=0.4, energy=0.02)),
        selector.evaluate(0.6, _state(timestamp=0.6, energy=0.19)),
    ]

    assert [item.selected_effect for item in timeline] == ["calm"] * 4
    assert timeline[1].reason_code == "STATE_UNCONFIRMED"
    assert timeline[3].reason_code == "STATE_UNCONFIRMED"


def test_min_hold_blocks_brief_state_change():
    selector = _selector(hold=5.0)
    first = selector.evaluate(0.0, _state(timestamp=0.0, energy=0.02))
    second = selector.evaluate(2.0, _state(timestamp=2.0, energy=0.4))

    assert first.selected_effect == "calm"
    assert second.selected_effect == "calm"
    assert second.hold_active is True
    assert second.reason_code == "HOLD_ACTIVE"


def test_switch_cooldown_blocks_second_switch():
    selector = _selector(cooldown=4.0)
    selector.evaluate(0.0, _state(timestamp=0.0, energy=0.02))
    switched = selector.evaluate(4.1, _state(timestamp=4.1, energy=0.4))
    blocked = selector.evaluate(
        5.0,
        _state(timestamp=5.0, energy=0.5, transient=0.9, bass_pulse=0.8),
    )

    assert switched.selected_effect == "color_wave"
    assert blocked.selected_effect == "color_wave"
    assert blocked.cooldown_active is True
    assert blocked.reason_code == "COOLDOWN_ACTIVE"


def test_low_confidence_tempo_avoids_beat_sync_and_speed_stays_positive():
    decision = _selector().evaluate(
        3.0,
        _state(
            timestamp=3.0,
            tempo_bpm=120.0,
            tempo_confidence=0.1,
            beat_regularity=0.2,
            beat_strength=0.8,
            transient=0.6,
            energy=0.5,
        ),
    )

    assert decision.sync_mode == "event_sync"
    assert decision.reason_code == "EVENT_FALLBACK"
    assert decision.speed > 0.0


def test_effect_absent_from_allowed_is_never_instantiated():
    created = []
    cue = _cue(allowed={"silence": "calm", "flowing": "color_wave"}, fallback="calm")
    resolver = TargetResolver([ZoneDef(id="zone")], [ZoneDef(id="strip", pixel_count=2)])

    def factory(name):
        created.append(name)
        return RecordingEffect(name)

    job = CueRenderJob(cue, 0, resolver, effect_factory=factory)
    job.render(
        EffectContext(
            timestamp=1.0,
            delta_time=0.1,
            music_control_state=_state(timestamp=1.0, energy=0.5, transient=0.9),
        )
    )

    assert created == ["calm"]
    assert "comet" not in created


def test_fixed_cues_ignore_adaptive_state_changes():
    cue = Cue(
        id="fixed",
        start=0.0,
        end=10.0,
        target=TargetSelector(kind="digital_strip", id="strip"),
        effect=EffectSpec(mode="fixed", name="breath"),
    )
    resolver = TargetResolver([ZoneDef(id="zone")], [ZoneDef(id="strip", pixel_count=2)])
    created = []

    def factory(name):
        created.append(name)
        return RecordingEffect(name)

    job = CueRenderJob(cue, 0, resolver, effect_factory=factory)
    job.render(
        EffectContext(
            timestamp=1.0,
            delta_time=0.1,
            music_control_state=_state(timestamp=1.0, energy=0.8, transient=0.9),
        )
    )

    assert created == ["breath"]


def test_identical_runs_produce_same_selected_effect_timeline():
    states = [
        _state(timestamp=0.0, energy=0.02),
        _state(timestamp=6.0, energy=0.4),
        _state(timestamp=12.0, tempo_bpm=120, tempo_confidence=1.0, beat_regularity=1.0, beat_strength=1.0, energy=0.5),
        _state(timestamp=18.0, energy=0.5, transient=0.9, bass_pulse=0.8),
    ]

    def run():
        selector = _selector(hold=2.0, cooldown=1.0)
        return [selector.evaluate(state.timestamp, state).selected_effect for state in states]

    assert run() == run()


def test_every_decision_exposes_locked_reason_snapshot_and_gate_status():
    decision = _selector().evaluate(1.0, _state(timestamp=1.0, energy=0.02))

    assert isinstance(decision, SelectionDecision)
    assert decision.reason_code in REASON_CODES
    assert set(json.loads(G7_PATH.read_text(encoding="utf-8"))["selector_reason_codes"]) == REASON_CODES
    assert set(decision.source_features) == {
        "timestamp",
        "tempo_bpm",
        "tempo_confidence",
        "beat_phase",
        "beat_strength",
        "beat_regularity",
        "energy",
        "energy_trend",
        "transient",
        "bass_ambient",
        "bass_pulse",
        "spectral_motion",
    }
    assert decision.hold_active is False
    assert decision.cooldown_active is False
    assert decision.confirmation_active is False


@pytest.mark.parametrize(
    ("fixture", "state", "expected_state", "expected_sync", "expected_reason"),
    [
        (
            "rhythmic_120bpm.wav",
            _state(timestamp=4.0, tempo_bpm=120.0, tempo_confidence=0.95, beat_regularity=0.9, beat_strength=0.8, energy=0.5),
            "rhythmic",
            "beat_sync",
            "BEAT_CONFIDENT",
        ),
        (
            "piano_irregular.wav",
            _state(timestamp=1.0, transient=0.7, energy=0.4, tempo_confidence=0.1),
            "flowing",
            "event_sync",
            "EVENT_FALLBACK",
        ),
        (
            "string_crescendo.wav",
            _state(timestamp=1.0, energy=0.35, energy_trend=0.4, spectral_motion=0.2),
            "transition",
            "envelope_sync",
            "ENVELOPE_FALLBACK",
        ),
        (
            "sustained_bass_pad.wav",
            _state(timestamp=4.0, energy=0.5, bass_ambient=0.9, bass_pulse=0.05),
            "ambient",
            "free_run",
            "FREE_RUN_FALLBACK",
        ),
        (
            "silence.wav",
            _state(timestamp=1.0, energy=0.0),
            "silence",
            "free_run",
            "FREE_RUN_FALLBACK",
        ),
    ],
)
def test_locked_g7_fixture_expectations_drive_decision_table(
    fixture, state, expected_state, expected_sync, expected_reason
):
    expectations = json.loads(G7_PATH.read_text(encoding="utf-8"))
    assert fixture in expectations["fixtures"]

    decision = _selector().evaluate(state.timestamp, state)

    assert decision.music_state == expected_state
    assert decision.sync_mode == expected_sync
    assert decision.reason_code == expected_reason


def test_tempo_modulation_is_smoothed_and_quantized_to_configured_subdivision():
    selector = _selector(beat_subdivision=1.0)
    first = selector.evaluate(
        0.0,
        _state(timestamp=0.0, tempo_bpm=120.0, tempo_confidence=1.0, beat_regularity=1.0, beat_strength=1.0, energy=0.5),
    )
    second = selector.evaluate(
        0.5,
        _state(timestamp=0.5, tempo_bpm=180.0, tempo_confidence=1.0, beat_regularity=1.0, beat_strength=1.0, energy=0.5),
    )

    assert first.tempo_period == pytest.approx(2.0)
    assert second.tempo_period == pytest.approx(1.6666666667)
    assert first.speed < second.speed < 3.0
