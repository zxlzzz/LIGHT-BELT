"""UDP output for ESP32-S3 digital LED strips.

Implements a minimal binary protocol with sequence numbers and checksum.
Does NOT require actual hardware to be present.
"""

from __future__ import annotations

import struct
import time
from typing import Optional

from light_engine.models import PixelFrame
from light_engine.outputs import LightOutput


# Protocol constants
PROTOCOL_VERSION = 1
HEADER_MAGIC = 0x4C45  # "LE" for Light Engine
HEADER_SIZE = 12
MAX_PIXELS_PER_PACKET = 218  # Fits in ~1400 byte UDP payload


def _compute_checksum(data: bytes) -> int:
    """Simple 16-bit XOR checksum."""
    result = 0
    for i in range(0, len(data) - 1, 2):
        result ^= (data[i] << 8) | data[i + 1]
    if len(data) % 2:
        result ^= data[-1] << 8
    return result & 0xFFFF


class UdpPacket:
    """Encoded UDP packet for a digital strip frame."""

    def __init__(
        self,
        sequence: int,
        strip_id: int,
        pixel_offset: int,
        pixel_count: int,
        pixels: list[tuple[int, int, int]],
    ):
        self.sequence = sequence
        self.strip_id = strip_id
        self.pixel_offset = pixel_offset
        self.pixel_count = pixel_count
        self.pixels = pixels

    def encode(self) -> bytes:
        """Encode packet to binary format."""
        payload = bytearray()
        for r, g, b in self.pixels:
            payload.extend([r, g, b])
        header = struct.pack(
            ">HHHHHH",
            HEADER_MAGIC,
            PROTOCOL_VERSION,
            self.sequence & 0xFFFF,
            self.strip_id,
            self.pixel_offset,
            self.pixel_count,
        )
        checksum = _compute_checksum(header + payload)
        return header + payload + struct.pack(">H", checksum)

    @classmethod
    def decode(cls, data: bytes) -> Optional["UdpPacket"]:
        """Decode binary packet. Returns None on error."""
        if len(data) < HEADER_SIZE + 2:
            return None
        header = data[:HEADER_SIZE]
        magic, version, seq, strip_id, offset, count = struct.unpack(">HHHHHH", header)
        if magic != HEADER_MAGIC or version != PROTOCOL_VERSION:
            return None
        expected_payload = count * 3
        if len(data) != HEADER_SIZE + expected_payload + 2:
            return None
        payload = data[HEADER_SIZE : HEADER_SIZE + expected_payload]
        received_checksum = struct.unpack(">H", data[-2:])[0]
        computed = _compute_checksum(data[: HEADER_SIZE + expected_payload])
        if received_checksum != computed:
            return None
        pixels = [
            (payload[i], payload[i + 1], payload[i + 2])
            for i in range(0, expected_payload, 3)
        ]
        return cls(seq, strip_id, offset, count, pixels)


class UdpOutput(LightOutput):
    """Sends digital strip data via UDP. Stub for ESP32-S3.

    Actual UDP sending is not implemented unless a socket can be created.
    """

    def __init__(
        self, host: str = "127.0.0.1", port: int = 9001, max_packet_size: int = 1400
    ):
        super().__init__()
        self._host = host
        self._port = port
        self._max_packet_size = max_packet_size
        self._socket: Optional[object] = None
        self._enabled = False

    def open(self) -> None:
        try:
            import socket as _socket
            self._socket = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            self._enabled = True
        except Exception:
            self._enabled = False
        self._open = True

    def send_frame(self, frame: PixelFrame) -> None:
        if not self._enabled or self._socket is None:
            self._health.frames_dropped += 1
            return
        frame_ok = True
        for strip_idx, strip in enumerate(frame.strips):
            pixels_uint8 = strip.to_uint8()
            offset = 0
            while offset < strip.pixel_count:
                chunk = pixels_uint8[offset : offset + MAX_PIXELS_PER_PACKET]
                packet = UdpPacket(
                    sequence=frame.sequence,
                    strip_id=strip_idx,
                    pixel_offset=offset,
                    pixel_count=len(chunk),
                    pixels=list(chunk),
                )
                try:
                    self._socket.sendto(packet.encode(), (self._host, self._port))  # type: ignore
                    self._health.packets_sent += 1
                    self._health.mark_success()
                except Exception as e:
                    frame_ok = False
                    self._health.last_error = str(e)
                    self._health.packets_dropped += 1
                offset += MAX_PIXELS_PER_PACKET
        if frame_ok:
            self._health.logical_frames_sent += 1
            self._health.mark_success()
        else:
            self._health.frames_dropped += 1

    def close(self) -> None:
        if self._socket:
            try:
                self._socket.close()  # type: ignore
            except Exception:
                pass
        self._socket = None
        self._enabled = False
        self._open = False

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update({
            "supports_digital": True,
            "max_pixels": 65535,
            "protocol": f"UDP binary v{PROTOCOL_VERSION}",
        })
        return caps
