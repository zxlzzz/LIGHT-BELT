"""Tests for engine media-finished logic and run-loop stop conditions."""

import numpy as np
import pytest
from light_engine.clock import Clock
from light_engine.config import Config
import light_engine.engine as engine_module
from light_engine.engine import Engine
from light_engine.mapping.physical import PhysicalFrame
from light_engine.models import RGBCCTColor
from light_engine.show import (
    Cue,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    TargetSelector,
    TransitionSpec,
)
from light_engine.outputs import NullOutput


def _make_engine():
    Config.reset()
    config = Config()
    engine = Engine(config)
    engine.use_synthetic(seed=42)
    engine.set_effect("video_audio_fusion")
    null = NullOutput()
    null.open()
    engine._outputs = {"null": null}
    return engine


class TestDurationLimit:
    def test_duration_takes_priority(self):
        engine = _make_engine()
        engine.run(duration=1.0)
        assert 28 <= engine.frame_count <= 33, f"Expected ~30 frames, got {engine.frame_count}"

    def test_duration_overrides_media(self):
        engine = _make_engine()
        engine.run(duration=0.5)
        assert engine.frame_count < 20


class RecordingOutput(NullOutput):
    def __init__(self):
        super().__init__()
        self.frames = []

    def send_frame(self, frame):
        self.frames.append(frame)


class SessionRecordingOutput(RecordingOutput):
    def __init__(self):
        super().__init__()
        self.open_calls = 0
        self.close_calls = 0

    def open(self):
        self.open_calls += 1
        super().open()

    def send_frame(self, frame):
        if not self.is_open():
            raise RuntimeError("recording output is closed")
        super().send_frame(frame)

    def close(self):
        self.close_calls += 1
        super().close()


class ScriptedClock(Clock):
    def __init__(self, times):
        self._times = list(times)
        self._time = self._times[0] if self._times else 0.0

    def now(self):
        return self._time

    def tick(self):
        previous = self._time
        if self._times:
            self._time = self._times.pop(0)
        return max(0.0, self._time - previous)


class TestFrameSequence:
    @pytest.mark.parametrize("mode", ["memory", "production"])
    def test_default_host_session_starts_at_sequence_one(self, mode):
        Config.reset()
        config = Config()
        config._data["outputs"]["mode"] = mode
        engine = Engine(config)
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = RecordingOutput()
        output.open()
        engine._outputs = {"recording": output}

        engine.run(max_frames=1)

        assert [frame.sequence for frame in output.frames] == [1, 2]
        assert output.frames[-1].metadata["SAFE_STATE"] is True

    def test_engine_sequence_wraps_as_uint32(self):
        Config.reset()
        config = Config()
        engine = Engine(config, sequence_seed=0xFFFFFFFF)
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = RecordingOutput()
        output.open()
        engine._outputs = {"recording": output}

        engine.run(max_frames=1)

        assert [frame.sequence for frame in output.frames] == [0, 1]

        engine.run(max_frames=1)

        assert [frame.sequence for frame in output.frames] == [0, 1, 0, 1]

    def test_same_engine_reopens_outputs_and_starts_each_run_from_one(self):
        Config.reset()
        engine = Engine(Config())
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = SessionRecordingOutput()
        output.open()
        engine._outputs = {"recording": output}

        engine.run(max_frames=2)
        assert output.is_open() is False
        assert engine.frame_count == 2

        engine.run(max_frames=2)

        authored = [
            frame.sequence
            for frame in output.frames
            if not frame.metadata.get("SAFE_STATE")
        ]
        safe = [
            frame.sequence
            for frame in output.frames
            if frame.metadata.get("SAFE_STATE")
        ]
        assert authored == [1, 2, 1, 2]
        assert safe == [3, 3]
        assert output.open_calls == 2
        assert output.close_calls == 2
        assert output.is_open() is False
        assert engine.frame_count == 2

    def test_same_engine_duration_run_resets_engine_owned_offline_clock(self):
        Config.reset()
        engine = Engine(Config())
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = SessionRecordingOutput()
        output.open()
        engine._outputs = {"recording": output}

        engine.run(duration=0.1)
        first_authored = [
            (frame.sequence, frame.timestamp)
            for frame in output.frames
            if not frame.metadata.get("SAFE_STATE")
        ]
        first_end = len(output.frames)

        engine.run(duration=0.1)
        second_authored = [
            (frame.sequence, frame.timestamp)
            for frame in output.frames[first_end:]
            if not frame.metadata.get("SAFE_STATE")
        ]

        assert first_authored == second_authored
        assert first_authored

    def test_engine_reads_final_output_transform_configuration(self):
        Config.reset()
        config = Config()
        config._data["system"]["smoothing"]["max_brightness"] = 0.75
        config._data["system"]["smoothing"]["gamma"] = 1.8
        config._data["outputs"]["transform"] = {
            "power_limit": 1.5,
            "per_zone_warm_bias": {"front": 0.8},
            "per_zone_cool_bias": {"front": 1.2},
        }

        engine = Engine(config)

        transform = engine._output_transform
        assert transform.global_brightness == 0.75
        assert transform.gamma == 1.8
        assert transform.power_limit == 1.5
        assert transform.per_zone_warm_bias == {"front": 0.8}
        assert transform.per_zone_cool_bias == {"front": 1.2}

    def test_engine_assigns_monotonic_frame_sequence(self):
        Config.reset()
        config = Config()
        engine = Engine(config)
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = RecordingOutput()
        output.open()
        engine._outputs = {"recording": output}

        engine.run(max_frames=5)

        assert [frame.sequence for frame in output.frames] == [1, 2, 3, 4, 5, 6]
        assert output.frames[-1].metadata["SAFE_STATE"] is True

    def test_exit_safe_state_configuration_can_explicitly_disable_shutdown_frame(self):
        Config.reset()
        config = Config()
        config._data["outputs"]["exit_safe_state"] = False
        engine = Engine(config)
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = RecordingOutput()
        output.open()
        engine._outputs = {"recording": output}

        engine.run(max_frames=1)

        assert [frame.sequence for frame in output.frames] == [1]
        assert all(not frame.metadata.get("SAFE_STATE") for frame in output.frames)

    def test_engine_sends_physical_frame_to_output(self, monkeypatch):
        captured = []

        def capture_send_all(_outputs, frame):
            captured.append(frame)

        monkeypatch.setattr(engine_module, "send_all", capture_send_all)
        Config.reset()
        config = Config()
        engine = Engine(config)
        engine.set_effect("static")
        output = NullOutput()
        output.open()
        engine._outputs = {"null": output}

        engine.run(max_frames=1)

        assert len(captured) == 2
        assert isinstance(captured[0], PhysicalFrame)
        assert captured[0].sequence == 1
        assert len(captured[0].analog_commands) == 6
        assert len(captured[0].digital_frames) == 1
        assert captured[1].sequence == 2
        assert captured[1].metadata["SAFE_STATE"] is True
        assert all(
            command.color.r == 0.0
            and command.color.g == 0.0
            and command.color.b == 0.0
            and command.color.warm_white == 0.0
            and command.color.cool_white == 0.0
            for command in captured[1].analog_commands
        )

    def test_engine_show_runtime_composes_independent_targets(self, monkeypatch):
        captured = []

        def capture_send_all(_outputs, frame):
            captured.append(frame)

        monkeypatch.setattr(engine_module, "send_all", capture_send_all)
        Config.reset()
        config = Config()
        engine = Engine(config)
        show = ShowDefinition(
            schema_version=1,
            id="phase-13-smoke",
            duration=5.0,
            cues=(
                Cue(
                    id="front-chase",
                    start=0.0,
                    end=5.0,
                    priority=1,
                    target=TargetSelector("digital_strip", id="front"),
                    effect=EffectSpec(mode="fixed", name="chase"),
                    transition=TransitionSpec(blend="replace"),
                ),
                Cue(
                    id="rear-comet",
                    start=0.0,
                    end=5.0,
                    priority=1,
                    target=TargetSelector("digital_strip", id="rear"),
                    effect=EffectSpec(mode="fixed", name="comet"),
                    transition=TransitionSpec(blend="replace"),
                ),
                Cue(
                    id="wall-breath",
                    start=0.0,
                    end=5.0,
                    priority=1,
                    target=TargetSelector("analog_zone", id="wall_left"),
                    effect=EffectSpec(mode="fixed", name="breath"),
                    transition=TransitionSpec(blend="replace"),
                ),
            ),
        )
        engine.set_show_runtime(ShowRuntime.from_layout(show, engine._layout))
        output = NullOutput()
        output.open()
        engine._outputs = {"null": output}

        engine.run(max_frames=1)

        first_frame = captured[0]
        assert isinstance(first_frame, PhysicalFrame)
        assert first_frame.sequence == 1
        analog_by_zone = {command.zone_id: command.color for command in first_frame.analog_commands}
        assert analog_by_zone["wall_left"] != RGBCCTColor()
        assert analog_by_zone["ceiling_left"] == RGBCCTColor()
        assert any(
            pixel != (0.0, 0.0, 0.0)
            for digital_frame in first_frame.digital_frames
            for pixel in digital_frame.pixels
        )

    def test_shutdown_closes_outputs_when_safe_frame_send_fails(self, monkeypatch):
        def failing_send_all(_outputs, _frame):
            raise RuntimeError("safe send failed")

        monkeypatch.setattr(engine_module, "send_all", failing_send_all)
        Config.reset()
        config = Config()
        engine = Engine(config)
        output = NullOutput()
        output.open()
        engine._outputs = {"null": output}

        engine._shutdown()

        assert output.is_open() is False
        assert engine.diagnostics()["running"] is False
        assert engine.diagnostics()["last_error"] == "safe send failed"


class TestMaxFramesLimit:
    def test_max_frames_takes_priority(self):
        engine = _make_engine()
        engine.run(max_frames=10)
        assert engine.frame_count == 10

    def test_max_frames_overrides_duration(self):
        engine = _make_engine()
        engine.run(duration=999.0, max_frames=5)
        assert engine.frame_count == 5


class TestSyntheticSource:
    def test_synthetic_runs_to_end(self):
        engine = _make_engine()
        engine._output_fps = 300.0
        engine.run(max_frames=200)
        assert engine.frame_count == 200

    @staticmethod
    def _engine_at(times):
        Config.reset()
        engine = Engine(Config(), clock=ScriptedClock(times))
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        output = RecordingOutput()
        output.open()
        engine._outputs = {"recording": output}
        return engine, output

    def test_explicit_duration_outlives_synthetic_fixture(self, monkeypatch):
        monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)
        engine, output = self._engine_at([119.9, 120.0, 299.9, 300.0])

        engine.run(duration=300.0)

        authored = [frame for frame in output.frames if not frame.metadata.get("SAFE_STATE")]
        assert [frame.timestamp for frame in authored] == [119.9, 120.0, 299.9]

    def test_synthetic_fixture_still_ends_naturally_without_duration(self, monkeypatch):
        monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)
        engine, output = self._engine_at([119.9, 120.0])

        engine.run()

        authored = [frame for frame in output.frames if not frame.metadata.get("SAFE_STATE")]
        assert [frame.timestamp for frame in authored] == [119.9]


class TestAudioOnlyStop:
    def test_audio_stops_at_end(self):
        from light_engine.data.test_media import generate_test_wav, cleanup_test_media
        wav_path = generate_test_wav(None, duration=0.5, sample_rate=44100)
        try:
            Config.reset()
            config = Config()
            engine = Engine(config)
            engine.load_audio(wav_path)
            engine.set_effect("spectrum")
            null = NullOutput()
            null.open()
            engine._outputs = {"null": null}
            engine.run()
            assert 12 <= engine.frame_count <= 18, f"Expected ~15 frames, got {engine.frame_count}"
        finally:
            cleanup_test_media(wav_path)


class TestVideoOnlyStop:
    def test_video_stops_at_end(self):
        from light_engine.data.test_media import generate_test_video, cleanup_test_media
        vid_path = generate_test_video(None, duration=1.0, fps=30.0, width=160, height=90)
        try:
            Config.reset()
            config = Config()
            engine = Engine(config)
            engine.load_video(vid_path)
            engine.set_effect("video_ambient")
            null = NullOutput()
            null.open()
            engine._outputs = {"null": null}
            engine.run()
            assert 25 <= engine.frame_count <= 35, f"Expected ~30 frames, got {engine.frame_count}"
        finally:
            cleanup_test_media(vid_path)


class TestAudioVideoBothStop:
    def test_both_stop_at_longest(self):
        from light_engine.data.test_media import generate_test_wav, generate_test_video, cleanup_test_media
        wav_path = generate_test_wav(None, duration=0.5, sample_rate=44100)
        vid_path = generate_test_video(None, duration=1.0, fps=30.0, width=160, height=90)
        try:
            Config.reset()
            config = Config()
            engine = Engine(config)
            engine.load_audio(wav_path)
            engine.load_video(vid_path)
            engine.set_effect("video_audio_fusion")
            null = NullOutput()
            null.open()
            engine._outputs = {"null": null}
            engine.run()
            assert 25 <= engine.frame_count <= 35, f"Expected ~30 frames, got {engine.frame_count}"
        finally:
            cleanup_test_media(wav_path, vid_path)


class TestNoHiddenGate:
    def test_no_100_frame_hidden_limit(self):
        engine = _make_engine()
        engine._output_fps = 300.0
        engine.run(max_frames=200)
        assert engine.frame_count == 200


class TestTenSecondsAudio:
    def test_ten_seconds_audio_produces_about_300_frames(self):
        from light_engine.data.test_media import generate_test_wav, cleanup_test_media
        wav_path = generate_test_wav(None, duration=10.0, sample_rate=44100)
        try:
            Config.reset()
            config = Config()
            engine = Engine(config)
            engine.load_audio(wav_path)
            engine.set_effect("spectrum")
            null = NullOutput()
            null.open()
            engine._outputs = {"null": null}
            engine.run()
            assert 295 <= engine.frame_count <= 305, f"Expected ~300 frames, got {engine.frame_count}"
        finally:
            cleanup_test_media(wav_path)
