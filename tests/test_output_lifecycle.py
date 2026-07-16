"""Focused output resource-ownership and failure-accounting tests."""

from __future__ import annotations

import socket as socket_module
from collections.abc import Callable

import pytest

from light_engine.mapping.physical import (
    DigitalNodeFrame,
    DigitalOutputFrame,
    PhysicalFrame,
)
from light_engine.outputs import LightOutput, OutputMode, open_all, send_all
from light_engine.outputs.udp_output import UdpOutputV2, UdpOutputV3


class StubOutput(LightOutput):
    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        mode: OutputMode = OutputMode.MEMORY,
        open_error: Exception | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.mode = mode
        self.events = events
        self.open_error = open_error

    def open(self) -> None:
        self.events.append(f"open:{self.name}")
        if self.open_error is not None:
            raise self.open_error
        self._open = True

    def send_frame(self, _frame: PhysicalFrame) -> None:
        pass

    def close(self) -> None:
        self.events.append(f"close:{self.name}")
        self._open = False


class RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.options: list[tuple[int, int, int]] = []
        self.close_calls = 0

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        return len(data)

    def close(self) -> None:
        self.close_calls += 1


class FailingSendSocket(RecordingSocket):
    def sendto(self, _data: bytes, _address: tuple[str, int]) -> int:
        raise OSError("send failed")


class SelectiveFailSocket(RecordingSocket):
    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        if address[0] == "192.0.2.2":
            raise OSError("node 2 send failed")
        return len(data)


def _v2_frame() -> PhysicalFrame:
    return PhysicalFrame(
        sequence=1,
        timestamp=0.0,
        digital_frames=[
            DigitalNodeFrame(
                node_id=2,
                host="192.0.2.2",
                port=9001,
                pixels=[(1.0, 0.0, 0.0)],
            )
        ],
    )


def _v3_frame() -> PhysicalFrame:
    return PhysicalFrame(
        sequence=1,
        timestamp=0.0,
        digital_frames=[
            DigitalNodeFrame(
                node_id=2,
                host="192.0.2.2",
                port=9001,
                outputs=[
                    DigitalOutputFrame(
                        output_id=1,
                        gpio=4,
                        strip_id="strip_41",
                        pixels=[(1.0, 0.0, 0.0)],
                    )
                ],
            )
        ],
    )


def _v3_safe_frame() -> PhysicalFrame:
    return PhysicalFrame(
        sequence=9,
        timestamp=1.0,
        metadata={"SAFE_STATE": True},
        digital_frames=[
            DigitalNodeFrame(
                node_id=node_id,
                host=f"192.0.2.{node_id}",
                port=9001,
                outputs=[
                    DigitalOutputFrame(
                        output_id=1,
                        gpio=4,
                        strip_id=f"strip_{node_id}",
                        pixels=[(0.0, 0.0, 0.0)],
                    )
                ],
            )
            for node_id in (1, 2, 3)
        ],
    )


def test_open_all_rolls_back_every_prior_output_in_reverse_order() -> None:
    events: list[str] = []
    first = StubOutput("first", events)
    second = StubOutput("second", events)
    failing = StubOutput(
        "failing",
        events,
        mode=OutputMode.PRODUCTION,
        open_error=OSError("production open failed"),
    )

    with pytest.raises(OSError, match="production open failed"):
        open_all({"first": first, "second": second, "failing": failing})

    assert events == [
        "open:first",
        "open:second",
        "open:failing",
        "close:second",
        "close:first",
    ]
    assert not first.is_open()
    assert not second.is_open()
    assert not failing.is_open()
    assert failing.health().healthy is False
    assert failing.health().last_error == "production open failed"


def test_v3_startup_beacon_failure_closes_owned_socket_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FailingSendSocket()
    monkeypatch.setattr(socket_module, "socket", lambda *_args, **_kwargs: transport)
    output = UdpOutputV3(
        mode=OutputMode.PRODUCTION,
        scheduled_apply=True,
        monotonic_us=lambda: 1_000_000,
        startup_beacons=1,
    )

    with pytest.raises(RuntimeError, match="clock beacon startup error"):
        output.open()

    assert not output.is_open()
    assert transport.close_calls == 1
    assert output._socket is None
    assert output._owns_socket is False
    assert output.health().healthy is False
    assert output.health().packets_dropped == 1


@pytest.mark.parametrize(
    ("factory", "frame"),
    [
        (UdpOutputV2, _v2_frame),
        (UdpOutputV3, _v3_frame),
    ],
)
def test_closed_production_udp_send_raises_and_drops_exactly_one_frame(
    factory: type[UdpOutputV2],
    frame: Callable[[], PhysicalFrame],
) -> None:
    output = factory(mode=OutputMode.PRODUCTION, socket=RecordingSocket())

    with pytest.raises(RuntimeError, match="UDP output is not open"):
        output.send_frame(frame())

    assert output.health().healthy is False
    assert output.health().frames_dropped == 1
    assert output.health().packets_dropped == 0
    assert output.pending_frames() == 0


@pytest.mark.parametrize(
    ("factory", "frame"),
    [
        (UdpOutputV2, _v2_frame),
        (UdpOutputV3, _v3_frame),
    ],
)
def test_production_udp_flush_failure_counts_frame_before_reraising(
    factory: type[UdpOutputV2],
    frame: Callable[[], PhysicalFrame],
) -> None:
    output = factory(mode=OutputMode.PRODUCTION, socket=FailingSendSocket())
    output.open()

    with pytest.raises(OSError, match="send failed"):
        output.send_frame(frame())

    assert output.health().healthy is False
    assert output.health().logical_frames_sent == 0
    assert output.health().packets_dropped == 1
    assert output.health().frames_dropped == 1
    assert output.pending_frames() == 0


def test_injected_socket_is_reused_after_close_without_real_socket_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock_values = iter((1_000_000, 2_000_000, 3_000_000))
    transport = RecordingSocket()

    def unexpected_socket_factory(*_args, **_kwargs):
        raise AssertionError("reopen must not replace the injected socket")

    monkeypatch.setattr(socket_module, "socket", unexpected_socket_factory)
    output = UdpOutputV3(
        mode=OutputMode.PRODUCTION,
        socket=transport,
        scheduled_apply=True,
        monotonic_us=lambda: next(clock_values),
        beacon_interval_us=2_000_000,
        startup_beacons=1,
    )

    output.open()
    output.close()
    assert not output.is_open()
    assert output._socket is transport
    assert transport.close_calls == 0

    output.open()
    output.send_frame(_v3_frame())

    assert output.is_open()
    assert output.health().healthy is True
    assert output._socket is transport
    assert transport.close_calls == 0
    assert len(transport.options) == 2
    assert len(transport.sent) == 5  # Two startup beacons and three KEY frames.


def test_safe_frame_attempts_every_udp_node_even_after_failure() -> None:
    transport = SelectiveFailSocket()
    output = UdpOutputV3(mode=OutputMode.PRODUCTION, socket=transport)
    output.open()
    output.health().healthy = False  # Simulate the failure that ended a show.

    send_all({"udp_v3": output}, _v3_safe_frame())

    assert [address[0] for _raw, address in transport.sent] == [
        "192.0.2.1",
        "192.0.2.2",
        "192.0.2.3",
    ]
    assert output.health().logical_frames_submitted == 1
    assert output.health().logical_frames_sent == 0
    assert output.health().frames_dropped == 1
    assert output.health().packets_sent == 2
    assert output.health().packets_dropped == 1
