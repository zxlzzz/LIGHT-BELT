from argparse import Namespace

import pytest

import light_engine.cli as cli
import light_engine.engine as engine_module
from light_engine.clock import Clock
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.outputs import NullOutput
from light_engine.show import ShowDefinition, ShowRuntime


class ScriptedClock(Clock):
    def __init__(self, times):
        self._times = list(times)
        self._time = self._times[0] if self._times else 0.0
        self._last = self._time

    def now(self):
        return self._time

    def tick(self):
        if not self._times:
            return 0.0
        self._last = self._time
        self._time = self._times.pop(0)
        return max(0.0, self._time - self._last)


class RecordingOutput(NullOutput):
    def __init__(self):
        super().__init__()
        self.frames = []

    def send_frame(self, frame):
        self.frames.append(frame)


def _engine_with_show(clock, show):
    Config.reset()
    config = Config()
    engine = Engine(config, clock=clock)
    engine.set_show_runtime(ShowRuntime.from_layout(show, engine._layout))
    output = RecordingOutput()
    output.open()
    engine._outputs = {"recording": output}
    return engine, output


def _empty_show(duration=300.0):
    return ShowDefinition(
        schema_version=1,
        id="empty-show",
        duration=duration,
        cues=(),
    )


def test_show_engine_composes_no_cue_state_against_explicit_black_base(monkeypatch):
    captured = []

    def capture_send_all(_outputs, frame):
        captured.append(frame)

    monkeypatch.setattr(engine_module, "send_all", capture_send_all)
    engine, _output = _engine_with_show(ScriptedClock([0.0]), _empty_show())

    engine.run(max_frames=1)

    authored = captured[0]
    assert authored.sequence == 1
    assert len(authored.analog_commands) == 6
    assert all(command.color.r == 0.0 for command in authored.analog_commands)
    assert all(command.color.g == 0.0 for command in authored.analog_commands)
    assert all(command.color.b == 0.0 for command in authored.analog_commands)
    assert all(command.color.warm_white == 0.0 for command in authored.analog_commands)
    assert all(command.color.cool_white == 0.0 for command in authored.analog_commands)
    assert all(
        pixel == (0.0, 0.0, 0.0)
        for digital_frame in authored.digital_frames
        for pixel in digital_frame.pixels
    )


def test_show_engine_stops_before_evaluating_t_at_duration():
    engine, output = _engine_with_show(ScriptedClock([299.9666666667, 300.0]), _empty_show(duration=300.0))

    engine.run(duration=300.0)

    authored_frames = [frame for frame in output.frames if not frame.metadata.get("SAFE_STATE")]
    assert [frame.timestamp for frame in authored_frames] == [299.9666666667]


def test_engine_backward_clock_jump_fails_clearly():
    engine, _output = _engine_with_show(ScriptedClock([1.0, 0.5]), _empty_show())

    with pytest.raises(RuntimeError, match="clock moved backward"):
        engine.run(max_frames=2)


def test_validate_show_creates_no_engine_or_outputs(monkeypatch):
    class ForbiddenEngine:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("validate-show must not construct Engine")

    monkeypatch.setattr(cli, "Engine", ForbiddenEngine)
    Config.reset()
    args = Namespace(config=None, show="config/show.example.yaml")

    result = cli.cmd_validate_show(args)

    assert result == 0


def test_run_show_accepts_adaptive_runtime(monkeypatch):
    sent = []

    def capture_send_all(_outputs, frame):
        sent.append(frame)

    monkeypatch.setattr(engine_module, "send_all", capture_send_all)
    Config.reset()
    args = Namespace(
        config=None,
        clock="offline",
        mpv_socket=None,
        video=None,
        audio=None,
        effect=None,
        show="config/show.example.yaml",
        duration=0.1,
        max_frames=1,
    )

    result = cli.cmd_run(args)

    assert result == 0
    assert sent
