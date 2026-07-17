"""Exact UDP contracts for Node8 and staged Node2+Node8 emergency shows."""

import math
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

import pytest

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import FLAG_KEY_FRAME, FLAG_SAFE_STATE, UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


FPS = 5.0
BLACK = (0, 0, 0)
BLUE20 = (0, 0, 0x20)
GREEN20 = (0, 0x20, 0)


@dataclass(frozen=True)
class NodeSpec:
    node_id: int
    host: str
    pixel_count: int
    active_windows: tuple[tuple[float, float], ...]
    fill_color: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class Case:
    id: str
    profile: Path
    show: Path
    duration: float
    nodes: tuple[NodeSpec, ...]
    expected_logical_frames: int
    expected_packets: int
    expected_scene_transitions: int
    expected_physical_writes: int
    expected_identical_skipped: int

    @property
    def render_frames(self) -> int:
        return int(self.duration * FPS) - 1


CASES = (
    Case(
        id="node2_black_sentinel",
        profile=Path("config/profiles/ws2811-emergency-node2-strip41.yaml"),
        show=Path("config/shows/ws2811-emergency-black-sentinel-3s.yaml"),
        duration=3.0,
        nodes=(
            NodeSpec(
                node_id=2,
                host="192.168.31.202",
                pixel_count=10,
                active_windows=(),
            ),
        ),
        expected_logical_frames=15,
        expected_packets=15,
        expected_scene_transitions=0,
        expected_physical_writes=1,
        expected_identical_skipped=14,
    ),
    Case(
        id="node2_blue_isolation",
        profile=Path("config/profiles/ws2811-emergency-node2-strip41.yaml"),
        show=Path("config/shows/ws2811-emergency-node2-strip41-blue-60s.yaml"),
        duration=60.0,
        nodes=(
            NodeSpec(
                node_id=2,
                host="192.168.31.202",
                pixel_count=10,
                active_windows=((5.0, 45.0),),
            ),
        ),
        expected_logical_frames=300,
        expected_packets=300,
        expected_scene_transitions=101,
        expected_physical_writes=102,
        expected_identical_skipped=198,
    ),
    Case(
        id="node8",
        profile=Path("config/profiles/ws2811-emergency-node8-strip42.yaml"),
        show=Path("config/shows/ws2811-emergency-node8-strip42-blue-60s.yaml"),
        duration=60.0,
        nodes=(
            NodeSpec(
                node_id=8,
                host="192.168.31.208",
                pixel_count=20,
                active_windows=((5.0, 45.0),),
            ),
        ),
        expected_logical_frames=300,
        expected_packets=300,
        expected_scene_transitions=101,
        expected_physical_writes=102,
        expected_identical_skipped=198,
    ),
    Case(
        id="node2_node8",
        profile=Path("config/profiles/ws2811-emergency-two-node-41-42.yaml"),
        show=Path("config/shows/ws2811-emergency-two-node-blue-staged-110s.yaml"),
        duration=110.0,
        nodes=(
            NodeSpec(
                node_id=2,
                host="192.168.31.202",
                pixel_count=10,
                active_windows=((5.0, 35.0), (75.0, 105.0)),
            ),
            NodeSpec(
                node_id=8,
                host="192.168.31.208",
                pixel_count=20,
                active_windows=((40.0, 70.0), (75.0, 105.0)),
            ),
        ),
        expected_logical_frames=550,
        expected_packets=1100,
        expected_scene_transitions=152,
        expected_physical_writes=153,
        expected_identical_skipped=397,
    ),
    Case(
        id="node2_node8_green_static",
        profile=Path("config/profiles/ws2811-emergency-two-node-41-42.yaml"),
        show=Path(
            "config/shows/"
            "ws2811-emergency-two-node-green-static-staged-35s.yaml"
        ),
        duration=35.0,
        nodes=(
            NodeSpec(
                node_id=2,
                host="192.168.31.202",
                pixel_count=10,
                active_windows=((5.0, 10.0), (25.0, 30.0)),
                fill_color=GREEN20,
            ),
            NodeSpec(
                node_id=8,
                host="192.168.31.208",
                pixel_count=20,
                active_windows=((15.0, 20.0), (25.0, 30.0)),
                fill_color=GREEN20,
            ),
        ),
        expected_logical_frames=175,
        expected_packets=350,
        expected_scene_transitions=4,
        expected_physical_writes=5,
        expected_identical_skipped=170,
    ),
)


def _expected_payload(
    spec: NodeSpec,
    timestamp: float,
) -> tuple[tuple[int, int, int], ...]:
    pixels = [BLACK] * spec.pixel_count
    for start, end in spec.active_windows:
        if start <= timestamp < end:
            if spec.fill_color is not None:
                return (BLACK,) + (spec.fill_color,) * (spec.pixel_count - 1)
            usable = spec.pixel_count - 1
            step = math.floor((timestamp - start) * 2.5 + 1e-9)
            pixels[1 + step % usable] = BLUE20
            break
    return tuple(pixels)


def _decode(raw: bytes, spec: NodeSpec) -> UdpV3Packet:
    packet = UdpV3Packet.decode(
        raw,
        expected_node_id=spec.node_id,
        expected_outputs={1: (4, spec.pixel_count)},
    )
    assert packet is not None
    return packet


def _render(case: Case) -> tuple[UdpOutputV3, list]:
    config = Config.get_instance(case.profile)
    layout = Layout.from_config(config)
    show = load_show(case.show, TargetCatalog.from_layout(layout))
    runtime = ShowRuntime.from_layout(show, layout, seed=20260716)
    transform = OutputTransform(
        global_brightness=config.get("system.smoothing.max_brightness"),
        gamma=config.get("system.smoothing.gamma"),
        power_limit=config.get("outputs.transform.power_limit"),
    )
    mapping = PhysicalMapping(layout)
    output = UdpOutputV3()
    output.open()

    assert config.get("system.output_fps") == FPS
    assert config.get("outputs.udp_v3.presentation.mode") == "immediate"
    assert show.duration == case.duration
    for index in range(case.render_frames):
        timestamp = (index + 1) / FPS
        sequence = index + 1
        logical = runtime.render(
            EffectContext(
                timestamp=timestamp,
                delta_time=1.0 / FPS,
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

    safe_sequence = case.expected_logical_frames
    safe = OutputTransform.generate_safe_frame(
        timestamp=case.duration,
        sequence=safe_sequence,
        zone_ids=[zone.id for zone in layout.zones],
        strips=[
            {"id": strip.id, "pixel_count": strip.pixel_count}
            for strip in layout.strips
        ],
    )
    output.send_frame(mapping.map(safe))
    return output, output.get_sent_datagrams()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_emergency_profiles_emit_exact_per_node_udp_packets(case: Case) -> None:
    Config.reset()
    try:
        output, datagrams = _render(case)
        logical_frames = case.expected_logical_frames
        packets_per_frame = len(case.nodes)
        assert logical_frames == case.expected_logical_frames
        assert len(datagrams) == case.expected_packets
        assert len(datagrams) == logical_frames * packets_per_frame

        specs_by_address = {
            (spec.host, 9001): spec
            for spec in case.nodes
        }
        for logical_index in range(logical_frames):
            sequence = logical_index + 1
            start = logical_index * packets_per_frame
            chunk = datagrams[start : start + packets_per_frame]
            packets_by_node = {}
            for raw, address in chunk:
                assert address in specs_by_address
                spec = specs_by_address[address]
                packet = _decode(raw, spec)
                packets_by_node[spec.node_id] = packet

                assert packet.sequence == sequence
                assert packet.outputs[0].pixels[0] == BLACK
                if sequence <= case.render_frames:
                    timestamp = (logical_index + 1) / FPS
                    assert packet.outputs[0].pixels == _expected_payload(
                        spec, timestamp
                    )
                    assert bool(packet.flags & FLAG_KEY_FRAME) is (sequence == 1)
                    assert packet.flags & FLAG_SAFE_STATE == 0
                else:
                    assert packet.flags & FLAG_SAFE_STATE
                    assert packet.outputs[0].pixels == (BLACK,) * spec.pixel_count

            assert set(packets_by_node) == {spec.node_id for spec in case.nodes}
            assert {packet.sequence for packet in packets_by_node.values()} == {
                sequence
            }
            assert len({packet.flags for packet in packets_by_node.values()}) == 1

        assert output.health().logical_frames_sent == logical_frames
        assert output.health().packets_sent == case.expected_packets
    finally:
        Config.reset()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_emergency_per_node_scene_and_skip_budgets(case: Case) -> None:
    for spec in case.nodes:
        payloads = [
            _expected_payload(spec, (index + 1) / FPS)
            for index in range(case.render_frames)
        ] + [(BLACK,) * spec.pixel_count]
        assert min(len(list(run)) for _, run in groupby(payloads)) >= 2

        previous = (BLACK,) * spec.pixel_count
        scene_transitions = 0
        identical_content = 0
        for payload in payloads:
            if payload == previous:
                identical_content += 1
            else:
                scene_transitions += 1
                previous = payload

        assert scene_transitions == case.expected_scene_transitions
        assert scene_transitions + 1 == case.expected_physical_writes
        assert identical_content - 1 == case.expected_identical_skipped
