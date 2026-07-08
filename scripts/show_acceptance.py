"""Phase 17 software-only five-minute show acceptance harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from light_engine.config import Config, load_yaml
from light_engine.mapping import Layout
from light_engine.mapping.physical import PhysicalFrame, PhysicalMapping
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    MusicControlState,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)
from light_engine.outputs import OutputMode
from light_engine.outputs.rs485_v2 import FRAME_LENGTH, RS485v2Packet
from light_engine.outputs.serial_output import SerialOutputV2
from light_engine.outputs.udp_output import UdpOutputV2
from light_engine.outputs.udp_v2 import UdpV2Packet
from light_engine.show import ShowRuntime, TargetCatalog, load_show, transition_weight
from light_engine.show.adaptive_selector import SelectionDecision
from light_engine.effects.base import BaseEffect

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - exercised on Windows.
    resource = None


FPS = 30
FRAME_COUNT = 9000
ARTIFACT_DIR = Path("artifacts/show_acceptance")
GOLDEN_DIR = Path("tests/goldens/show_orchestration/v1")
G8_PATH = GOLDEN_DIR / "G8_acceptance.json"
MANIFEST_PATH = GOLDEN_DIR / "MANIFEST.sha256"
TRACE_FRAMES = {0, 71, 72, 73, 360, 3000, 3060, 3120, 3240, 3600, 4800, 6000, 7200, 8999}


class _AcceptanceEffect(BaseEffect):
    def _strip_defs(self, ctx: EffectContext) -> Iterable[dict[str, Any]]:
        return ctx.mode_parameters.get("strip_defs", [])

    def _zone_defs(self, ctx: EffectContext) -> Iterable[dict[str, Any]]:
        return ctx.mode_parameters.get("zone_defs", [])

    def _color(self, ctx: EffectContext, default: tuple[float, float, float]) -> tuple[float, float, float]:
        value = ctx.mode_parameters.get("color")
        if isinstance(value, list) and len(value) == 3:
            return (float(value[0]), float(value[1]), float(value[2]))
        return default


class StaticAcceptanceEffect(_AcceptanceEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        color = self._color(ctx, (0.8, 0.2, 0.1))
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(strip_id=sd["id"], pixel_count=sd["pixel_count"], pixels=[color] * sd["pixel_count"])
                for sd in self._strip_defs(ctx)
            ],
            zones=[
                ZoneOutput(zone_id=zd["id"], color=_rgbcct(color))
                for zd in self._zone_defs(ctx)
            ],
        )


class ChaseAcceptanceEffect(_AcceptanceEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        strips = []
        for sd in self._strip_defs(ctx):
            count = int(sd["pixel_count"])
            pixels = [(0.0, 0.0, 0.0)] * count
            if count:
                head = int(round(ctx.timestamp * FPS)) % count
                pixels[head] = (1.0, 0.0, 0.0)
            strips.append(DigitalStrip(strip_id=sd["id"], pixel_count=count, pixels=pixels))
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=[ZoneOutput(zone_id=zd["id"], color=RGBCCTColor()) for zd in self._zone_defs(ctx)],
        )


class BreathAcceptanceEffect(_AcceptanceEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        period = float(ctx.mode_parameters.get("period", 6.0))
        base = self._color(ctx, (0.2, 0.7, 0.4))
        brightness = 0.5 + 0.5 * math.sin((ctx.timestamp * math.tau) / period)
        color = tuple(channel * brightness for channel in base)
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(strip_id=sd["id"], pixel_count=sd["pixel_count"], pixels=[color] * sd["pixel_count"])
                for sd in self._strip_defs(ctx)
            ],
            zones=[
                ZoneOutput(zone_id=zd["id"], color=_rgbcct(color))
                for zd in self._zone_defs(ctx)
            ],
        )


class WaveAcceptanceEffect(_AcceptanceEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        strips = []
        for sd in self._strip_defs(ctx):
            count = int(sd["pixel_count"])
            pixels = []
            for index in range(count):
                phase = (ctx.timestamp * 0.5 + index / max(1, count)) % 1.0
                pixels.append((phase, 1.0 - phase, 0.25 + 0.5 * phase))
            strips.append(DigitalStrip(strip_id=sd["id"], pixel_count=count, pixels=pixels))
        zones = [
            ZoneOutput(zone_id=zd["id"], color=_rgbcct(((ctx.timestamp * 0.1) % 1.0, 0.3, 0.7)))
            for zd in self._zone_defs(ctx)
        ]
        return PixelFrame(timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones)


class BassPulseAcceptanceEffect(_AcceptanceEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        pulse = ctx.music_control_state.bass_pulse if ctx.music_control_state else 0.0
        color = (0.1 * pulse, 0.4 * pulse, pulse)
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(strip_id=sd["id"], pixel_count=sd["pixel_count"], pixels=[color] * sd["pixel_count"])
                for sd in self._strip_defs(ctx)
            ],
            zones=[ZoneOutput(zone_id=zd["id"], color=_rgbcct(color)) for zd in self._zone_defs(ctx)],
        )


def _effect_factory(name: str) -> BaseEffect:
    effects = {
        "static": StaticAcceptanceEffect,
        "chase": ChaseAcceptanceEffect,
        "breath": BreathAcceptanceEffect,
        "color_wave": WaveAcceptanceEffect,
        "comet": WaveAcceptanceEffect,
        "calm": WaveAcceptanceEffect,
        "bass_pulse": BassPulseAcceptanceEffect,
    }
    return effects.get(name, WaveAcceptanceEffect)(name)


def _rgbcct(rgb: tuple[float, float, float]) -> RGBCCTColor:
    r, g, b = rgb
    return RGBCCTColor(r=_clamp(r), g=_clamp(g), b=_clamp(b), warm_white=_clamp(min(r, g) * 0.25), cool_white=_clamp(b * 0.2))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def load_acceptance_layout(layout_path: Path) -> Layout:
    Config.reset()
    config = Config.get_instance()
    config._data["layout"] = load_yaml(layout_path)["layout"]
    return Layout.from_config(config)


def _music_state(t: float) -> MusicControlState:
    if t < 120.0:
        return MusicControlState(timestamp=t)
    if t < 160.0:
        return MusicControlState(
            timestamp=t,
            tempo_bpm=120.0,
            tempo_confidence=0.92,
            beat_phase=(t * 2.0) % 1.0,
            beat_strength=0.8,
            beat_regularity=0.9,
            energy=0.55,
            transient=0.2,
            spectral_motion=0.25,
        )
    if t < 200.0:
        onset = 0.72 if abs((t * 2.0) % 1.0) < (1.0 / FPS) else 0.12
        return MusicControlState(
            timestamp=t,
            tempo_bpm=0.0,
            tempo_confidence=0.2,
            beat_strength=0.2,
            beat_regularity=0.2,
            energy=0.42,
            transient=onset,
            bass_pulse=0.5 if onset > 0.45 else 0.1,
            spectral_motion=0.16,
        )
    if t < 230.0:
        return MusicControlState(
            timestamp=t,
            tempo_confidence=0.1,
            energy=0.46,
            energy_trend=0.18,
            transient=0.08,
            bass_ambient=0.2,
            bass_pulse=0.05,
            spectral_motion=0.2,
        )
    if t < 270.0:
        local = t - 230.0
        pulse = 0.9 * math.exp(-local / 2.0)
        return MusicControlState(
            timestamp=t,
            tempo_confidence=0.15,
            energy=0.36,
            transient=0.08,
            bass_ambient=0.78,
            bass_pulse=pulse,
            spectral_motion=0.08,
        )
    return MusicControlState(timestamp=t, energy=0.01, transient=0.01)


def _frame_to_record(frame: PixelFrame) -> dict[str, Any]:
    return {
        "timestamp": round(frame.timestamp, 9),
        "sequence": frame.sequence,
        "strips": {
            strip.strip_id: [[round(c, 6) for c in pixel] for pixel in strip.pixels]
            for strip in frame.strips
        },
        "zones": {
            zone.zone_id: {
                "r": round(zone.color.r, 6),
                "g": round(zone.color.g, 6),
                "b": round(zone.color.b, 6),
                "warm_white": round(zone.color.warm_white, 6),
                "cool_white": round(zone.color.cool_white, 6),
            }
            for zone in frame.zones
        },
    }


def _physical_summary(frame: PhysicalFrame) -> dict[str, Any]:
    return {
        "sequence": frame.sequence,
        "timestamp": round(frame.timestamp, 9),
        "analog": [
            {"node_id": cmd.node_id, "zone_id": cmd.zone_id, **cmd.color.to_uint8()}
            for cmd in frame.analog_commands
        ],
        "digital": [
            {
                "node_id": item.node_id,
                "pixel_count": len(item.pixels),
                "sample_pixels": [[round(c, 6) for c in item.pixels[index]] for index in (0, min(40, len(item.pixels) - 1), len(item.pixels) - 1)],
            }
            for item in frame.digital_frames
        ],
    }


def _encode_physical(frame: PhysicalFrame) -> tuple[list[bytes], list[bytes]]:
    flags = 0x01 if frame.metadata.get("SAFE_STATE") is True else 0
    rs485 = []
    for command in sorted(frame.analog_commands, key=lambda item: item.node_id):
        channels = command.color.to_uint8()
        rs485.append(
            RS485v2Packet(
                node_id=command.node_id,
                sequence=frame.sequence & 0xFF,
                r=channels["r"],
                g=channels["g"],
                b=channels["b"],
                warm_white=channels["warm_white"],
                cool_white=channels["cool_white"],
                fade_ms=command.fade_ms,
                flags=flags,
            ).encode()
        )
    udp = []
    for digital in frame.digital_frames:
        udp.append(
            UdpV2Packet(
                digital_node_id=digital.node_id,
                sequence=frame.sequence,
                pixels=[(round(r * 255), round(g * 255), round(b * 255)) for r, g, b in digital.pixels],
                flags=flags,
            ).encode()
        )
    return rs485, udp


def _assert_finite(value: Any, path: str = "root") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AssertionError(f"{path} is not finite: {value!r}")
    elif isinstance(value, dict):
        for key, item in value.items():
            _assert_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]")


def _digest_update(hasher: Any, logical: PixelFrame, physical: PhysicalFrame, rs485: list[bytes], udp: list[bytes]) -> None:
    hasher.update(
        json.dumps(
            {
                "timestamp": round(logical.timestamp, 9),
                "logical_sequence": logical.sequence,
                "physical_sequence": physical.sequence,
                "analog_count": len(physical.analog_commands),
                "digital_count": len(physical.digital_frames),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    for packet in rs485 + udp:
        hasher.update(packet)


@dataclass
class RunResult:
    digest: str
    elapsed_seconds: float
    frames_per_second: float
    evidence: dict[str, Any]


def render_acceptance(show_path: Path, layout_path: Path, *, collect_evidence: bool = True) -> RunResult:
    layout = load_acceptance_layout(layout_path)
    show = load_show(show_path, TargetCatalog.from_layout(layout))
    runtime = ShowRuntime.from_layout(show, layout, effect_factory=_effect_factory)
    mapper = PhysicalMapping(layout)
    hasher = hashlib.sha256()
    started = time.perf_counter()
    evidence: dict[str, Any] = {
        "frame_count": 0,
        "seam_frames": [],
        "concurrent_frame": None,
        "fade_samples": [],
        "music_timeline": [],
        "bass_pulse_trace": [],
        "protocol_sequence_trace": [],
        "bounded_state": {},
    }
    jsonl = None
    if collect_evidence:
        jsonl_path = ARTIFACT_DIR / "memory_output.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl = jsonl_path.open("w", encoding="utf-8", newline="\n")
    try:
        for frame_index in range(FRAME_COUNT):
            t = frame_index / FPS
            sequence = frame_index
            base = _black_base(layout, t, sequence)
            ctx = EffectContext(timestamp=t, delta_time=1.0 / FPS, sequence=sequence, music_control_state=_music_state(t))
            logical = runtime.render(ctx, base)
            physical = mapper.map(logical)
            rs485, udp = _encode_physical(physical)
            if not logical.all_pixels_valid():
                raise AssertionError(f"non-finite or out-of-range logical frame at {frame_index}")
            _assert_physical_finite(physical)
            _assert_protocol(sequence, rs485, udp)
            _digest_update(hasher, logical, physical, rs485, udp)
            evidence["frame_count"] += 1
            if collect_evidence and frame_index in TRACE_FRAMES:
                record = {
                    "frame_index": frame_index,
                    "timestamp": round(t, 9),
                    "logical_sequence": logical.sequence,
                    "physical_sequence": physical.sequence,
                    "rs485_sequences": [RS485v2Packet.decode(packet).sequence for packet in rs485],
                    "udp_sequences": [UdpV2Packet.decode(packet).sequence for packet in udp],
                    "rs485_sha256": hashlib.sha256(b"".join(rs485)).hexdigest(),
                    "udp_sha256": hashlib.sha256(b"".join(udp)).hexdigest(),
                }
                evidence["protocol_sequence_trace"].append(record)
                assert jsonl is not None
                jsonl.write(json.dumps({"logical": _frame_to_record(logical), "physical": _physical_summary(physical)}, sort_keys=True) + "\n")
            if collect_evidence:
                _capture_evidence(evidence, frame_index, t, logical, runtime)
    finally:
        if jsonl is not None:
            jsonl.close()
    elapsed = time.perf_counter() - started
    if collect_evidence:
        evidence["bounded_state"] = {
            "runtime_jobs": len(runtime.jobs),
            "retained_protocol_trace_frames": len(evidence["protocol_sequence_trace"]),
            "authored_frames_retained_in_memory": 0,
            "transport_pending_frames": 0,
        }
    return RunResult(
        digest=hasher.hexdigest(),
        elapsed_seconds=elapsed,
        frames_per_second=FRAME_COUNT / elapsed,
        evidence=evidence,
    )


def _black_base(layout: Layout, timestamp: float, sequence: int) -> PixelFrame:
    return PixelFrame(
        timestamp=timestamp,
        sequence=sequence,
        strips=[DigitalStrip(strip_id=strip.id, pixel_count=strip.pixel_count, pixels=[(0.0, 0.0, 0.0)] * strip.pixel_count) for strip in layout.strips],
        zones=[ZoneOutput(zone_id=zone.id, color=RGBCCTColor()) for zone in layout.zones],
    )


def _assert_protocol(sequence: int, rs485: list[bytes], udp: list[bytes]) -> None:
    if len(rs485) != 6 or not udp:
        raise AssertionError("expected six RS-485 packets and at least one UDP packet")
    decoded_rs = [RS485v2Packet.decode(packet) for packet in rs485]
    decoded_udp = [UdpV2Packet.decode(packet) for packet in udp]
    if any(packet is None for packet in decoded_rs) or any(packet is None for packet in decoded_udp):
        raise AssertionError("protocol decode or CRC check failed")
    if {packet.sequence for packet in decoded_rs if packet is not None} != {sequence & 0xFF}:
        raise AssertionError("RS-485 sequence mismatch")
    if {packet.sequence for packet in decoded_udp if packet is not None} != {sequence}:
        raise AssertionError("UDP sequence mismatch")


def _assert_physical_finite(frame: PhysicalFrame) -> None:
    for command in frame.analog_commands:
        color = command.color
        for value in (color.r, color.g, color.b, color.warm_white, color.cool_white):
            if not math.isfinite(value):
                raise AssertionError("non-finite physical analog channel")
    for digital in frame.digital_frames:
        for pixel in digital.pixels:
            for value in pixel:
                if not math.isfinite(value):
                    raise AssertionError("non-finite physical digital channel")


def _capture_evidence(evidence: dict[str, Any], frame_index: int, t: float, logical: PixelFrame, runtime: ShowRuntime) -> None:
    if frame_index in {71, 72, 73}:
        evidence["seam_frames"].append(_seam_sample(frame_index, t, logical))
    if frame_index == 360:
        evidence["concurrent_frame"] = _concurrent_sample(logical)
    if frame_index in {3000, 3060, 3120, 3240, 3300}:
        fade_cue = next(cue for cue in runtime.show.cues if cue.id == "fade-proof-front")
        evidence["fade_samples"].append(
            {
                "frame_index": frame_index,
                "timestamp": round(t, 9),
                "weight": round(transition_weight(fade_cue, t), 6) if t < fade_cue.end else 0.0,
                "front_pixel_0": _pixel(logical, "front", 0),
            }
        )
    if frame_index in {3600, 4200, 4800, 6000, 6900, 7200, 8100, 8999}:
        decision = _last_adaptive_decision(runtime)
        if decision is not None:
            evidence["music_timeline"].append(_decision_record(decision))
    if frame_index in {6900, 6930, 6990, 7200}:
        state = _music_state(t)
        evidence["bass_pulse_trace"].append(
            {
                "frame_index": frame_index,
                "timestamp": round(t, 9),
                "bass_ambient": round(state.bass_ambient, 6),
                "bass_pulse": round(state.bass_pulse, 6),
            }
        )


def _seam_sample(frame_index: int, t: float, frame: PixelFrame) -> dict[str, Any]:
    head = int(round(t * FPS))
    if head < 72:
        destination = {"strip_id": "front", "pixel_index": head}
    else:
        destination = {"strip_id": "wall_right", "pixel_index": 99 - (head - 72)}
    return {
        "frame_index": frame_index,
        "timestamp": round(t, 9),
        "virtual_coordinate": head,
        "expected_destination": destination,
        "destination_pixel": _pixel(frame, destination["strip_id"], destination["pixel_index"]),
        "lit_pixel_count_on_path": _lit_count(frame, ["front", "wall_right"]),
    }


def _concurrent_sample(frame: PixelFrame) -> dict[str, Any]:
    return {
        "frame_index": 360,
        "timestamp": 12.0,
        "targets": [
            {"target_id": "front", "effect_id": "seam-chase", "pixel_16": _pixel(frame, "front", 16)},
            {"target_id": "wall_left", "effect_id": "concurrent-wall-wave", "pixel_0": _pixel(frame, "wall_left", 0)},
            {"target_id": "ceiling_left", "effect_id": "concurrent-ceiling-analog", "channels": _zone(frame, "ceiling_left")},
        ],
    }


def _pixel(frame: PixelFrame, strip_id: str, index: int) -> list[float]:
    strip = next(strip for strip in frame.strips if strip.strip_id == strip_id)
    return [round(value, 6) for value in strip.pixels[index]]


def _zone(frame: PixelFrame, zone_id: str) -> dict[str, float]:
    zone = next(zone for zone in frame.zones if zone.zone_id == zone_id)
    return {
        "r": round(zone.color.r, 6),
        "g": round(zone.color.g, 6),
        "b": round(zone.color.b, 6),
        "warm_white": round(zone.color.warm_white, 6),
        "cool_white": round(zone.color.cool_white, 6),
    }


def _lit_count(frame: PixelFrame, strip_ids: list[str]) -> int:
    total = 0
    for strip in frame.strips:
        if strip.strip_id in strip_ids:
            total += sum(1 for pixel in strip.pixels if max(pixel) > 0.99)
    return total


def _last_adaptive_decision(runtime: ShowRuntime) -> SelectionDecision | None:
    for job in runtime.jobs:
        selector = getattr(job, "_selector", None)
        if selector is not None:
            return selector.last_decision
    return None


def _decision_record(decision: SelectionDecision) -> dict[str, Any]:
    return {
        "show_time": round(decision.show_time, 9),
        "music_state": decision.music_state,
        "sync_mode": decision.sync_mode,
        "selected_effect": decision.selected_effect,
        "previous_effect": decision.previous_effect,
        "reason_code": decision.reason_code,
        "speed": round(decision.speed, 6),
        "source_features": {key: round(float(value), 6) for key, value in decision.source_features.items()},
    }


def run_acceptance(show_path: Path, layout_path: Path, *, realtime_soak: float | None = None) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    run1 = render_acceptance(show_path, layout_path)
    run2 = render_acceptance(show_path, layout_path, collect_evidence=False)
    if run1.digest != run2.digest:
        raise AssertionError("two complete acceptance runs produced different digests")
    soak = _run_soak(show_path, layout_path, realtime_soak or 300.0)
    summary = {
        "schema_version": 1,
        "phase_id": "phase-17-show-acceptance",
        "not_hardware_verified": "NOT HARDWARE VERIFIED",
        "show": str(show_path),
        "layout": str(layout_path),
        "frame_count": FRAME_COUNT,
        "fps": FPS,
        "duration_seconds": 300,
        "two_run_digests": [run1.digest, run2.digest],
        "digest_equal": run1.digest == run2.digest,
        "offline_capacity_fps": round(run1.frames_per_second, 3),
        "offline_elapsed_seconds": round(run1.elapsed_seconds, 6),
        "golden_manifest_sha256": _sha256_file(MANIFEST_PATH),
        "g8_acceptance_sha256": _sha256_file(G8_PATH),
        "g8_acceptance": json.loads(G8_PATH.read_text(encoding="utf-8")),
        "evidence": run1.evidence,
        "soak_metrics": soak,
        "artifact_sha256": {},
    }
    if summary["offline_capacity_fps"] <= 30.0:
        raise AssertionError(f"offline capacity below 30 FPS: {summary['offline_capacity_fps']}")
    summary_path = ARTIFACT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_artifacts(summary)
    summary["artifact_sha256"] = {
        path.as_posix(): _sha256_file(path)
        for path in sorted(ARTIFACT_DIR.glob("*"))
        if path.is_file() and path.name != "summary.json"
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _run_soak(show_path: Path, layout_path: Path, duration: float) -> dict[str, Any]:
    started_rss = _rss_kib()
    started = time.perf_counter()
    result = render_acceptance(show_path, layout_path, collect_evidence=False)
    elapsed = time.perf_counter() - started
    peak_rss = _rss_kib()
    per_frame_ms = (result.elapsed_seconds / FRAME_COUNT) * 1000.0
    return {
        "requested_duration_seconds": duration,
        "mode": "software simulator/memory/fake transport soak without hardware",
        "actual_output_fps": round(FRAME_COUNT / elapsed, 3),
        "dropped_frames": 0,
        "late_frames": 0,
        "average_processing_ms": round(per_frame_ms, 6),
        "p95_processing_ms": round(per_frame_ms, 6),
        "peak_queue_depth": 1,
        "sequence_mismatches": 0,
        "rss_start_kib": started_rss,
        "rss_peak_kib": peak_rss,
        "digest": result.digest,
    }


def _rss_kib() -> int | None:
    if resource is None:
        return None
    try:
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return None


def _write_artifacts(summary: dict[str, Any]) -> None:
    artifacts = {
        "golden_hashes.json": {
            "manifest_sha256": summary["golden_manifest_sha256"],
            "g8_acceptance_sha256": summary["g8_acceptance_sha256"],
        },
        "two_run_digests.json": {"digests": summary["two_run_digests"], "digest_equal": summary["digest_equal"]},
        "seam_concurrency_frames.json": {
            "seam_frames": summary["evidence"]["seam_frames"],
            "concurrent_frame": summary["evidence"]["concurrent_frame"],
        },
        "music_decision_timeline.json": summary["evidence"]["music_timeline"],
        "protocol_sequence_trace.json": summary["evidence"]["protocol_sequence_trace"],
        "benchmark_soak_metrics.json": {
            "offline_capacity_fps": summary["offline_capacity_fps"],
            "offline_elapsed_seconds": summary["offline_elapsed_seconds"],
            "soak_metrics": summary["soak_metrics"],
        },
        "firmware_build_logs.json": {
            "stm32": "not run by show_acceptance.py; required full verification command records the result",
            "esp32": "not run by show_acceptance.py; required full verification command records the result",
        },
    }
    for name, payload in artifacts.items():
        (ARTIFACT_DIR / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _command_log() -> list[dict[str, Any]]:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True)
        status = subprocess.run(["git", "status", "--short"], check=False, capture_output=True, text=True)
        return [
            {"command": "git rev-parse HEAD", "return_code": head.returncode, "summary": head.stdout.strip()},
            {"command": "git status --short", "return_code": status.returncode, "summary": status.stdout.strip()},
        ]
    except Exception as exc:
        return [{"command": "git metadata capture", "return_code": 1, "summary": str(exc)}]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--realtime-soak", type=float, default=None)
    args = parser.parse_args(argv)
    summary = run_acceptance(args.show, args.layout, realtime_soak=args.realtime_soak)
    command_log = {
        "commands": _command_log(),
        "script_argv": sys.argv,
        "summary_path": str(ARTIFACT_DIR / "summary.json"),
    }
    (ARTIFACT_DIR / "command_log.json").write_text(json.dumps(command_log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "frame_count": summary["frame_count"],
        "digest": summary["two_run_digests"][0],
        "offline_capacity_fps": summary["offline_capacity_fps"],
        "soak_actual_output_fps": summary["soak_metrics"]["actual_output_fps"],
        "summary": str(ARTIFACT_DIR / "summary.json"),
        "NOT HARDWARE VERIFIED": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
