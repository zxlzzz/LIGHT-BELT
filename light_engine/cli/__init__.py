"""CLI module for light engine commands."""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from light_engine import __version__
from light_engine.clock import FakeClock, MpvIPCClock, OfflineRenderClock
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.outputs import health_summary


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_health_summary(outputs: dict) -> None:
    print("Output health summary:")
    print(json.dumps(health_summary(outputs), indent=2, sort_keys=True))


def _default_mpv_socket() -> str:
    return str(Path(tempfile.gettempdir()) / "light-belt-mpv-ipc")


def _clock_from_args(args: argparse.Namespace, config: Config):
    mode = getattr(args, "clock", None) or config.get("system.clock.mode", "internal")
    if mode == "internal":
        return OfflineRenderClock(fps=config.get("system.output_fps", 30.0))
    if mode == "offline":
        return OfflineRenderClock(fps=config.get("system.output_fps", 30.0))
    if mode == "fake":
        return FakeClock()
    if mode == "mpv":
        clock = MpvIPCClock(getattr(args, "mpv_socket", None) or _default_mpv_socket())
        clock.connect()
        return clock
    raise ValueError(f"Unknown clock mode: {mode}")


def cmd_demo(args: argparse.Namespace) -> int:
    """Run demo with synthetic data."""
    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging(config.get("system.logging.level", "INFO"))

    engine = Engine(config, clock=_clock_from_args(args, config))
    engine.use_synthetic(seed=args.seed)
    engine.set_effect(args.effect or "demo")
    engine.init_outputs()

    print(f"Light Engine v{__version__} - Demo Mode")
    print(f"  Effect: {args.effect or 'demo'}")
    print(f"  Duration: {args.duration}s")
    print(f"  Outputs: {list(engine._outputs.keys())}")
    print(f"  Press Ctrl+C to stop")

    engine.run(duration=args.duration, max_frames=args.max_frames)

    stats = engine.get_fps_stats()
    print(f"\nCompleted: {stats['frame_count']} frames")
    print(f"  Wall time: {stats['wall_time_s']:.2f}s")
    print(f"  Effective FPS: {stats['effective_fps']:.1f}")
    print(f"  Processing capacity: {stats['processing_capacity']:.1f} FPS")
    print(f"  P50: {stats['p50_ms']:.2f}ms  P95: {stats['p95_ms']:.2f}ms  P99: {stats['p99_ms']:.2f}ms")
    _print_health_summary(engine._outputs)

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run with media files."""
    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging(config.get("system.logging.level", "INFO"))

    engine = Engine(config, clock=_clock_from_args(args, config))
    if args.video:
        try:
            engine.load_video(args.video)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.audio:
        try:
            engine.load_audio(args.audio)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if not args.video and not args.audio:
        engine.use_synthetic()

    engine.set_effect(args.effect or "video_audio_fusion")
    engine.init_outputs()

    print(f"Light Engine v{__version__} - Run Mode")
    print(f"  Video: {args.video or 'generated'}")
    print(f"  Audio: {args.audio or 'generated'}")
    print(f"  Effect: {args.effect or 'video_audio_fusion'}")

    engine.run(duration=args.duration, max_frames=args.max_frames)

    stats = engine.get_fps_stats()
    print(f"\nCompleted: {stats['frame_count']} frames")
    print(f"  Effective FPS: {stats['effective_fps']:.1f}")
    print(f"  Processing capacity: {stats['processing_capacity']:.1f} FPS")
    _print_health_summary(engine._outputs)

    return 0


def cmd_simulator(args: argparse.Namespace) -> int:
    """Run the terminal simulator."""
    from light_engine.outputs import SimulatorOutput
    from light_engine.simulator import TerminalSimulator

    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging(config.get("system.logging.level", "INFO"))

    sim_out = SimulatorOutput()
    sim_out.open()

    engine = Engine(config, clock=_clock_from_args(args, config))
    if args.video:
        try:
            engine.load_video(args.video)
        except FileNotFoundError as e:
            print(f"Warning: {e} - using synthetic data")
    if args.audio:
        try:
            engine.load_audio(args.audio)
        except FileNotFoundError as e:
            print(f"Warning: {e} - using synthetic data")
    if not args.video and not args.audio:
        engine.use_synthetic(seed=args.seed)

    engine.set_effect(args.effect or "demo")
    engine._outputs = {"simulator": sim_out}

    import threading
    engine_done = threading.Event()

    def _engine_runner():
        try:
            engine.run(duration=args.duration, max_frames=args.max_frames)
        finally:
            engine_done.set()

    engine_thread = threading.Thread(
        target=_engine_runner,
        daemon=True,
    )
    engine_thread.start()

    sim = TerminalSimulator(sim_out, config, engine_done=engine_done)
    try:
        sim.run(max_frames=args.max_frames)
    except KeyboardInterrupt:
        pass
    finally:
        engine._running = False
        engine_done.set()
        engine_thread.join(timeout=3.0)

    print(f"\nEngine Generated: {sim_out.frames_sent()}")
    print(f"Simulator Rendered: {sim.frame_count}")
    print(f"Frames Dropped: {sim_out.frames_dropped()}")
    _print_health_summary(engine._outputs)

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export lighting data to JSONL file."""
    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging(config.get("system.logging.level", "INFO"))

    # Force JSON output
    config._data["outputs"] = {"enabled": ["json"], "json": {"path": args.output, "pretty": False}}

    engine = Engine(config, clock=_clock_from_args(args, config))
    if args.video:
        try:
            engine.load_video(args.video)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.audio:
        try:
            engine.load_audio(args.audio)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if not args.video and not args.audio:
        engine.use_synthetic()

    engine.set_effect(args.effect or "video_audio_fusion")
    engine.init_outputs()

    print(f"Exporting to {args.output}...")
    engine.run(duration=args.duration, max_frames=args.max_frames)
    print(f"Exported {engine.frame_count} frames to {args.output}")
    _print_health_summary(engine._outputs)

    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run performance benchmark."""
    from light_engine.outputs import NullOutput

    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging("WARNING")

    engine = Engine(config, clock=_clock_from_args(args, config))
    engine.use_synthetic(seed=args.seed)
    engine.set_effect(args.effect or "video_audio_fusion")

    # Use NullOutput for benchmarking
    null_out = NullOutput()
    null_out.open()
    engine._outputs = {"null": null_out}

    print(f"Benchmark: {args.frames} frames, effect={args.effect or 'video_audio_fusion'}")
    print(f"  Strips: {len(engine._strip_defs)}, "
          f"Pixels: {sum(s['pixel_count'] for s in engine._strip_defs)}")
    print(f"  Zones: {len(engine._zone_defs)}")
    print(f"  OS: {os.name}, Python: {sys.version.split()[0]}")

    import time
    start = time.perf_counter()
    engine.run(max_frames=args.frames)
    elapsed = time.perf_counter() - start

    stats = engine.get_fps_stats()
    print(f"\nResults ({stats['frame_count']} frames in {stats['wall_time_s']:.2f}s):")
    print(f"  Processing: {stats['processing_capacity']:.1f} FPS")
    print(f"  P50:        {stats['p50_ms']:.2f} ms")
    print(f"  P95:        {stats['p95_ms']:.2f} ms")
    print(f"  P99:        {stats['p99_ms']:.2f} ms")
    print(f"\n  Machine:    {os.environ.get('COMPUTERNAME', 'unknown')} ({os.name})")
    print(f"  Target:     RK3588 ARM64 Linux (30 FPS target)")
    print(f"  Verified:   Current machine only - NOT RK3588")
    _print_health_summary(engine._outputs)

    return 0


def cmd_run_mpv(args: argparse.Namespace) -> int:
    """Launch or connect to mpv JSON IPC and run the lighting engine."""
    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging(config.get("system.logging.level", "INFO"))

    socket_path = args.mpv_socket or _default_mpv_socket()
    mpv_process = None
    if args.media:
        mpv_cmd = [
            args.mpv_binary,
            f"--input-ipc-server={socket_path}",
            "--idle=yes",
            args.media,
        ]
        try:
            mpv_process = subprocess.Popen(mpv_cmd)
        except OSError as e:
            print(f"Error: failed to start mpv: {e}", file=sys.stderr)
            return 1

    try:
        clock = MpvIPCClock(socket_path)
        clock.connect()
    except Exception as e:
        if mpv_process is not None:
            mpv_process.terminate()
        print(f"Error: {e}", file=sys.stderr)
        return 1

    engine = Engine(config, clock=clock)
    engine.set_effect(args.effect or "video_audio_fusion")
    engine.init_outputs()

    print(f"Light Engine v{__version__} - mpv Clock Mode")
    print(f"  IPC: {socket_path}")
    print(f"  Effect: {args.effect or 'video_audio_fusion'}")
    print("  Clock: mpv")

    try:
        engine.run(duration=args.duration, max_frames=args.max_frames)
    finally:
        clock.close()
        if mpv_process is not None:
            mpv_process.terminate()
            mpv_process.wait(timeout=3.0)

    stats = engine.get_fps_stats()
    print(f"\nCompleted: {stats['frame_count']} frames")
    print(f"  Effective FPS: {stats['effective_fps']:.1f}")
    print(f"  Processing capacity: {stats['processing_capacity']:.1f} FPS")
    _print_health_summary(engine._outputs)
    return 0


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="light_engine",
        description=f"Light Engine v{__version__} - Video/music driven multi-zone lighting prototype",
    )
    parser.add_argument("--version", action="version", version=f"light_engine {__version__}")
    parser.add_argument("--config", "-c", default=None, help="Path to config directory")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # demo
    p_demo = subparsers.add_parser("demo", help="Run demo with synthetic data")
    p_demo.add_argument("--effect", "-e", default="demo", help="Effect name")
    p_demo.add_argument("--duration", "-d", type=float, default=30.0, help="Duration in seconds")
    p_demo.add_argument("--max-frames", "-n", type=int, default=None, help="Max output frames")
    p_demo.add_argument("--seed", type=int, default=42, help="Random seed")
    p_demo.add_argument("--clock", choices=["internal", "offline", "fake"], default="internal")

    # run
    p_run = subparsers.add_parser("run", help="Run with media files")
    p_run.add_argument("--video", "-v", default=None, help="Path to video file")
    p_run.add_argument("--audio", "-a", default=None, help="Path to audio file")
    p_run.add_argument("--effect", "-e", default=None, help="Effect name")
    p_run.add_argument("--duration", "-d", type=float, default=None, help="Duration in seconds")
    p_run.add_argument("--max-frames", "-n", type=int, default=None, help="Max output frames")
    p_run.add_argument("--clock", choices=["internal", "offline", "fake", "mpv"], default="internal")
    p_run.add_argument("--mpv-socket", default=None, help="mpv JSON IPC socket path")

    # simulator
    p_sim = subparsers.add_parser("simulator", help="Run terminal simulator")
    p_sim.add_argument("--video", "-v", default=None, help="Path to video file")
    p_sim.add_argument("--audio", "-a", default=None, help="Path to audio file")
    p_sim.add_argument("--effect", "-e", default="demo", help="Effect name")
    p_sim.add_argument("--duration", "-d", type=float, default=None, help="Duration in seconds")
    p_sim.add_argument("--max-frames", "-n", type=int, default=None, help="Max output frames")
    p_sim.add_argument("--seed", type=int, default=42, help="Random seed")
    p_sim.add_argument("--clock", choices=["internal", "offline", "fake"], default="internal")

    # export
    p_export = subparsers.add_parser("export", help="Export lighting data to JSONL")
    p_export.add_argument("--video", "-v", default=None, help="Path to video file")
    p_export.add_argument("--audio", "-a", default=None, help="Path to audio file")
    p_export.add_argument("--effect", "-e", default=None, help="Effect name")
    p_export.add_argument("--output", "-o", default="output.jsonl", help="Output file path")
    p_export.add_argument("--duration", "-d", type=float, default=None, help="Duration in seconds")
    p_export.add_argument("--max-frames", "-n", type=int, default=None, help="Max output frames")
    p_export.add_argument("--clock", choices=["internal", "offline", "fake", "mpv"], default="offline")
    p_export.add_argument("--mpv-socket", default=None, help="mpv JSON IPC socket path")

    # benchmark
    p_bench = subparsers.add_parser("benchmark", help="Run performance benchmark")
    p_bench.add_argument("--effect", "-e", default="video_audio_fusion", help="Effect name")
    p_bench.add_argument("--frames", "-n", type=int, default=600, help="Number of frames")
    p_bench.add_argument("--seed", type=int, default=42, help="Random seed")
    p_bench.add_argument("--clock", choices=["internal", "offline", "fake"], default="offline")

    # run-mpv
    p_run_mpv = subparsers.add_parser("run-mpv", help="Run using mpv JSON IPC clock")
    p_run_mpv.add_argument("--media", "-m", default=None, help="Optional media path to launch with mpv")
    p_run_mpv.add_argument("--mpv-binary", default="mpv", help="mpv executable")
    p_run_mpv.add_argument("--mpv-socket", default=None, help="mpv JSON IPC socket path")
    p_run_mpv.add_argument("--effect", "-e", default=None, help="Effect name")
    p_run_mpv.add_argument("--duration", "-d", type=float, default=None, help="Duration in seconds")
    p_run_mpv.add_argument("--max-frames", "-n", type=int, default=None, help="Max output frames")

    args = parser.parse_args()

    if args.command == "demo":
        sys.exit(cmd_demo(args))
    elif args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "simulator":
        sys.exit(cmd_simulator(args))
    elif args.command == "export":
        sys.exit(cmd_export(args))
    elif args.command == "benchmark":
        sys.exit(cmd_benchmark(args))
    elif args.command == "run-mpv":
        sys.exit(cmd_run_mpv(args))
    elif args.command == "inspect-video":
        sys.exit(cmd_inspect_video(args))
    elif args.command == "inspect-audio":
        sys.exit(cmd_inspect_audio(args))
    elif args.command == "inspect-effect":
        sys.exit(cmd_inspect_effect(args))
    elif args.command == "inspect-serial":
        sys.exit(cmd_inspect_serial(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
