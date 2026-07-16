"""UDP v3 scheduled-apply clock and Host transport tests."""

from __future__ import annotations

import socket

import pytest

from light_engine.mapping.physical import (
    DigitalNodeFrame,
    DigitalOutputFrame,
    PhysicalFrame,
)
from light_engine.outputs import OutputMode
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import (
    CLOCK_BEACON_LENGTH,
    FLAG_SCHEDULED_APPLY,
    MESSAGE_TYPE_CLOCK_BEACON,
    UdpV3ClockBeacon,
    UdpV3Packet,
)


class ManualClock:
    def __init__(self, now_us: int = 1_000_000) -> None:
        self.now_us = now_us
        self.reads = 0
        self.sleep_calls: list[float] = []

    def __call__(self) -> int:
        self.reads += 1
        return self.now_us

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now_us += round(seconds * 1_000_000)

    def advance(self, microseconds: int) -> None:
        self.now_us += microseconds


class RecordingSocket:
    def __init__(self) -> None:
        self.options: list[tuple[int, int, int]] = []
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        return len(data)


def _frame(sequence: int = 1, *, apply_at_us: int | None = None) -> PhysicalFrame:
    metadata = {} if apply_at_us is None else {"apply_at_us": apply_at_us}
    return PhysicalFrame(
        sequence=sequence,
        timestamp=(sequence - 1) / 30.0,
        metadata=metadata,
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
                        pixels=[(node_id / 10.0, 0.0, 0.0)],
                    )
                ],
            )
            for node_id in (2, 8)
        ],
    )


def test_clock_beacon_is_fixed_length_crc_protected_and_has_no_node_payload() -> None:
    beacon = UdpV3ClockBeacon(
        sequence=0x01020304,
        host_monotonic_us=1_234_567,
    )
    encoded = beacon.encode()

    assert len(encoded) == CLOCK_BEACON_LENGTH == 20
    assert encoded[:4] == bytes.fromhex("4c450302")
    assert encoded[4:8] == bytes.fromhex("01020304")
    assert encoded[8:16] == (1_234_567).to_bytes(8, "big")
    assert UdpV3ClockBeacon.decode(encoded) == beacon
    assert UdpV3Packet.decode(encoded) is None

    corrupt = bytearray(encoded)
    corrupt[10] ^= 1
    assert UdpV3ClockBeacon.decode(bytes(corrupt)) is None
    assert UdpV3ClockBeacon.decode(encoded + b"\x00") is None


def test_clock_beacon_rejects_wrong_type_and_non_uint_fields() -> None:
    with pytest.raises(ValueError, match="unsupported message_type"):
        UdpV3ClockBeacon(
            sequence=1,
            host_monotonic_us=2,
            message_type=MESSAGE_TYPE_CLOCK_BEACON + 1,
        )
    with pytest.raises(ValueError, match="sequence"):
        UdpV3ClockBeacon(sequence=True, host_monotonic_us=2)
    with pytest.raises(ValueError, match="host_monotonic_us"):
        UdpV3ClockBeacon(sequence=1, host_monotonic_us=-1)


def test_default_transport_stays_immediate_and_does_not_read_clock() -> None:
    def unexpected_clock_read() -> int:
        raise AssertionError("immediate mode must not read the scheduling clock")

    output = UdpOutputV3(monotonic_us=unexpected_clock_read)
    output.open()
    output.send_frame(_frame())

    datagrams = output.get_sent_datagrams()
    assert len(datagrams) == 2
    packets = [UdpV3Packet.decode(raw) for raw, _address in datagrams]
    assert all(packet is not None for packet in packets)
    assert all(packet.apply_at_us is None for packet in packets)
    assert all(not packet.flags & FLAG_SCHEDULED_APPLY for packet in packets)


def test_explicit_legacy_frame_apply_time_gets_matching_flag_without_beacon() -> None:
    output = UdpOutputV3()
    output.open()
    output.send_frame(_frame(apply_at_us=9_000_000))

    datagrams = output.get_sent_datagrams()
    assert len(datagrams) == 2
    packets = [UdpV3Packet.decode(raw) for raw, _address in datagrams]
    assert all(packet is not None for packet in packets)
    assert {packet.apply_at_us for packet in packets} == {9_000_000}
    assert all(packet.flags & FLAG_SCHEDULED_APPLY for packet in packets)


def test_scheduled_transport_sends_startup_burst_and_one_apply_time_per_frame() -> None:
    clock = ManualClock()
    output = UdpOutputV3(
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
    )
    output.open()

    startup = output.get_sent_datagrams()
    assert len(startup) == 5
    assert {address for _raw, address in startup} == {("255.255.255.255", 9001)}
    beacons = [UdpV3ClockBeacon.decode(raw) for raw, _address in startup]
    assert all(beacon is not None for beacon in beacons)
    assert [beacon.sequence for beacon in beacons] == [1, 2, 3, 4, 5]
    assert [beacon.host_monotonic_us for beacon in beacons] == [
        1_000_000,
        1_010_000,
        1_020_000,
        1_030_000,
        1_040_000,
    ]
    assert clock.sleep_calls == [0.01, 0.01, 0.01, 0.01, 0.01]

    output.send_frame(_frame())
    frame_datagrams = output.get_sent_datagrams()[5:]
    frame_packets = [UdpV3Packet.decode(raw) for raw, _address in frame_datagrams]
    assert len(frame_datagrams) == 6
    assert all(packet is not None for packet in frame_packets)
    assert {packet.apply_at_us for packet in frame_packets} == {1_070_000}
    assert all(packet.flags & FLAG_SCHEDULED_APPLY for packet in frame_packets)
    assert [raw for raw, _address in frame_datagrams[:2]] == [
        raw for raw, _address in frame_datagrams[2:4]
    ] == [raw for raw, _address in frame_datagrams[4:6]]
    assert clock.sleep_calls == [0.01, 0.01, 0.01, 0.01, 0.01, 0.002, 0.002]
    assert output.health().packets_sent == 11
    assert output.health().logical_frames_sent == 1


def test_scheduled_transport_can_unicast_each_beacon_round_to_all_nodes() -> None:
    clock = ManualClock()
    addresses = (("192.0.2.2", 9001), ("192.0.2.8", 9001))
    output = UdpOutputV3(
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
        beacon_addresses=addresses,
        startup_beacons=3,
        startup_beacon_spacing_us=100_000,
    )
    output.open()

    startup = output.get_sent_datagrams()
    assert len(startup) == 6
    assert [address for _raw, address in startup] == [
        addresses[0],
        addresses[1],
        addresses[0],
        addresses[1],
        addresses[0],
        addresses[1],
    ]
    beacons = [UdpV3ClockBeacon.decode(raw) for raw, _address in startup]
    assert all(beacon is not None for beacon in beacons)
    assert [beacon.sequence for beacon in beacons] == [1, 1, 2, 2, 3, 3]
    assert [beacon.host_monotonic_us for beacon in beacons] == [
        1_000_000,
        1_000_000,
        1_100_000,
        1_100_000,
        1_200_000,
        1_200_000,
    ]
    assert output.capabilities()["clock_beacon_targets"] == 2
    assert output.health().packets_sent == 6


def test_periodic_beacon_uses_same_clock_sample_as_scheduled_frame() -> None:
    clock = ManualClock(10_000_000)
    output = UdpOutputV3(
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
        startup_beacons=1,
        beacon_interval_us=500_000,
    )
    output.open()
    output.send_frame(_frame(sequence=1))
    # The startup settle already advanced 10 ms after the last beacon.
    clock.advance(485_999)
    output.send_frame(_frame(sequence=2))
    clock.advance(1)
    output.send_frame(_frame(sequence=3))

    datagrams = output.get_sent_datagrams()
    assert len(datagrams) == 12
    periodic = UdpV3ClockBeacon.decode(datagrams[9][0])
    assert periodic is not None
    assert periodic.sequence == 2
    assert periodic.host_monotonic_us == 10_500_000
    sequence_three = [
        UdpV3Packet.decode(raw)
        for raw, _address in datagrams[10:]
    ]
    assert all(packet is not None for packet in sequence_three)
    assert {packet.sequence for packet in sequence_three} == {3}
    assert {packet.apply_at_us for packet in sequence_three} == {10_520_000}
    assert clock.reads == 4  # One startup sample, then exactly one per frame.


def test_reopen_resets_beacon_sequence_and_clock_epoch_state() -> None:
    clock = ManualClock()
    output = UdpOutputV3(
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
        startup_beacons=1,
    )
    output.open()
    first = UdpV3ClockBeacon.decode(output.get_sent_datagrams()[-1][0])
    assert first is not None and first.sequence == 1

    output.close()
    clock.advance(5_000_000)
    output.open()
    reopened = UdpV3ClockBeacon.decode(output.get_sent_datagrams()[-1][0])
    assert reopened is not None
    assert reopened.sequence == 1
    assert reopened.host_monotonic_us == 6_010_000


def test_scheduled_transport_owns_apply_time_and_rejects_clock_regression() -> None:
    clock = ManualClock()
    output = UdpOutputV3(
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
        startup_beacons=1,
    )
    output.open()
    with pytest.raises(ValueError, match="owns apply_at_us"):
        output.send_frame(_frame(apply_at_us=2_000_000))

    clock.now_us = 999_999
    with pytest.raises(ValueError, match="must not move backwards"):
        output.send_frame(_frame(sequence=2))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"scheduled_apply": 1}, "scheduled_apply"),
        ({"lead_us": 0}, "lead_us"),
        ({"lead_us": 100_001}, "lead_us"),
        ({"session_start_repeats": 1}, "session_start_repeats"),
        ({"session_start_repeats": 11}, "session_start_repeats"),
        ({"session_start_spacing_us": -1}, "session_start_spacing_us"),
        ({"session_start_spacing_us": 10_001}, "session_start_spacing_us"),
        ({"beacon_interval_us": 0}, "beacon_interval_us"),
        ({"startup_beacons": 0}, "startup_beacons"),
        ({"startup_beacon_spacing_us": -1}, "startup_beacon_spacing_us"),
        ({"beacon_address": ("", 9001)}, "beacon_address"),
        ({"beacon_address": ("host", 0)}, "port"),
        ({"beacon_addresses": ()}, "beacon_addresses"),
        ({"beacon_addresses": (("host", 9001), ("host", 9001))}, "unique"),
        ({"monotonic_us": 123}, "monotonic_us"),
        ({"sleep_s": 123}, "sleep_s"),
    ],
)
def test_scheduling_constructor_rejects_ambiguous_or_unsafe_values(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        UdpOutputV3(**kwargs)


def test_production_scheduled_transport_enables_broadcast_on_injected_socket() -> None:
    clock = ManualClock()
    transport = RecordingSocket()
    output = UdpOutputV3(
        mode=OutputMode.PRODUCTION,
        socket=transport,
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
        startup_beacons=1,
    )
    output.open()

    assert transport.options == [(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)]
    assert len(transport.sent) == 1
    assert UdpV3ClockBeacon.decode(transport.sent[0][0]) is not None


def test_all_nodes_are_encoded_before_any_session_start_datagram_is_sent() -> None:
    clock = ManualClock()
    output = UdpOutputV3(
        scheduled_apply=True,
        monotonic_us=clock,
        sleep_s=clock.sleep,
    )
    output.open()
    startup_count = len(output.get_sent_datagrams())
    frame = _frame()
    frame.digital_frames[1].outputs[0].pixels[0] = (2.0, 0.0, 0.0)

    output.send_frame(frame)

    assert len(output.get_sent_datagrams()) == startup_count
    assert output.health().logical_frames_sent == 0
    assert output.health().frames_dropped == 1
