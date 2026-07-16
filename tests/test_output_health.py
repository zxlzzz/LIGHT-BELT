"""Tests for Phase 6 output health accounting."""

from __future__ import annotations

import json

import pytest

from light_engine.mapping.physical import (
    AnalogNodeCommand,
    DigitalNodeFrame,
    PhysicalFrame,
)
from light_engine.models import RGBCCTColor
from light_engine.outputs import OutputMode, health_summary, send_all
from light_engine.outputs.rs485_v2 import FRAME_LENGTH, RS485v2Packet
from light_engine.outputs.serial_output import SerialOutputV2
from light_engine.outputs.udp_output import UdpOutputV2


class RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        return len(data)


class FailingSocket:
    def sendto(self, _data: bytes, _address: tuple[str, int]) -> int:
        raise OSError("send failed")


def _physical_frame(sequence: int = 7, digital_nodes: int = 1) -> PhysicalFrame:
    return PhysicalFrame(
        sequence=sequence,
        timestamp=0.25,
        analog_commands=[
            AnalogNodeCommand(
                node_id=node_id,
                zone_id=f"zone_{node_id}",
                color=RGBCCTColor(r=0.1, g=0.2, b=0.3, warm_white=0.4),
                fade_ms=10,
            )
            for node_id in range(1, 7)
        ],
        digital_frames=[
            DigitalNodeFrame(
                node_id=node_id,
                host=f"192.0.2.{node_id}",
                port=9000 + node_id,
                pixels=[(0.1, 0.2, 0.3)],
            )
            for node_id in range(1, digital_nodes + 1)
        ],
    )


def test_send_all_counts_submitted_and_backend_counts_once() -> None:
    output = UdpOutputV2(mode=OutputMode.MEMORY)
    output.open()

    send_all({"udp_v2": output}, _physical_frame(digital_nodes=2))

    health = output.health()
    assert health.logical_frames_submitted == 1
    assert health.logical_frames_sent == 1
    assert health.packets_sent == 2
    assert health.frames_dropped == 0


def test_send_all_counts_submitted_for_unhealthy_output_only() -> None:
    output = UdpOutputV2(mode=OutputMode.MEMORY)
    output.open()
    output.health().healthy = False

    send_all({"udp_v2": output}, _physical_frame())

    health = output.health()
    assert health.logical_frames_submitted == 1
    assert health.logical_frames_sent == 0
    assert health.packets_sent == 0


def test_rs485_counts_one_logical_frame_and_six_packets() -> None:
    output = SerialOutputV2(mode=OutputMode.MEMORY)
    output.open()

    output.send_frame(_physical_frame())

    raw = output.get_memory_bytes()
    assert len(raw) == FRAME_LENGTH * 6
    assert output.health().logical_frames_sent == 1
    assert output.health().packets_sent == 6
    assert output.health().frames_dropped == 0


def test_rs485_packets_for_one_frame_are_contiguous() -> None:
    output = SerialOutputV2(mode=OutputMode.MEMORY)
    output.open()

    output.send_frame(_physical_frame(sequence=513))

    raw = output.get_memory_bytes()
    packets = [
        RS485v2Packet.decode(raw[offset : offset + FRAME_LENGTH])
        for offset in range(0, len(raw), FRAME_LENGTH)
    ]
    assert [packet.node_id for packet in packets if packet is not None] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]
    assert {packet.sequence for packet in packets if packet is not None} == {1}


def test_production_udp_failure_is_reraised_and_counted() -> None:
    output = UdpOutputV2(mode=OutputMode.PRODUCTION, socket=FailingSocket())
    output.open()

    with pytest.raises(OSError, match="send failed"):
        send_all({"udp_v2": output}, _physical_frame())

    health = output.health()
    assert health.healthy is False
    assert health.logical_frames_submitted == 1
    assert health.logical_frames_sent == 0
    assert health.packets_dropped == 1
    assert "send failed" in (health.last_error or "")


def test_health_summary_is_json_serializable() -> None:
    output = UdpOutputV2(mode=OutputMode.MEMORY)
    output.open()
    send_all({"udp_v2": output}, _physical_frame())

    summary = health_summary({"udp_v2": output})

    json.dumps(summary)
    assert summary["outputs"]["udp_v2"]["healthy"] is True
    assert summary["outputs"]["udp_v2"]["logical_frames_submitted"] == 1
    assert summary["outputs"]["udp_v2"]["logical_frames_sent"] == 1
    assert summary["totals"]["packets_sent"] == 1
