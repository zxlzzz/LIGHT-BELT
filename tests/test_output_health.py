"""Regression tests for output health and RGB+CCT validation bugs."""

from __future__ import annotations

import math
from collections import deque

import pytest

import light_engine.outputs.serial_output as serial_module
from light_engine.models import DigitalStrip, PixelFrame, RGBCCTColor, ZoneOutput
from light_engine.outputs import send_all
from light_engine.outputs.serial_output import SerialOutput, SerialStreamParser
from light_engine.outputs.udp_output import MAX_PIXELS_PER_PACKET, UdpOutput


def _zone_frame(zone_count: int = 1) -> PixelFrame:
    return PixelFrame(
        timestamp=0.0,
        zones=[
            ZoneOutput(
                zone_id=f"zone_{idx}",
                color=RGBCCTColor(
                    r=0.1, g=0.2, b=0.3, warm_white=0.4, cool_white=0.2
                ),
            )
            for idx in range(zone_count)
        ],
    )


def _strip_frame(pixel_count: int = 1) -> PixelFrame:
    return PixelFrame(
        timestamp=0.0,
        strips=[
            DigitalStrip(
                strip_id="strip_0",
                pixel_count=pixel_count,
                pixels=[(0.1, 0.2, 0.3)] * pixel_count,
            )
        ],
    )


class RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        return len(data)


def _enabled_udp_output() -> tuple[UdpOutput, RecordingSocket]:
    sock = RecordingSocket()
    output = UdpOutput(host="127.0.0.1", port=9001)
    output._open = True
    output._enabled = True
    output._socket = sock
    return output, sock


def _memory_serial_output() -> SerialOutput:
    output = SerialOutput()
    output._open = True
    output._running = True
    output._use_memory = True
    output._memory_transport = bytearray()
    output._parser = SerialStreamParser()
    return output


def test_udp_unopened_health_drop_does_not_call_health_as_function() -> None:
    output = UdpOutput()

    output.send_frame(_strip_frame())

    health = output.health()
    assert health.frames_dropped == 1
    assert health.frames_sent == 0
    assert health.packets_sent == 0


def test_udp_health_counts_one_logical_frame_and_multiple_packets() -> None:
    output, sock = _enabled_udp_output()

    output.send_frame(_strip_frame(MAX_PIXELS_PER_PACKET + 1))

    health = output.health()
    assert health.frames_sent == 1
    assert health.packets_sent == 2
    assert health.frames_dropped == 0
    assert len(sock.sent) == 2


def test_send_all_does_not_double_count_udp_backend_health() -> None:
    output, sock = _enabled_udp_output()

    send_all({"udp": output}, _strip_frame())

    health = output.health()
    assert health.frames_sent == 1
    assert health.packets_sent == 1
    assert health.frames_dropped == 0
    assert len(sock.sent) == 1


def test_serial_send_frame_queue_drop_does_not_call_health_as_function() -> None:
    output = _memory_serial_output()
    output._write_queue = deque(maxlen=1)

    output.send_frame(_zone_frame(zone_count=2))

    health = output.health()
    assert health.frames_sent == 0
    assert health.frames_dropped == 1
    assert health.packets_sent == 0
    assert len(output._write_queue) == 0


def test_serial_counts_complete_logical_frame_when_queue_can_hold_all_packets() -> None:
    output = _memory_serial_output()
    output._write_queue = deque(maxlen=2)

    output.send_frame(_zone_frame(zone_count=2))

    health = output.health()
    assert health.frames_sent == 1
    assert health.frames_dropped == 0
    assert health.packets_sent == 0
    assert len(output._write_queue) == 2


def test_serial_writer_updates_packet_health_without_type_error(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _memory_serial_output()
    output._write_queue = deque(maxlen=2)
    output.send_frame(_zone_frame(zone_count=2))

    def stop_after_iteration(_seconds: float) -> None:
        output._running = False

    monkeypatch.setattr(serial_module.time, "sleep", stop_after_iteration)

    output._writer_loop()

    health = output.health()
    assert health.frames_sent == 1
    assert health.packets_sent == 2
    assert health.frames_dropped == 0
    assert output.get_memory_bytes()


def test_serial_encode_failure_does_not_count_complete_logical_frame() -> None:
    class BadColor:
        def to_uint8(self) -> dict[str, int]:
            raise ValueError("bad color")

    output = _memory_serial_output()
    frame = PixelFrame(
        timestamp=0.0,
        zones=[
            ZoneOutput(
                zone_id="ok",
                color=RGBCCTColor(r=0.1, g=0.2, b=0.3, warm_white=0.4),
            ),
            ZoneOutput(zone_id="bad", color=BadColor()),  # type: ignore[arg-type]
        ],
    )

    output.send_frame(frame)

    health = output.health()
    assert health.frames_sent == 0
    assert health.frames_dropped == 1
    assert health.packets_sent == 0
    assert len(output._write_queue) == 0


@pytest.mark.parametrize("channel", ["r", "g", "b", "warm_white", "cool_white"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_rgbcct_color_rejects_non_finite_channels(channel: str, value: float) -> None:
    kwargs = {
        "r": 0.1,
        "g": 0.2,
        "b": 0.3,
        "warm_white": 0.4,
        "cool_white": 0.2,
    }
    kwargs[channel] = value

    with pytest.raises(ValueError, match=channel):
        RGBCCTColor(**kwargs)


@pytest.mark.parametrize("channel", ["r", "g", "b", "warm_white", "cool_white"])
@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_rgbcct_color_rejects_out_of_range_channels(channel: str, value: float) -> None:
    kwargs = {
        "r": 0.1,
        "g": 0.2,
        "b": 0.3,
        "warm_white": 0.4,
        "cool_white": 0.2,
    }
    kwargs[channel] = value

    with pytest.raises(ValueError, match=channel):
        RGBCCTColor(**kwargs)


def test_rgbcct_color_preserves_valid_channels_individually() -> None:
    color = RGBCCTColor(r=0.1, g=0.2, b=0.3, warm_white=0.4, cool_white=0.2)

    assert color.r == 0.1
    assert color.g == 0.2
    assert color.b == 0.3
    assert color.warm_white == 0.4
    assert color.cool_white == 0.2
