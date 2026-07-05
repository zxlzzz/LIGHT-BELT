"""Tests for SimulatorOutput thread safety, pop semantics, and simulator lifecycle."""

import threading
import time

import pytest
from light_engine.mapping.physical import (
    AnalogNodeCommand,
    DigitalNodeFrame,
    PhysicalFrame,
)
from light_engine.models import RGBCCTColor
from light_engine.outputs.simulator_output import SimulatorOutput


def _make_frame(timestamp=0.0):
    return PhysicalFrame(
        timestamp=timestamp,
        sequence=round(timestamp * 1000),
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="127.0.0.1",
                port=9001,
                pixels=[
                    (0.1, 0.2, 0.3),
                    (0.4, 0.5, 0.6),
                    (0.7, 0.8, 0.9),
                ],
            )
        ],
        analog_commands=[
            AnalogNodeCommand(
                node_id=1,
                zone_id="ceiling_left",
                color=RGBCCTColor(r=0.1, g=0.2, b=0.3),
            )
        ],
        metadata={"logical_regions": {"ceiling_left": "top"}},
    )


class TestSimulatorOutput:
    """Verify thread-safe pop semantics."""

    def test_pop_consumes_frame(self):
        out = SimulatorOutput()
        out.open()
        out.send_frame(_make_frame(0.0))
        assert out.frame_count() == 1
        f1 = out.pop_latest()
        assert f1 is not None
        assert out.frame_count() == 0
        f2 = out.pop_latest()
        assert f2 is None
        out.close()

    def test_pop_does_not_repeat_same_frame(self):
        out = SimulatorOutput()
        out.open()
        out.send_frame(_make_frame(1.0))
        f1 = out.pop_latest()
        assert f1 is not None and f1.timestamp == 1.0
        f2 = out.pop_latest()
        assert f2 is None
        out.close()

    def test_pop_latest_gets_newest_and_drains_old(self):
        out = SimulatorOutput()
        out.open()
        out.send_frame(_make_frame(1.0))
        out.send_frame(_make_frame(2.0))
        out.send_frame(_make_frame(3.0))
        f = out.pop_latest()
        assert f is not None
        assert f.timestamp == 3.0
        assert out.frame_count() == 0
        out.close()

    def test_concurrent_send_pop_no_crash(self):
        out = SimulatorOutput(max_frames=128)
        out.open()
        errors = []

        def producer():
            try:
                for i in range(500):
                    out.send_frame(_make_frame(i * 0.01))
            except Exception as e:
                errors.append(e)

        def consumer():
            try:
                for _ in range(200):
                    out.pop_latest()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=producer) for _ in range(4)]
        threads += [threading.Thread(target=consumer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        assert len(errors) == 0, f"Errors: {errors}"
        out.close()

    def test_frames_sent_and_consumed_counters(self):
        out = SimulatorOutput()
        out.open()
        for i in range(10):
            out.send_frame(_make_frame(i))
        assert out.frames_sent() == 10
        # pop_latest drains all frames, returns only the latest.
        f = out.pop_latest()
        assert f is not None
        assert out.frames_consumed() == 1
        assert out.frame_count() == 0
        out.close()

    def test_pop_latest_drops_old_frames(self):
        out = SimulatorOutput()
        out.open()
        for i in range(20):
            out.send_frame(_make_frame(i))
        f = out.pop_latest()
        assert f is not None
        assert out.frames_dropped() > 0
        out.close()


class TestSimulatorFrameCount:
    """TerminalSimulator only counts truly new frames."""

    def test_simulator_frame_count_never_exceeds_engine_generated(self):
        from light_engine.simulator import TerminalSimulator
        out = SimulatorOutput()
        out.open()
        sim = TerminalSimulator(out)
        # Feed 10 frames, then stop
        for i in range(10):
            out.send_frame(_make_frame(i * 0.033))
        # Manually simulate what happens: each pop should get a unique frame
        pop_count = 0
        while True:
            f = out.pop_latest()
            if f is None:
                break
            pop_count += 1
        # With pop_latest() draining, 10 sends should equal at most 10 pops
        assert pop_count <= 10, f"Pop count {pop_count} exceeds sent count 10"
        out.close()


class TestEngineFpsMetrics:
    """Effective FPS includes sleep; processing capacity is raw compute."""

    def test_effective_fps_about_30_for_30fps_config(self):
        from light_engine.config import Config
        from light_engine.engine import Engine
        from light_engine.outputs import NullOutput

        Config.reset()
        config = Config()
        engine = Engine(config)
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        null = NullOutput()
        null.open()
        engine._outputs = {"null": null}

        engine.run(duration=1.0)
        stats = engine.get_fps_stats()

        # With duration=1.0s and output_fps=30, expect ~30 frames and ~1s wall time
        assert abs(stats["effective_fps"] - 30.0) < 3.0, (
            f"Effective FPS {stats['effective_fps']:.1f} not near 30"
        )
        assert stats["processing_capacity"] > 30.0, (
            f"Processing capacity {stats['processing_capacity']:.1f} should exceed 30"
        )
        assert abs(stats["wall_time_s"] - 1.0) < 0.2, (
            f"Wall time {stats['wall_time_s']:.2f}s not near 1.0s"
        )

    def test_duration_2_seconds_about_2_seconds(self):
        from light_engine.config import Config
        from light_engine.engine import Engine
        from light_engine.outputs import NullOutput

        Config.reset()
        config = Config()
        engine = Engine(config)
        engine.use_synthetic(seed=42)
        engine.set_effect("static")
        null = NullOutput()
        null.open()
        engine._outputs = {"null": null}

        engine.run(duration=2.0)
        stats = engine.get_fps_stats()

        assert stats["wall_time_s"] >= 1.8, (
            f"2s duration should take ~2s, got {stats['wall_time_s']:.2f}s"
        )
        assert 58 <= stats["frame_count"] <= 62, (
            f"2s @ 30fps should produce ~60 frames, got {stats['frame_count']}"
        )


class TestSimulatorAutoExit:
    """Simulator must auto-exit when engine is done and buffer empty."""

    def test_auto_exit_when_engine_done_and_buffer_empty(self, tmp_path):
        import threading
        from light_engine.simulator import TerminalSimulator

        out = SimulatorOutput()
        out.open()

        # Feed a few frames then stop
        for i in range(5):
            out.send_frame(_make_frame(i * 0.033))

        engine_done = threading.Event()
        engine_done.set()  # Engine already "done"

        sim = TerminalSimulator(out, engine_done=engine_done)
        sim.run(max_frames=30)  # Should exit well before 30 since buffer drains

        # Should have rendered at most 5 frames (unique pop_latest calls)
        assert sim.frame_count <= 5, (
            f"Simulator rendered {sim.frame_count} frames from 5 sends"
        )
        out.close()

    def test_pop_latest_returns_none_on_empty(self):
        out = SimulatorOutput()
        out.open()
        assert out.pop_latest() is None
        out.close()

    def test_draw_displays_physical_node_grouping(self, capsys):
        from light_engine.simulator import TerminalSimulator

        out = SimulatorOutput()
        out.open()
        sim = TerminalSimulator(out)
        sim._draw(_make_frame(1.0))

        captured = capsys.readouterr().out
        assert "node 7" in captured
        assert "node 1" in captured
        assert "zone:ceiling_left" in captured
        out.close()
