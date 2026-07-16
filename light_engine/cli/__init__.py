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
from light_engine.config import Config, ConfigError
from light_engine.engine import Engine
from light_engine.mapping import Layout
from light_engine.outputs import health_summary
from light_engine.show import ShowValidationError, ShowRuntime, TargetCatalog, load_show


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


def _load_show_for_config(show_path: str, config: Config):
    layout = Layout.from_config(config)
    catalog = TargetCatalog.from_layout(layout)
    return load_show(Path(show_path), catalog), layout


def _configure_engine_show(engine: Engine, show_path: str) -> float:
    show, _layout = _load_show_for_config(show_path, engine._config)
    engine.set_show_runtime(ShowRuntime.from_layout(show, engine._layout))
    return show.duration


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

    show_duration = None
    if args.show:
        try:
            show_duration = _configure_engine_show(engine, args.show)
        except (OSError, ShowValidationError, ValueError, KeyError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        engine.set_effect(args.effect or "video_audio_fusion")
    try:
        engine.init_outputs()
    except Exception as exc:
        print(f"Error: output initialization failed: {exc}", file=sys.stderr)
        _print_health_summary(engine._outputs)
        return 1

    print(f"Light Engine v{__version__} - Run Mode")
    print(f"  Video: {args.video or 'generated'}")
    print(f"  Audio: {args.audio or 'generated'}")
    if args.show:
        print(f"  Show: {args.show}")
    else:
        print(f"  Effect: {args.effect or 'video_audio_fusion'}")

    try:
        engine.run(
            duration=args.duration if args.duration is not None else show_duration,
            max_frames=args.max_frames,
        )
    except Exception as exc:
        print(f"Error: output run failed: {exc}", file=sys.stderr)
        _print_health_summary(engine._outputs)
        return 1

    stats = engine.get_fps_stats()
    print(f"\nCompleted: {stats['frame_count']} frames")
    print(f"  Effective FPS: {stats['effective_fps']:.1f}")
    print(f"  Processing capacity: {stats['processing_capacity']:.1f} FPS")
    _print_health_summary(engine._outputs)

    summary = health_summary(engine._outputs)
    if summary["totals"]["healthy_outputs"] != summary["totals"]["outputs"]:
        print("Error: one or more outputs are unhealthy", file=sys.stderr)
        return 1
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

    show_duration = None
    if args.show:
        try:
            show_duration = _configure_engine_show(engine, args.show)
        except (OSError, ShowValidationError, ValueError, KeyError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        engine.set_effect(args.effect or "video_audio_fusion")
    engine.init_outputs()

    print(f"Exporting to {args.output}...")
    engine.run(duration=args.duration if args.duration is not None else show_duration, max_frames=args.max_frames)
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
    show_duration = None
    if args.show:
        try:
            show_duration = _configure_engine_show(engine, args.show)
        except (OSError, ShowValidationError, ValueError, KeyError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        engine.set_effect(args.effect or "video_audio_fusion")
    engine.init_outputs()

    print(f"Light Engine v{__version__} - mpv Clock Mode")
    print(f"  IPC: {socket_path}")
    if args.show:
        print(f"  Show: {args.show}")
    else:
        print(f"  Effect: {args.effect or 'video_audio_fusion'}")
    print("  Clock: mpv")

    try:
        engine.run(duration=args.duration if args.duration is not None else show_duration, max_frames=args.max_frames)
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


def cmd_validate_show(args: argparse.Namespace) -> int:
    config = Config.get_instance(Path(args.config) if args.config else None)
    setup_logging(config.get("system.logging.level", "INFO"))
    try:
        show, _layout = _load_show_for_config(args.show, config)
    except (OSError, ShowValidationError, ValueError, KeyError) as e:
        print(f"Invalid show: {e}", file=sys.stderr)
        return 1
    print(f"Show valid: {show.id} ({len(show.cues)} cues, duration={show.duration:g}s)")
    return 0


def _configured_outputs(config: Config) -> tuple[bool, bool]:
    """Return explicitly enabled UDP v3 and RS-485 v2 transport states."""
    enabled = set(config.get("outputs.enabled", []))
    udp_enabled = "udp_v3" in enabled and config.get("outputs.udp_v3.enabled", False) is True
    rs485_enabled = "rs485_v2" in enabled and config.get("outputs.rs485_v2.enabled", True) is not False
    return udp_enabled, rs485_enabled


def _digital_inspection_row(layout: Layout, strip_id: str, *, source_start: int, pixel_count: int, direction: str) -> dict:
    strip = layout.get_strip(strip_id)
    if strip is None:
        raise ValueError(f"validated layout has no logical strip {strip_id!r}")
    output = next((item for item in layout.digital_outputs if item.strip_id == strip_id), None)
    if output is None:
        raise ValueError(f"validated layout has no physical output for {strip_id!r}")
    node = next((item for item in layout.digital_nodes if item.node_id == output.node_id), None)
    if node is None:
        raise ValueError(f"validated layout has no digital node {output.node_id!r}")
    return {
        "logical_id": strip.id,
        "logical_label": strip.label or strip.id,
        "installation_id": strip.id.removeprefix("strip_"),
        "source_start": source_start,
        "pixel_count": pixel_count,
        "direction": direction,
        "node_id": node.node_id,
        "output_id": output.output_id,
        "gpio": output.gpio,
        "physical_label": f"ESP32-S3 node {node.node_id}, output {output.output_id}, GPIO{output.gpio}",
        "host": node.host,
        "port": node.port,
    }


def _analog_inspection_row(layout: Layout, config: Config, zone_id: str) -> dict:
    zone = layout.get_zone(zone_id)
    if zone is None:
        raise ValueError(f"validated layout has no analog zone {zone_id!r}")
    node = next((item for item in layout.analog_nodes if item.zone_id == zone_id), None)
    if node is None:
        raise ValueError(f"validated layout has no analog node for {zone_id!r}")
    return {
        "logical_id": zone.id,
        "logical_label": zone.label or zone.id,
        "installation_id": zone.id.removeprefix("zone_"),
        "pixel_count": zone.pixel_count,
        "node_id": node.node_id,
        "output_id": None,
        "gpio": None,
        "physical_label": f"STM32 RS-485 node {node.node_id}",
        "host": None,
        "port": config.get("outputs.serial.port"),
    }


def build_topology_inspection(config: Config, show_path: str | None = None) -> dict:
    """Trace validated logical targets to their configured physical endpoints.

    No parallel mapping table is kept here.  The layout and an optional Show v2
    file have already passed their normal validators before this report is
    constructed.
    """
    layout = Layout.from_config(config)
    udp_enabled, rs485_enabled = _configured_outputs(config)
    virtual_paths: list[dict] = []

    if show_path:
        show, _ = _load_show_for_config(show_path, config)
        for path in show.virtual_paths:
            regions = []
            for index, target in enumerate(path.targets):
                if target.kind == "digital_strip" and target.id is not None:
                    region = _digital_inspection_row(
                        layout, target.id, source_start=0,
                        pixel_count=layout.get_strip(target.id).pixel_count,  # type: ignore[union-attr]
                        direction=layout.get_strip(target.id).direction,  # type: ignore[union-attr]
                    )
                    region["transport_enabled"] = udp_enabled
                elif target.kind == "analog_zone" and target.id is not None:
                    region = _analog_inspection_row(layout, config, target.id)
                    region["transport_enabled"] = rs485_enabled
                else:  # The Show v2 validator currently excludes this in paths.
                    raise ValueError(f"unsupported inspected virtual-path target {target.kind!r}")
                region["region_index"] = index
                regions.append(region)
            virtual_paths.append({
                "id": path.id,
                "origin": path.origin,
                "regions": regions,
            })
        source = {"kind": "show_v2", "path": show_path}
    else:
        for path in layout.virtual_paths:
            regions = []
            for index, segment in enumerate(path.segments):
                region = _digital_inspection_row(
                    layout,
                    segment.strip_id,
                    source_start=segment.source_start,
                    pixel_count=segment.pixel_count,
                    direction=segment.direction,
                )
                region["region_index"] = index
                region["transport_enabled"] = udp_enabled
                regions.append(region)
            virtual_paths.append({
                "id": path.id,
                "origin": "layout_order",
                "regions": regions,
            })
        source = {"kind": "layout", "path": None}

    analog_zones = []
    for zone in layout.zones:
        row = _analog_inspection_row(layout, config, zone.id)
        row["transport_enabled"] = rs485_enabled
        analog_zones.append(row)

    return {
        "schema_version": 1,
        "source": source,
        "output_mode": config.get("outputs.mode"),
        "transports": {
            "udp_v3_enabled": udp_enabled,
            "rs485_v2_enabled": rs485_enabled,
        },
        "summary": {
            "digital_strips": len(layout.strips),
            "analog_zones": len(layout.zones),
            "physical_fixtures": len(layout.strips) + len(layout.zones),
        },
        "virtual_paths": virtual_paths,
        "analog_zones": analog_zones,
        "hardware_verification": "NOT HARDWARE VERIFIED",
    }


def cmd_inspect_topology(args: argparse.Namespace) -> int:
    """Print a config-derived virtual-path-to-physical-topology report."""
    try:
        config = Config(Path(args.config)) if args.config else Config.get_instance()
        report = build_topology_inspection(config, args.show)
    except (OSError, ShowValidationError, ConfigError, ValueError, KeyError) as exc:
        print(f"Unable to inspect topology: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
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
    p_run.add_argument("--show", default=None, help="Path to authored show YAML")
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
    p_export.add_argument("--show", default=None, help="Path to authored show YAML")
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
    p_run_mpv.add_argument("--show", default=None, help="Path to authored show YAML")
    p_run_mpv.add_argument("--duration", "-d", type=float, default=None, help="Duration in seconds")
    p_run_mpv.add_argument("--max-frames", "-n", type=int, default=None, help="Max output frames")

    p_validate_show = subparsers.add_parser("validate-show", help="Validate authored show YAML")
    p_validate_show.add_argument("--show", required=True, help="Path to authored show YAML")

    p_inspect_topology = subparsers.add_parser(
        "inspect-topology",
        help="Trace validated virtual-path targets to configured nodes, outputs, and GPIOs",
    )
    p_inspect_topology.add_argument(
        "--show",
        default=None,
        help="Optional Show v2 path; otherwise inspect layout.virtual_paths",
    )

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
    elif args.command == "validate-show":
        sys.exit(cmd_validate_show(args))
    elif args.command == "inspect-topology":
        sys.exit(cmd_inspect_topology(args))
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
