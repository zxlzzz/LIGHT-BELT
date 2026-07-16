"""Phase 26 UDP v3 codec and multi-output transport tests."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from light_engine.mapping.physical import DigitalNodeFrame, DigitalOutputFrame, PhysicalFrame
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v2 import crc32
from light_engine.outputs.udp_v3 import (
    FLAG_KEY_FRAME,
    FLAG_SCHEDULED_APPLY,
    HEADER_LENGTH,
    UdpV3Output,
    UdpV3Packet,
)


GOLDEN = Path("firmware/shared/udp_v3_golden.json")


def _packet() -> UdpV3Packet:
    return UdpV3Packet(
        digital_node_id=2,
        sequence=0x01020304,
        media_timestamp_us=1_234_567,
        flags=2,
        outputs=(
            UdpV3Output(1, 4, ((1, 2, 3), (4, 5, 6))),
            UdpV3Output(2, 5, ((254, 128, 0),)),
        ),
    )


def test_golden_vector_roundtrip_preserves_independent_outputs() -> None:
    vector = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"][0]
    packet = _packet()
    assert packet.encode().hex() == vector["encoded_hex"]
    decoded = UdpV3Packet.decode(packet.encode())
    assert decoded == packet
    assert [len(output.pixels) for output in decoded.outputs] == [2, 1]
    assert HEADER_LENGTH == 29


def test_scheduled_golden_vector_preserves_shared_apply_deadline() -> None:
    vector = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"][1]
    packet = UdpV3Packet(
        digital_node_id=vector["digital_node_id"],
        sequence=vector["sequence"],
        media_timestamp_us=vector["media_timestamp_us"],
        apply_at_us=vector["apply_at_us"],
        flags=vector["flags"],
        outputs=tuple(
            UdpV3Output(
                output["output_id"],
                output["gpio"],
                tuple(tuple(pixel) for pixel in output["pixels"]),
            )
            for output in vector["outputs"]
        ),
    )

    encoded = packet.encode()

    assert encoded.hex() == vector["encoded_hex"]
    assert UdpV3Packet.decode(encoded) == packet
    assert packet.flags & FLAG_SCHEDULED_APPLY
    assert packet.apply_at_us == 987_654_321


def test_generated_shared_header_matches_authoritative_json() -> None:
    vectors = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"]
    header = Path("firmware/shared/udp_v3_golden.h").read_text(encoding="utf-8")
    for index, vector in enumerate(vectors):
        assert f"UDP_V3_GOLDEN_{index}[]" in header
        for byte in bytes.fromhex(vector["encoded_hex"]):
            assert f"0x{byte:02X}" in header


def test_apply_at_us_is_optional_and_round_trips_when_present() -> None:
    packet = UdpV3Packet(
        digital_node_id=1,
        sequence=9,
        media_timestamp_us=10,
        apply_at_us=11,
        flags=FLAG_SCHEDULED_APPLY,
        outputs=(UdpV3Output(1, 4, ((0, 0, 0),)),),
    )
    assert UdpV3Packet.decode(packet.encode()) == packet


@pytest.mark.parametrize(
    ("flags", "apply_at_us"),
    [
        (0, 11),
        (FLAG_SCHEDULED_APPLY, None),
        (FLAG_SCHEDULED_APPLY, 0),
    ],
)
def test_scheduled_flag_and_apply_time_must_be_present_together(
    flags: int, apply_at_us: int | None
) -> None:
    with pytest.raises(ValueError, match="apply_at_us|present together"):
        UdpV3Packet(
            digital_node_id=1,
            sequence=9,
            media_timestamp_us=10,
            apply_at_us=apply_at_us,
            flags=flags,
            outputs=(UdpV3Output(1, 4, ((0, 0, 0),)),),
        )


@pytest.mark.parametrize(
    ("flags", "apply_at_us"),
    [
        (0, 11),
        (FLAG_SCHEDULED_APPLY, 0),
    ],
)
def test_decoder_rejects_wire_level_scheduled_pair_mismatch(
    flags: int, apply_at_us: int
) -> None:
    raw = bytearray(_packet().encode())
    raw[5] = flags
    raw[18:26] = apply_at_us.to_bytes(8, "big")
    raw[-4:] = struct.pack(">I", crc32(bytes(raw[:-4])))
    assert UdpV3Packet.decode(bytes(raw)) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.__setitem__(-1, raw[-1] ^ 1),
        lambda raw: raw.__setitem__(0, 0),
        lambda raw: raw.__setitem__(HEADER_LENGTH - 1, 0),
    ],
)
def test_malformed_or_crc_corrupt_packets_are_rejected(mutate) -> None:
    raw = bytearray(_packet().encode())
    mutate(raw)
    assert UdpV3Packet.decode(bytes(raw)) is None


def test_duplicate_or_incomplete_outputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        UdpV3Packet(
            digital_node_id=1, sequence=1, media_timestamp_us=1,
            outputs=(UdpV3Output(1, 4, ((0, 0, 0),)), UdpV3Output(1, 5, ((0, 0, 0),))),
        )
    encoded = _packet().encode()
    assert UdpV3Packet.decode(encoded, expected_outputs={1: (4, 2)}) is None
    assert UdpV3Packet.decode(encoded, expected_outputs={1: (4, 2), 2: (6, 1)}) is None


def test_sequence_and_datagram_bounds_are_checked() -> None:
    encoded = _packet().encode()
    assert UdpV3Packet.decode(encoded, min_sequence=0x01020305) is None
    assert UdpV3Packet.decode(encoded, max_udp_payload=len(encoded) - 1) is None


def test_output_length_mismatch_is_rejected_after_repaired_crc() -> None:
    raw = bytearray(_packet().encode())
    # First descriptor's output_length is the final u16 of the descriptor.
    descriptor_offset = HEADER_LENGTH
    raw[descriptor_offset + 5] = 5
    raw[-4:] = struct.pack(">I", crc32(bytes(raw[:-4])))
    assert UdpV3Packet.decode(bytes(raw)) is None


def test_non_frame_message_type_is_rejected_after_repaired_crc() -> None:
    raw = bytearray(_packet().encode())
    raw[3] = 2  # message type follows magic and version
    raw[-4:] = struct.pack(">I", crc32(bytes(raw[:-4])))
    assert UdpV3Packet.decode(bytes(raw)) is None
    with pytest.raises(ValueError, match="unsupported message_type"):
        UdpV3Packet(
            digital_node_id=1,
            sequence=1,
            media_timestamp_us=1,
            message_type=2,
            outputs=(UdpV3Output(1, 4, ((0, 0, 0),)),),
        )


def test_transport_sends_one_packet_per_node_without_concatenating_outputs() -> None:
    frame = PhysicalFrame(
        sequence=42,
        timestamp=3.5,
        digital_frames=[
            DigitalNodeFrame(
                node_id=2,
                host="192.0.2.2",
                port=9001,
                outputs=[
                    DigitalOutputFrame(1, 4, "strip_41", [(1.0, 0.0, 0.0)]),
                    DigitalOutputFrame(2, 5, "strip_42", [(0.0, 1.0, 0.0)] * 2),
                    DigitalOutputFrame(3, 6, "strip_43", [(0.0, 0.0, 1.0)] * 3),
                ],
            )
        ],
    )
    output = UdpOutputV3()
    output.open()
    output.send_frame(frame)
    sent = output.get_sent_datagrams()
    assert len(sent) == 1
    decoded = UdpV3Packet.decode(sent[0][0], expected_outputs={1: (4, 1), 2: (5, 2), 3: (6, 3)})
    assert decoded is not None
    assert decoded.sequence == frame.sequence
    assert decoded.media_timestamp_us == 3_500_000
    assert [len(item.pixels) for item in decoded.outputs] == [1, 2, 3]


def test_transport_marks_only_sequence_one_as_new_session_key_frame() -> None:
    output = UdpOutputV3()
    output.open()

    for sequence in (1, 2):
        output.send_frame(
            PhysicalFrame(
                sequence=sequence,
                timestamp=(sequence - 1) / 30.0,
                digital_frames=[
                    DigitalNodeFrame(
                        node_id=2,
                        host="192.0.2.2",
                        port=9001,
                        outputs=[
                            DigitalOutputFrame(
                                1, 4, "strip_41", [(1.0, 0.0, 0.0)]
                            )
                        ],
                    )
                ],
            )
        )

    packets = [UdpV3Packet.decode(raw) for raw, _address in output.get_sent_datagrams()]
    assert all(packet is not None for packet in packets)
    assert packets[0].flags & FLAG_KEY_FRAME
    assert not packets[1].flags & FLAG_KEY_FRAME


def test_transport_refuses_legacy_concatenated_node_frame() -> None:
    output = UdpOutputV3()
    output.open()
    output.send_frame(PhysicalFrame(
        sequence=1, timestamp=0.0,
        digital_frames=[DigitalNodeFrame(2, "192.0.2.2", 9001, pixels=[(0.0, 0.0, 0.0)])],
    ))
    assert output.get_sent_datagrams() == []
    assert output.health().frames_dropped == 1
