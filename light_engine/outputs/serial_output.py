"""Serial/RS-485 output for STM32 analog zones.

Frozen 11-byte protocol:
  [0x55] [CMD] [R] [G] [B] [W] [Brightness] [Fade_H] [Fade_L] [CheckSum] [0xAA]

CheckSum algorithm:
  checksum = sum(Byte1 through Byte8) & 0xFF
  (Byte1 = CMD, Byte8 = Fade_L)

Brightness: 0-100
Legacy RGBW payload: 0-255
Fade: 0-65535 (big-endian)
Frame length: exactly 11 bytes
"""

from __future__ import annotations

import struct
import threading
import time
from collections import deque
from typing import Optional, Tuple

from light_engine.models import PixelFrame
from light_engine.outputs import LightOutput


# Protocol constants
FRAME_HEADER = 0x55
FRAME_FOOTER = 0xAA
FRAME_LENGTH = 11
DEFAULT_CMD = 0x01

# Limits
MAX_BRIGHTNESS = 100
MAX_RGBW = 255
MAX_FADE = 65535


def _compute_checksum(data: bytes) -> int:
    """8-bit sum checksum: sum(data[0:8]) & 0xFF.

    Covers bytes 1-8 (CMD through Fade_L inclusive).
    """
    return sum(data[:8]) & 0xFF


class SerialPacket:
    """Encoded 11-byte serial packet for a legacy RGBW zone.

    Fixed format:
      [0x55] [CMD] [R] [G] [B] [W] [Brightness] [Fade_H] [Fade_L] [CheckSum] [0xAA]
    """

    __slots__ = (
        "cmd", "r", "g", "b", "w", "brightness", "fade_ms",
    )

    def __init__(
        self,
        cmd: int = DEFAULT_CMD,
        r: int = 0,
        g: int = 0,
        b: int = 0,
        w: int = 0,
        brightness: int = 100,
        fade_ms: int = 0,
    ):
        if not (0 <= brightness <= MAX_BRIGHTNESS):
            raise ValueError(
                f"Brightness must be 0-{MAX_BRIGHTNESS}, got {brightness}"
            )
        for name, val in [("R", r), ("G", g), ("B", b), ("W", w)]:
            if not (0 <= val <= MAX_RGBW):
                raise ValueError(f"{name} must be 0-{MAX_RGBW}, got {val}")
        if not (0 <= fade_ms <= MAX_FADE):
            raise ValueError(f"Fade must be 0-{MAX_FADE}, got {fade_ms}")

        self.cmd = cmd
        self.r = r
        self.g = g
        self.b = b
        self.w = w
        self.brightness = brightness
        self.fade_ms = fade_ms

    def encode(self) -> bytes:
        """Encode to 11-byte binary frame.

        Returns:
            bytes of length 11.
        """
        # Build bytes 1-8: CMD, R, G, B, W, Brightness, Fade_H, Fade_L
        body = struct.pack(
            ">BBBBBBH",
            self.cmd,
            self.r,
            self.g,
            self.b,
            self.w,
            self.brightness,
            self.fade_ms,
        )
        checksum = _compute_checksum(body)
        frame = bytes([FRAME_HEADER]) + body + bytes([checksum, FRAME_FOOTER])
        assert len(frame) == FRAME_LENGTH, f"Frame must be {FRAME_LENGTH} bytes"
        return frame

    @classmethod
    def decode(cls, data: bytes) -> Optional["SerialPacket"]:
        """Decode an 11-byte frame. Returns None on any error.

        Validates: header, footer, length, checksum.
        Does NOT trust payload declarations.
        """
        if len(data) != FRAME_LENGTH:
            return None
        if data[0] != FRAME_HEADER or data[-1] != FRAME_FOOTER:
            return None

        body = data[1:9]  # bytes 1-8
        received_checksum = data[9]
        computed = _compute_checksum(body)
        if received_checksum != computed:
            return None

        cmd, r, g, b, w, brightness, fade_ms = struct.unpack(">BBBBBBH", body)

        # Validate ranges
        if brightness > MAX_BRIGHTNESS:
            return None
        if any(v > MAX_RGBW for v in (r, g, b, w)):
            return None
        if fade_ms > MAX_FADE:
            return None

        return cls(
            cmd=cmd,
            r=r,
            g=g,
            b=b,
            w=w,
            brightness=brightness,
            fade_ms=fade_ms,
        )

    def __repr__(self) -> str:
        return (
            f"SerialPacket(cmd=0x{self.cmd:02X}, r={self.r}, g={self.g}, "
            f"b={self.b}, w={self.w}, brightness={self.brightness}, "
            f"fade_ms={self.fade_ms})"
        )


class SerialStreamParser:
    """Streaming parser that handles fragmented, noisy, and malformed frames.

    Scans the byte stream for valid 11-byte frames.
    Handles: split packets, stuck bytes, noise, bad checksums, bad frames.
    Does NOT buffer unlimited data — has a configurable max buffer.
    """

    def __init__(self, max_buffer: int = 4096):
        self._buffer = bytearray()
        self._max_buffer = max_buffer
        self._valid_frames: int = 0
        self._invalid_frames: int = 0

    @property
    def valid_frames(self) -> int:
        return self._valid_frames

    @property
    def invalid_frames(self) -> int:
        return self._invalid_frames

    def feed(self, data: bytes) -> list[SerialPacket]:
        """Feed raw bytes into the parser. Returns list of decoded packets."""
        self._buffer.extend(data)

        # Enforce max buffer size to prevent unlimited growth
        if len(self._buffer) > self._max_buffer:
            # Drop oldest data
            self._buffer = self._buffer[-self._max_buffer:]

        frames = []
        while len(self._buffer) >= FRAME_LENGTH:
            # Find the next header byte
            try:
                header_idx = self._buffer.index(FRAME_HEADER)
            except ValueError:
                # No header found, clear buffer
                self._buffer.clear()
                break

            # Discard bytes before header (noise)
            if header_idx > 0:
                self._buffer = self._buffer[header_idx:]

            # Need at least FRAME_LENGTH bytes after header
            if len(self._buffer) < FRAME_LENGTH:
                break

            # Extract candidate frame
            candidate = bytes(self._buffer[:FRAME_LENGTH])
            packet = SerialPacket.decode(candidate)

            if packet is not None:
                frames.append(packet)
                self._valid_frames += 1
                self._buffer = self._buffer[FRAME_LENGTH:]
            else:
                # Bad frame: skip the header byte and try again
                self._buffer = self._buffer[1:]
                self._invalid_frames += 1

        return frames

    def reset(self) -> None:
        """Reset parser state."""
        self._buffer.clear()
        self._valid_frames = 0
        self._invalid_frames = 0


class SerialOutput(LightOutput):
    """Sends analog zone data via serial/RS-485 using legacy 11-byte protocol.

    Actual serial communication is only attempted if pyserial is available.
    Falls back to memory transport for testing.
    """

    def __init__(
        self,
        port: str = "COM3",
        baudrate: int = 115200,
        timeout: float = 0.1,
        reconnect_delay: float = 1.0,
        max_reconnect_attempts: int = 5,
    ):
        super().__init__()
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts

        self._serial: Optional[object] = None
        self._enabled = False
        self._reconnect_count = 0

        # Memory transport for testing (always available)
        self._memory_transport: Optional[bytearray] = None
        self._use_memory = False

        # Output thread
        self._write_queue: deque[bytes] = deque(maxlen=32)
        self._queue_lock = threading.Lock()
        self._write_thread: Optional[threading.Thread] = None
        self._running = False

        # Stream parser for testing loopback
        self._parser: Optional[SerialStreamParser] = None

    def open(self) -> None:
        """Open serial connection or fall back to memory transport."""
        self._open = True
        try:
            import serial as _serial
            self._serial = _serial.Serial(
                self._port, self._baudrate, timeout=self._timeout
            )
            self._enabled = True
            self._use_memory = False
        except Exception as e:
            self._enabled = False
            self._use_memory = True
            self._health.last_error = (
                f"Serial port {self._port} not available: {e}. "
                f"Using memory transport."
            )
            self._memory_transport = bytearray()
            self._parser = SerialStreamParser()

        self._running = True
        self._write_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._write_thread.start()

    def send_frame(self, frame: PixelFrame) -> None:
        """Enqueue legacy RGBW zone frames for writing."""
        if not self._open or not self._running:
            return

        packets: list[bytes] = []
        for zone in frame.zones:
            try:
                c = zone.color.to_uint8()
                legacy_w = max(c["warm_white"], c["cool_white"])
                packet = SerialPacket(
                    cmd=DEFAULT_CMD,
                    r=c["r"],
                    g=c["g"],
                    b=c["b"],
                    w=legacy_w,
                    brightness=MAX_BRIGHTNESS,
                    fade_ms=0,
                )
                packets.append(packet.encode())
            except Exception as e:
                self._health.last_error = f"Encode error: {e}"
                self._health.frames_dropped += 1
                return

        if not packets:
            return

        with self._queue_lock:
            maxlen = self._write_queue.maxlen
            if maxlen is not None and len(packets) > maxlen:
                self._health.last_error = (
                    f"Serial frame requires {len(packets)} packets, "
                    f"queue capacity is {maxlen}"
                )
                self._health.frames_dropped += 1
                return
            if maxlen is not None and len(self._write_queue) + len(packets) > maxlen:
                self._health.last_error = "Serial queue lacks capacity for complete frame"
                self._health.frames_dropped += 1
                return
            self._write_queue.extend(packets)
            self._health.frames_sent += 1

    def _writer_loop(self) -> None:
        """Background thread for writing queued frames."""
        while self._running:
            try:
                while True:
                    with self._queue_lock:
                        if not self._write_queue:
                            break
                        data = self._write_queue.popleft()
                    self._write_data(data)
                    self._health.packets_sent += 1
            except Exception as e:
                self._health.last_error = str(e)
                self._health.frames_dropped += 1
            time.sleep(0.001)  # 1ms polling, not busy-wait

    def _write_data(self, data: bytes) -> None:
        """Write raw bytes to the transport."""
        if self._use_memory and self._memory_transport is not None:
            self._memory_transport.extend(data)
            # Feed to parser for loopback testing
            if self._parser is not None:
                self._parser.feed(data)
        elif self._enabled and self._serial is not None:
            try:
                self._serial.write(data)  # type: ignore
            except Exception:
                self._health.last_error = "Serial write failed"
                self._attempt_reconnect()

    def _attempt_reconnect(self) -> None:
        """Attempt reconnection with backoff and max attempts."""
        if self._reconnect_count >= self._max_reconnect_attempts:
            self._enabled = False
            self._use_memory = True
            self._health.last_error = "Max reconnect attempts reached, using memory transport"
            return
        self._reconnect_count += 1
        time.sleep(self._reconnect_delay)
        try:
            import serial as _serial
            self._serial = _serial.Serial(
                self._port, self._baudrate, timeout=self._timeout
            )
            self._enabled = True
            self._reconnect_count = 0
        except Exception:
            pass

    def close(self) -> None:
        """Close serial connection and stop writer thread."""
        self._running = False
        if self._write_thread:
            self._write_thread.join(timeout=2.0)
        if self._serial:
            try:
                self._serial.close()  # type: ignore
            except Exception:
                pass
        self._serial = None
        self._enabled = False
        self._open = False

    # --- Test/Memory transport access ---
    def get_memory_bytes(self) -> bytes:
        """Get raw bytes written to memory transport (for testing)."""
        if self._memory_transport is not None:
            return bytes(self._memory_transport)
        return b""

    def get_parsed_packets(self) -> list[SerialPacket]:
        """Get packets parsed from memory transport (for loopback testing)."""
        if self._parser is not None:
            # Feed any remaining bytes
            raw = bytes(self._memory_transport or b"")
            if raw:
                return self._parser.feed(b"")
            # Re-parse from scratch
            temp_parser = SerialStreamParser()
            return temp_parser.feed(raw)
        return []

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update({
            "supports_rgbcct": True,
            "legacy_payload": "rgbw",
            "protocol": "STM32 11-byte fixed frame v1",
            "checksum": "8-bit sum (not CRC)",
            "frame_length": FRAME_LENGTH,
            "transport": "memory" if self._use_memory else "serial",
        })
        return caps
