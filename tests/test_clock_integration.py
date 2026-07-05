"""Engine integration tests for Phase 7 media clock ownership."""

from light_engine.clock import Clock, FakeClock, MediaEnded, OfflineRenderClock
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.outputs import NullOutput


class ScriptedClock(Clock):
    def __init__(self, times, paused=None, end_on_exhaust=False):
        self._times = list(times)
        self._paused = list(paused or [False] * len(self._times))
        self._time = self._times[0] if self._times else 0.0
        self._last = self._time
        self._ended = False
        self._end_on_exhaust = end_on_exhaust

    def now(self):
        return self._time

    def tick(self):
        if not self._times:
            if self._end_on_exhaust:
                self._ended = True
                raise MediaEnded("done")
            return 0.0
        self._last = self._time
        self._time = self._times.pop(0)
        self._is_paused = self._paused.pop(0) if self._paused else False
        return max(0.0, self._time - self._last)

    @property
    def paused(self):
        return getattr(self, "_is_paused", False)

    @property
    def ended(self):
        return self._ended


class CountingNullOutput(NullOutput):
    def __init__(self):
        super().__init__()
        self.frames = []

    def send_frame(self, frame):
        self.frames.append(frame)


def _engine(clock):
    Config.reset()
    config = Config()
    engine = Engine(config, clock=clock)
    engine.use_synthetic(seed=42)
    engine.set_effect("video_audio_fusion")
    out = CountingNullOutput()
    out.open()
    engine._outputs = {"null": out}
    return engine, out


def test_engine_accepts_injected_offline_clock():
    engine, out = _engine(OfflineRenderClock(fps=30.0))
    engine.run(max_frames=3)
    assert engine.frame_count == 3
    assert [frame.sequence for frame in out.frames] == [1, 2, 3, 4]


def test_fake_clock_pause_is_deterministic():
    clock = FakeClock()
    clock.set_paused(True)
    engine, out = _engine(clock)
    engine.run(max_frames=2)
    assert engine.frame_count == 2
    assert [frame.timestamp for frame in out.frames[:2]] == [0.0, 0.0]


def test_seek_resets_effect_without_changing_sequence_ownership():
    clock = ScriptedClock([0.0, 0.033, 5.0, 5.033])
    engine, out = _engine(clock)
    resets = []
    original_reset = engine._effect.reset

    def record_reset():
        resets.append(engine._sequence)
        original_reset()

    engine._effect.reset = record_reset
    engine.run(max_frames=4)

    assert resets
    assert [frame.sequence for frame in out.frames] == [1, 2, 3, 4, 5]


def test_end_of_media_exits_cleanly():
    clock = ScriptedClock([0.0, 0.033], end_on_exhaust=True)
    engine, out = _engine(clock)
    engine.run()
    assert engine.frame_count == 2
    assert out.frames[-1].metadata["SAFE_STATE"] is True
