"""Prepare and replay a frozen UDP trace for the strip41 breath A/B.

``prepare`` renders and validates the complete trace without opening a network
socket. ``replay`` loads that frozen file, validates it again, then sends the
stored datagrams at their recorded logical FPS. No effect or Show rendering
runs during replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import (
    FLAG_KEY_FRAME,
    FLAG_SAFE_STATE,
    FLAG_SCHEDULED_APPLY,
    UdpV3Packet,
)
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


DEFAULT_PROFILE = Path("config/profiles/ws2811-ab-node2-strip41-immediate-15fps.yaml")
DEFAULT_SHOW = Path("config/shows/ws2811-ab-strip41-blue-breath-40s.yaml")
EXPECTED_ADDRESS = ("192.168.31.202", 9001)
EXPECTED_OUTPUTS = {1: (4, 10)}
BLACK = (0, 0, 0)
TRACE_SCHEMA = 1

Datagram = tuple[bytes, tuple[str, int]]


@dataclass(frozen=True)
class TraceOracle:
    fps: float
    duration: float
    logical_frames: int
    active_frames: int
    visible_levels: tuple[int, ...]
    trace_sha256: str


def trace_sha256(datagrams: Sequence[Datagram]) -> str:
    digest = hashlib.sha256()
    for payload, address in datagrams:
        digest.update(len(payload).to_bytes(4, "big"))
        digest.update(payload)
        digest.update(address[0].encode("ascii"))
        digest.update(address[1].to_bytes(2, "big"))
    return digest.hexdigest().upper()


def validate_trace(
    datagrams: Sequence[Datagram],
    *,
    fps: float,
    duration: float,
) -> TraceOracle:
    expected_frames = int(round(fps * duration))
    if len(datagrams) != expected_frames:
        raise ValueError(
            f"trace has {len(datagrams)} frames, expected {expected_frames}"
        )

    active_frames = 0
    visible_levels: set[int] = set()
    for index, (raw, address) in enumerate(datagrams):
        sequence = index + 1
        if address != EXPECTED_ADDRESS:
            raise ValueError(f"sequence {sequence} targets {address!r}")
        packet = UdpV3Packet.decode(
            raw,
            expected_node_id=2,
            expected_outputs=EXPECTED_OUTPUTS,
        )
        if packet is None:
            raise ValueError(f"sequence {sequence} is not valid UDP v3")
        if packet.sequence != sequence:
            raise ValueError(
                f"sequence slot {sequence} contains {packet.sequence}"
            )
        if packet.flags & FLAG_SCHEDULED_APPLY:
            raise ValueError(f"sequence {sequence} is unexpectedly scheduled")
        if bool(packet.flags & FLAG_KEY_FRAME) is (sequence != 1):
            raise ValueError(f"sequence {sequence} has incorrect KEY flag")
        is_final = sequence == expected_frames
        if bool(packet.flags & FLAG_SAFE_STATE) is not is_final:
            raise ValueError(f"sequence {sequence} has incorrect SAFE flag")

        pixels = packet.outputs[0].pixels
        if len(set(pixels)) != 1:
            raise ValueError(f"sequence {sequence} is not uniform")
        timestamp = packet.media_timestamp_us / 1_000_000
        if 5.0 <= timestamp < 35.0 and not is_final:
            red, green, blue = pixels[0]
            if red != 0 or green != 0 or not 5 <= blue <= 37:
                raise ValueError(
                    f"sequence {sequence} is not allowed blue: {pixels[0]}"
                )
            active_frames += 1
            visible_levels.add(blue)
        elif pixels != (BLACK,) * 10:
            raise ValueError(f"sequence {sequence} must be black")

    levels = tuple(sorted(visible_levels))
    if active_frames != int(round(30.0 * fps)):
        raise ValueError(f"unexpected active-frame count {active_frames}")
    if fps == 15.0 and (len(levels) != 32 or levels[0] != 5 or levels[-1] != 37):
        raise ValueError(f"unexpected 15 FPS blue levels: {levels!r}")
    return TraceOracle(
        fps=fps,
        duration=duration,
        logical_frames=len(datagrams),
        active_frames=active_frames,
        visible_levels=levels,
        trace_sha256=trace_sha256(datagrams),
    )


def build_trace(profile_path: Path, show_path: Path) -> tuple[list[Datagram], TraceOracle]:
    Config.reset()
    try:
        config = Config.get_instance(profile_path)
        fps = float(config.get("system.output_fps"))
        if config.get("outputs.udp_v3.presentation.mode") != "immediate":
            raise ValueError("trace preparation requires Immediate presentation")
        layout = Layout.from_config(config)
        show = load_show(show_path, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=config.get("outputs.transform.power_limit"),
        )
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3(mode="memory")
        output.open()
        logical_frames = int(round(show.duration * fps))
        for index in range(logical_frames - 1):
            timestamp = (index + 1) / fps
            sequence = index + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))

        safe = OutputTransform.generate_safe_frame(
            timestamp=show.duration,
            sequence=logical_frames,
            zone_ids=[zone.id for zone in layout.zones],
            strips=[
                {"id": strip.id, "pixel_count": strip.pixel_count}
                for strip in layout.strips
            ],
        )
        output.send_frame(mapping.map(safe))
        datagrams = output.get_sent_datagrams()
        oracle = validate_trace(datagrams, fps=fps, duration=show.duration)
        return datagrams, oracle
    finally:
        Config.reset()


def write_trace(
    path: Path,
    datagrams: Sequence[Datagram],
    oracle: TraceOracle,
) -> None:
    document = {
        "schema": TRACE_SCHEMA,
        "fps": oracle.fps,
        "duration": oracle.duration,
        "logical_frames": oracle.logical_frames,
        "active_frames": oracle.active_frames,
        "visible_levels": list(oracle.visible_levels),
        "trace_sha256": oracle.trace_sha256,
        "datagrams": [
            {
                "host": address[0],
                "port": address[1],
                "payload_hex": payload.hex(),
            }
            for payload, address in datagrams
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="ascii")


def read_trace(path: Path) -> tuple[list[Datagram], TraceOracle]:
    document = json.loads(path.read_text(encoding="ascii"))
    if document.get("schema") != TRACE_SCHEMA:
        raise ValueError("unsupported trace schema")
    datagrams = [
        (
            bytes.fromhex(item["payload_hex"]),
            (str(item["host"]), int(item["port"])),
        )
        for item in document["datagrams"]
    ]
    oracle = validate_trace(
        datagrams,
        fps=float(document["fps"]),
        duration=float(document["duration"]),
    )
    if document.get("trace_sha256") != oracle.trace_sha256:
        raise ValueError("trace SHA-256 mismatch")
    return datagrams, oracle


def replay_trace(datagrams: Sequence[Datagram], oracle: TraceOracle) -> None:
    safe_datagram = datagrams[-1]
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    start = time.perf_counter()
    try:
        for index, (payload, address) in enumerate(datagrams):
            target = start + (index + 1) / oracle.fps
            remaining = target - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            written = udp.sendto(payload, address)
            if written != len(payload):
                raise RuntimeError(
                    f"short UDP write at sequence {index + 1}: {written}"
                )
            sent += 1
            if sent % int(oracle.fps * 5) == 0:
                print(f"replay_progress frames={sent}/{len(datagrams)}", flush=True)
    finally:
        if sent and sent < len(datagrams):
            udp.sendto(*safe_datagram)
        udp.close()
    print(
        f"replay_complete frames={sent} trace_sha256={oracle.trace_sha256}",
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="render and freeze a trace")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    prepare.add_argument("--show", type=Path, default=DEFAULT_SHOW)

    replay = subparsers.add_parser("replay", help="validate and replay a trace")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the frozen trace without opening a UDP socket",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        datagrams, oracle = build_trace(args.profile, args.show)
        write_trace(args.output, datagrams, oracle)
        print(
            "trace_prepared "
            f"path={args.output} frames={oracle.logical_frames} "
            f"active_frames={oracle.active_frames} levels={len(oracle.visible_levels)} "
            f"trace_sha256={oracle.trace_sha256}"
        )
        return 0

    datagrams, oracle = read_trace(args.input)
    print(
        "trace_valid "
        f"path={args.input} frames={oracle.logical_frames} "
        f"active_frames={oracle.active_frames} levels={len(oracle.visible_levels)} "
        f"trace_sha256={oracle.trace_sha256}"
    )
    if not args.dry_run:
        replay_trace(datagrams, oracle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
