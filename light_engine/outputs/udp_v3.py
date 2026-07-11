"""Pure UDP v3 codec for one complete multi-output ESP32 node frame.

Wire order is big-endian and deliberately self-describing::

    magic:u16 version:u8 type:u8 node:u8 flags:u8 sequence:u32
    media_timestamp_us:u64 apply_at_us:u64 output_count:u8 payload_length:u16
    repeated (output_id:u8 gpio:u8 pixel_count:u16 output_length:u16 payload)
    crc32:u32

``apply_at_us == 0`` means not scheduled in the initial release.  The codec
contains no sockets, clocks, GPIO drivers, or mutable sequence state.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from light_engine.outputs.udp_v2 import (
    ALLOWED_FLAGS,
    CRC_LENGTH,
    FLAG_KEY_FRAME,
    FLAG_SAFE_STATE,
    MAX_UINT8,
    MAX_UINT16,
    MAX_UINT32,
    crc32,
)


MAGIC = 0x4C45
VERSION = 0x03
MESSAGE_TYPE_FRAME = 0x01
HEADER_FORMAT = ">HBBBBIQQBH"
HEADER_LENGTH = struct.calcsize(HEADER_FORMAT)
OUTPUT_FORMAT = ">BBHH"
OUTPUT_LENGTH = struct.calcsize(OUTPUT_FORMAT)
MAX_UINT64 = 0xFFFFFFFFFFFFFFFF
MAX_UDP_PAYLOAD = 65507


def _require_uint(name: str, value: int, maximum: int) -> None:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{name} must be an integer in [0, {maximum}], got {value!r}")


def _pixels_to_payload(pixels: Sequence[tuple[int, int, int]]) -> bytes:
    payload = bytearray()
    for pixel in pixels:
        if len(pixel) != 3:
            raise ValueError(f"pixel must contain exactly 3 channels, got {pixel!r}")
        for channel in pixel:
            _require_uint("pixel channel", channel, MAX_UINT8)
        payload.extend(pixel)
    return bytes(payload)


@dataclass(frozen=True)
class UdpV3Output:
    output_id: int
    gpio: int
    pixels: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        _require_uint("output_id", self.output_id, MAX_UINT8)
        if self.output_id == 0:
            raise ValueError("output_id must be non-zero")
        _require_uint("gpio", self.gpio, MAX_UINT8)
        if len(self.pixels) > 100:
            raise ValueError("one ESP32 output may contain at most 100 pixels")
        if len(self.pixels) > MAX_UINT16:
            raise ValueError("pixel count must fit uint16")
        payload = _pixels_to_payload(self.pixels)
        if len(payload) > MAX_UINT16:
            raise ValueError("output payload length must fit uint16")


@dataclass(frozen=True)
class UdpV3Packet:
    """One atomic node frame; output boundaries are preserved in the packet."""

    digital_node_id: int
    sequence: int
    media_timestamp_us: int
    outputs: tuple[UdpV3Output, ...]
    apply_at_us: Optional[int] = None
    flags: int = 0
    message_type: int = MESSAGE_TYPE_FRAME

    def __post_init__(self) -> None:
        _require_uint("digital_node_id", self.digital_node_id, MAX_UINT8)
        if self.digital_node_id == 0:
            raise ValueError("digital_node_id must be non-zero")
        _require_uint("sequence", self.sequence, MAX_UINT32)
        _require_uint("media_timestamp_us", self.media_timestamp_us, MAX_UINT64)
        if self.apply_at_us is not None:
            _require_uint("apply_at_us", self.apply_at_us, MAX_UINT64)
        _require_uint("flags", self.flags, MAX_UINT8)
        if self.flags & ~ALLOWED_FLAGS:
            raise ValueError(f"reserved flags must be zero, got 0x{self.flags:02X}")
        _require_uint("message_type", self.message_type, MAX_UINT8)
        if self.message_type != MESSAGE_TYPE_FRAME:
            raise ValueError(f"unsupported message_type {self.message_type!r}")
        if not self.outputs or len(self.outputs) > 3:
            raise ValueError("a UDP v3 node frame must contain one to three outputs")
        output_ids = [output.output_id for output in self.outputs]
        gpios = [output.gpio for output in self.outputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("output IDs must be unique within one node frame")
        if len(gpios) != len(set(gpios)):
            raise ValueError("GPIO assignments must be unique within one node frame")
        payload_length = sum(OUTPUT_LENGTH + len(output.pixels) * 3 for output in self.outputs)
        if payload_length > MAX_UINT16:
            raise ValueError("node payload length must fit uint16")

    def encode(self) -> bytes:
        payload = bytearray()
        for output in self.outputs:
            rgb = _pixels_to_payload(output.pixels)
            payload.extend(struct.pack(OUTPUT_FORMAT, output.output_id, output.gpio, len(output.pixels), len(rgb)))
            payload.extend(rgb)
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            self.message_type,
            self.digital_node_id,
            self.flags,
            self.sequence,
            self.media_timestamp_us,
            0 if self.apply_at_us is None else self.apply_at_us,
            len(self.outputs),
            len(payload),
        )
        raw = header + bytes(payload)
        return raw + struct.pack(">I", crc32(raw))

    @classmethod
    def decode(
        cls,
        data: bytes,
        *,
        expected_node_id: Optional[int] = None,
        expected_outputs: Optional[Mapping[int, tuple[int, int]]] = None,
        min_sequence: Optional[int] = None,
        max_udp_payload: int = MAX_UDP_PAYLOAD,
    ) -> Optional["UdpV3Packet"]:
        if len(data) < HEADER_LENGTH + CRC_LENGTH or len(data) > max_udp_payload:
            return None
        try:
            (magic, version, message_type, node_id, flags, sequence, media_timestamp_us,
             apply_at_raw, output_count, payload_length) = struct.unpack(HEADER_FORMAT, data[:HEADER_LENGTH])
        except struct.error:
            return None
        if (
            magic != MAGIC
            or version != VERSION
            or message_type != MESSAGE_TYPE_FRAME
            or flags & ~ALLOWED_FLAGS
        ):
            return None
        if output_count == 0 or output_count > 3:
            return None
        if expected_node_id is not None and node_id != expected_node_id:
            return None
        if min_sequence is not None and sequence < min_sequence:
            return None
        if len(data) != HEADER_LENGTH + payload_length + CRC_LENGTH:
            return None
        if crc32(data[:-CRC_LENGTH]) != struct.unpack(">I", data[-CRC_LENGTH:])[0]:
            return None
        cursor = HEADER_LENGTH
        payload_end = cursor + payload_length
        outputs: list[UdpV3Output] = []
        seen_ids: set[int] = set()
        seen_gpios: set[int] = set()
        for _ in range(output_count):
            if cursor + OUTPUT_LENGTH > payload_end:
                return None
            output_id, gpio, pixel_count, output_length = struct.unpack(
                OUTPUT_FORMAT, data[cursor : cursor + OUTPUT_LENGTH]
            )
            cursor += OUTPUT_LENGTH
            if output_id == 0 or output_id in seen_ids or gpio in seen_gpios:
                return None
            if pixel_count > 100 or output_length != pixel_count * 3:
                return None
            if cursor + output_length > payload_end:
                return None
            if expected_outputs is not None:
                expected = expected_outputs.get(output_id)
                if expected != (gpio, pixel_count):
                    return None
            raw_pixels = data[cursor : cursor + output_length]
            cursor += output_length
            seen_ids.add(output_id)
            seen_gpios.add(gpio)
            try:
                outputs.append(UdpV3Output(
                    output_id=output_id,
                    gpio=gpio,
                    pixels=tuple(
                        (raw_pixels[index], raw_pixels[index + 1], raw_pixels[index + 2])
                        for index in range(0, output_length, 3)
                    ),
                ))
            except ValueError:
                return None
        if cursor != payload_end:
            return None
        if expected_outputs is not None and seen_ids != set(expected_outputs):
            return None
        try:
            return cls(
                message_type=message_type,
                digital_node_id=node_id,
                flags=flags,
                sequence=sequence,
                media_timestamp_us=media_timestamp_us,
                apply_at_us=None if apply_at_raw == 0 else apply_at_raw,
                outputs=tuple(outputs),
            )
        except ValueError:
            return None


__all__ = [
    "FLAG_KEY_FRAME", "FLAG_SAFE_STATE", "HEADER_LENGTH", "MAGIC", "VERSION",
    "UdpV3Output", "UdpV3Packet",
]
