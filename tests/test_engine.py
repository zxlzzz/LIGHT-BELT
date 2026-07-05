"""Tests for engine media-finished logic and run-loop stop conditions."""

import numpy as np
import pytest
from light_engine.config import Config
import light_engine.engine as engine_module
from light_engine.engine import Engine
from light_engine.models import RoutedFrame
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


class TestFrameSequence:
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

    def test_engine_builds_routed_frame_before_output(self, monkeypatch):
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
        assert isinstance(captured[0], RoutedFrame)
        assert captured[0].logical.sequence == 1
        assert captured[0].physical.sequence == 1
        assert captured[0].logical.timestamp == captured[0].physical.timestamp
        assert len(captured[0].physical.analog_commands) == 6
        assert len(captured[0].physical.digital_frames) == 1
        assert captured[1].logical.sequence == 2
        assert captured[1].logical.metadata["SAFE_STATE"] is True
        assert all(
            command.color.r == 0.0
            and command.color.g == 0.0
            and command.color.b == 0.0
            and command.color.warm_white == 0.0
            and command.color.cool_white == 0.0
            for command in captured[1].physical.analog_commands
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
