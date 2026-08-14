"""DDP realtime output for WLED-compatible ESP32 receivers."""

from __future__ import annotations

from typing import Optional

from light_engine.mapping.physical import DigitalNodeFrame, PhysicalFrame
from light_engine.outputs import LatestFrameQueue, LightOutput, OutputMode


DDP_DEFAULT_PORT = 4048
DDP_HEADER_LEN = 10
DDP_FLAGS_VER1 = 0x40
DDP_FLAGS_PUSH = 0x01
DDP_TYPE_RGB24 = 0x0B
DDP_ID_DISPLAY = 0x01
DDP_CHANNELS_PER_PACKET = 1440


def _to_u8(value: float) -> int:
    return max(0, min(255, round(value * 255)))


def encode_ddp_packets(
    pixels: list[tuple[int, int, int]],
    *,
    sequence: int,
    max_channels_per_packet: int = DDP_CHANNELS_PER_PACKET,
) -> list[bytes]:
    """Encode RGB pixels into one or more DDP RGB24 packets.

    DDP offsets and lengths are expressed in color channels, not pixels.
    The final packet carries the PUSH flag so WLED renders the complete frame.
    """
    if max_channels_per_packet <= 0:
        raise ValueError("max_channels_per_packet must be positive")

    max_channels_per_packet -= max_channels_per_packet % 3
    if max_channels_per_packet <= 0:
        raise ValueError("max_channels_per_packet must allow at least one RGB pixel")

    payload = bytearray()
    for red, green, blue in pixels:
        payload.extend((red & 0xFF, green & 0xFF, blue & 0xFF))

    if not payload:
        payload.extend((0, 0, 0))

    packets: list[bytes] = []
    channel_count = len(payload)
    channel_offset = 0
    seq = sequence & 0x0F
    if seq == 0:
        seq = 1

    while channel_offset < channel_count:
        next_offset = min(channel_offset + max_channels_per_packet, channel_count)
        chunk = bytes(payload[channel_offset:next_offset])
        is_last = next_offset >= channel_count
        flags = DDP_FLAGS_VER1 | (DDP_FLAGS_PUSH if is_last else 0)
        header = bytes(
            (
                flags,
                seq,
                DDP_TYPE_RGB24,
                DDP_ID_DISPLAY,
                (channel_offset >> 24) & 0xFF,
                (channel_offset >> 16) & 0xFF,
                (channel_offset >> 8) & 0xFF,
                channel_offset & 0xFF,
                (len(chunk) >> 8) & 0xFF,
                len(chunk) & 0xFF,
            )
        )
        packets.append(header + chunk)
        channel_offset = next_offset
        seq = (seq + 1) & 0x0F
        if seq == 0:
            seq = 1

    return packets


class DdpOutput(LightOutput):
    """WLED DDP transport.

    Each physical ESP32/WLED node becomes one DDP receiver. Independent node
    outputs are concatenated by output_id, matching WLED LED Preferences Start
    offsets when a controller drives multiple outputs.
    """

    def __init__(
        self,
        *,
        mode: OutputMode | str = OutputMode.MEMORY,
        socket: Optional[object] = None,
        port: int = DDP_DEFAULT_PORT,
        auto_flush: bool = True,
    ) -> None:
        super().__init__()
        self.mode = OutputMode.from_config(mode)
        self.port = port
        self._socket = socket
        self._owns_socket = False
        self._sent_datagrams: list[tuple[bytes, tuple[str, int]]] = []
        self._queue: LatestFrameQueue[PhysicalFrame] = LatestFrameQueue()
        self._auto_flush = auto_flush

    def open(self) -> None:
        if self._socket is None and self.mode is OutputMode.PRODUCTION:
            try:
                import socket as _socket

                self._socket = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                self._owns_socket = True
            except Exception as exc:
                self._health.healthy = False
                self._health.last_error = f"DDP production socket unavailable: {exc}"
                raise RuntimeError(self._health.last_error) from exc
        self._open = True
        self._health.healthy = True
        self._health.last_error = None

    def send_frame(self, frame: PhysicalFrame) -> None:
        if not self._open:
            self._health.frames_dropped += 1
            self._health.last_error = "DDP output is not open"
            if self.mode is OutputMode.PRODUCTION:
                self._health.healthy = False
                raise RuntimeError(self._health.last_error)
            return
        if self._queue.push(frame):
            self._health.frames_dropped += 1
        if self._auto_flush:
            self.flush_latest()

    def flush_latest(self) -> None:
        frame = self._queue.pop_latest()
        if frame is None:
            return

        frame_ok = True
        safe_state = frame.metadata.get("SAFE_STATE") is True
        for digital_frame in frame.digital_frames:
            if not digital_frame.enabled:
                continue
            try:
                pixels = self._node_pixels(digital_frame)
                for packet in encode_ddp_packets(pixels, sequence=frame.sequence):
                    self._send_datagram(packet, (digital_frame.host, self.port))
                    self._health.packets_sent += 1
                self._health.mark_success()
            except Exception as exc:
                frame_ok = False
                self._health.packets_dropped += 1
                self._health.last_error = f"DDP send error: {exc}"
                if self.mode is OutputMode.PRODUCTION:
                    self._health.healthy = False
                    if safe_state:
                        continue
                    self._health.frames_dropped += 1
                    raise

        if frame_ok:
            self._health.logical_frames_sent += 1
            self._health.mark_success()
        else:
            self._health.frames_dropped += 1

    def _node_pixels(self, digital_frame: DigitalNodeFrame) -> list[tuple[int, int, int]]:
        if digital_frame.outputs:
            source_pixels = [
                pixel
                for output in sorted(digital_frame.outputs, key=lambda item: item.output_id)
                for pixel in output.pixels
            ]
        else:
            source_pixels = digital_frame.pixels

        return [(_to_u8(red), _to_u8(green), _to_u8(blue)) for red, green, blue in source_pixels]

    def _send_datagram(self, packet: bytes, address: tuple[str, int]) -> None:
        if self.mode is OutputMode.FAKE:
            return
        if self.mode is OutputMode.MEMORY:
            self._sent_datagrams.append((packet, address))
            return
        if self._socket is None:
            raise RuntimeError("DDP production socket is not open")
        self._socket.sendto(packet, address)  # type: ignore[attr-defined]

    def close(self) -> None:
        if self._owns_socket and self._socket is not None:
            try:
                self._socket.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._socket = None
        self._owns_socket = False
        self._open = False

    def get_sent_datagrams(self) -> list[tuple[bytes, tuple[str, int]]]:
        return list(self._sent_datagrams)

    def pending_frames(self) -> int:
        return len(self._queue)

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(
            {
                "supports_digital": True,
                "protocol": "DDP RGB24 realtime",
                "port": self.port,
                "max_pixels_per_packet": DDP_CHANNELS_PER_PACKET // 3,
                "mode": self.mode.value,
                "hardware_verified": False,
            }
        )
        return caps
