"""Exact Host/UDP contract for the 120-second Gate 1m show."""

import math
from itertools import groupby
from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import FLAG_KEY_FRAME, FLAG_SAFE_STATE, UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-emergency-node2-strip41.yaml")
SHOW = Path("config/shows/ws2811-emergency-node2-strip41-gate1m-120s.yaml")
FPS = 5.0
TOTAL_PACKETS = 600
RENDER_FRAMES = TOTAL_PACKETS - 1
SAFE_SEQUENCE = TOTAL_PACKETS
BLACK = (0, 0, 0)
BLUE20 = (0, 0, 0x20)
GREEN20 = (0, 0x20, 0)
ORANGE20_08 = (0x20, 0x08, 0)


def _dot_payload(position: int, color: tuple[int, int, int]) -> tuple:
    pixels = [BLACK] * 10
    pixels[1 + position] = color
    return tuple(pixels)


def _theater_payload(phase: int) -> tuple[tuple[int, int, int], ...]:
    pixels = [BLACK] * 10
    for path_index in range(9):
        if path_index % 3 == phase:
            pixels[1 + path_index] = BLUE20
    return tuple(pixels)


def _expected_payload(timestamp: float) -> tuple[tuple[int, int, int], ...]:
    if 5.0 <= timestamp < 25.0:
        step = math.floor((timestamp - 5.0) * 2.5 + 1e-9)
        return _dot_payload(step % 9, BLUE20)
    if 30.0 <= timestamp < 50.0:
        phase = math.floor((timestamp - 30.0) * 2.5 + 1e-9) % 3
        return _theater_payload(phase)
    if 55.0 <= timestamp < 60.0:
        return (BLACK,) + (GREEN20,) * 9
    if 65.0 <= timestamp < 85.0:
        step = math.floor((timestamp - 65.0) * 2.5 + 1e-9)
        return _dot_payload(step % 9, GREEN20)
    if 90.0 <= timestamp < 110.0:
        step = math.floor((timestamp - 90.0) * 2.5 + 1e-9)
        return _dot_payload(step % 9, ORANGE20_08)
    return (BLACK,) * 10


def _decode(raw: bytes) -> UdpV3Packet:
    packet = UdpV3Packet.decode(
        raw,
        expected_node_id=2,
        expected_outputs={1: (4, 10)},
    )
    assert packet is not None
    return packet


def _render_session() -> tuple[UdpOutputV3, list[tuple[bytes, tuple[str, int]]]]:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
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
        assert show.duration == 120.0
        for index in range(RENDER_FRAMES):
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

        safe = OutputTransform.generate_safe_frame(
            timestamp=120.0,
            sequence=SAFE_SEQUENCE,
            zone_ids=[zone.id for zone in layout.zones],
            strips=[
                {"id": strip.id, "pixel_count": strip.pixel_count}
                for strip in layout.strips
            ],
        )
        output.send_frame(mapping.map(safe))
        return output, output.get_sent_datagrams()
    finally:
        Config.reset()


def test_gate1m_renders_600_exact_frames_then_one_safe_frame() -> None:
    output, datagrams = _render_session()
    assert len(datagrams) == TOTAL_PACKETS
    for index, (raw, address) in enumerate(datagrams[:RENDER_FRAMES]):
        packet = _decode(raw)
        timestamp = (index + 1) / FPS
        assert address == ("192.168.31.202", 9001)
        assert packet.sequence == index + 1
        assert packet.outputs[0].pixels == _expected_payload(timestamp)
        assert packet.outputs[0].pixels[0] == BLACK
        assert set(packet.outputs[0].pixels) <= {
            BLACK,
            BLUE20,
            GREEN20,
            ORANGE20_08,
        }
        assert bool(packet.flags & FLAG_KEY_FRAME) is (index == 0)
        assert packet.flags & FLAG_SAFE_STATE == 0

    safe_packet = _decode(datagrams[-1][0])
    assert safe_packet.sequence == SAFE_SEQUENCE
    assert safe_packet.flags & FLAG_SAFE_STATE
    assert safe_packet.outputs[0].pixels == (BLACK,) * 10
    assert output.health().logical_frames_sent == TOTAL_PACKETS
    assert output.health().packets_sent == TOTAL_PACKETS


def test_two_independent_gate1m_sessions_emit_identical_exact_payloads() -> None:
    _, first_datagrams = _render_session()
    _, second_datagrams = _render_session()

    assert len(first_datagrams) == len(second_datagrams) == TOTAL_PACKETS
    first_payloads = []
    for first, second in zip(first_datagrams, second_datagrams, strict=True):
        first_raw, first_address = first
        second_raw, second_address = second
        first_packet = _decode(first_raw)
        second_packet = _decode(second_raw)

        assert first_address == second_address == ("192.168.31.202", 9001)
        assert first_raw == second_raw
        assert first_packet.outputs[0].pixels == second_packet.outputs[0].pixels
        first_payloads.append(first_packet.outputs[0].pixels)

    for index, payload in enumerate(first_payloads[:RENDER_FRAMES]):
        timestamp = (index + 1) / FPS
        if 5.0 <= timestamp < 25.0:
            assert GREEN20 not in payload
            assert payload.count(BLUE20) == 1
            assert set(payload) == {BLACK, BLUE20}
        if 90.0 <= timestamp < 110.0:
            assert payload.count(ORANGE20_08) == 1
            assert sum(pixel != BLACK for pixel in payload) == 1
            assert set(payload) == {BLACK, ORANGE20_08}


def test_gate1m_payload_holds_and_scene_budget_are_exact() -> None:
    payloads = [
        _expected_payload((index + 1) / FPS) for index in range(RENDER_FRAMES)
    ] + [(BLACK,) * 10]
    assert min(len(list(run)) for _, run in groupby(payloads)) >= 2

    previous = (BLACK,) * 10
    scene_transitions = 0
    identical_content = 0
    for payload in payloads:
        if payload == previous:
            identical_content += 1
        else:
            scene_transitions += 1
            previous = payload

    assert scene_transitions == 206
    assert identical_content == 394
    assert scene_transitions + 1 == 207  # Initial KEY rebuilds the cache.
    assert identical_content - 1 == 393  # Matching KEY is not deduplicated.

    theater = payloads[int(30 * FPS) : int(50 * FPS) : 2]
    assert theater[:3] == [
        _theater_payload(0),
        _theater_payload(1),
        _theater_payload(2),
    ]
    black_windows = (
        (0, 5),
        (25, 30),
        (50, 55),
        (60, 65),
        (85, 90),
        (110, 120),
    )
    for index, payload in enumerate(payloads[:RENDER_FRAMES]):
        timestamp = (index + 1) / FPS
        if any(start <= timestamp < end for start, end in black_windows):
            assert payload == (BLACK,) * 10
