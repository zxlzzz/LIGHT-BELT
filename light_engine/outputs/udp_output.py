"""UDP v2 output for ESP32-S3 WS2811 physical nodes."""

from __future__ import annotations

from typing import Optional

from light_engine.mapping.physical import PhysicalFrame
from light_engine.outputs import LatestFrameQueue, LightOutput, OutputMode
from light_engine.outputs.udp_v2 import FLAG_SAFE_STATE, UdpV2Packet
from light_engine.outputs.udp_v3 import UdpV3Output, UdpV3Packet


class UdpOutputV2(LightOutput):
    """UDP v2 transport that sends one datagram per digital node frame."""

    def __init__(
        self,
        *,
        mode: OutputMode | str = OutputMode.MEMORY,
        socket: Optional[object] = None,
        auto_flush: bool = True,
    ) -> None:
        super().__init__()
        self.mode = OutputMode.from_config(mode)
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
                self._health.last_error = f"UDP production socket unavailable: {exc}"
                raise RuntimeError(self._health.last_error) from exc
        self._open = True

    def send_frame(self, frame: PhysicalFrame) -> None:
        if not self._open:
            self._health.frames_dropped += 1
            self._health.last_error = "UDP output is not open"
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
        flags = FLAG_SAFE_STATE if frame.metadata.get("SAFE_STATE") is True else 0
        for digital_frame in frame.digital_frames:
            try:
                pixels_uint8 = [
                    (round(r * 255), round(g * 255), round(b * 255))
                    for r, g, b in digital_frame.pixels
                ]
                packet = UdpV2Packet(
                    digital_node_id=digital_frame.node_id,
                    sequence=frame.sequence,
                    pixels=pixels_uint8,
                    flags=flags,
                ).encode()
                address = (digital_frame.host, digital_frame.port)
                self._send_datagram(packet, address)
                self._health.packets_sent += 1
                self._health.mark_success()
            except Exception as exc:
                frame_ok = False
                self._health.packets_dropped += 1
                self._health.last_error = f"UDP v2 send error: {exc}"
                if self.mode is OutputMode.PRODUCTION:
                    self._health.healthy = False
                    raise
        if frame_ok:
            self._health.logical_frames_sent += 1
            self._health.mark_success()
        else:
            self._health.frames_dropped += 1

    def _send_datagram(self, packet: bytes, address: tuple[str, int]) -> None:
        if self.mode is OutputMode.FAKE:
            return
        if self.mode is OutputMode.MEMORY:
            self._sent_datagrams.append((packet, address))
            return
        if self._socket is None:
            raise RuntimeError("UDP production socket is not open")
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
                "protocol": "UDP complete physical frame v2",
                "max_pixels": 65535,
                "mode": self.mode.value,
                "transport": "injected"
                if self._socket is not None and not self._owns_socket
                else self.mode.value,
                "hardware_verified": False,
            }
        )
        return caps


class UdpOutputV3(UdpOutputV2):
    """UDP v3 transport: one atomic multi-output datagram per ESP32 node.

    ``DigitalNodeFrame.outputs`` is the only V3 input.  This class refuses a
    legacy concatenated ``pixels``-only frame so independent hardware outputs
    can never accidentally be treated as one continuous strip.
    """

    def flush_latest(self) -> None:
        frame = self._queue.pop_latest()
        if frame is None:
            return
        frame_ok = True
        flags = FLAG_SAFE_STATE if frame.metadata.get("SAFE_STATE") is True else 0
        media_timestamp_us = int(round(frame.timestamp * 1_000_000))
        apply_at_us = frame.metadata.get("apply_at_us")
        if apply_at_us is not None and type(apply_at_us) is not int:
            raise ValueError("PhysicalFrame metadata apply_at_us must be an integer")
        for digital_frame in frame.digital_frames:
            try:
                if not digital_frame.outputs:
                    raise ValueError(
                        f"UDP v3 node {digital_frame.node_id} has no independent outputs"
                    )
                packet = UdpV3Packet(
                    digital_node_id=digital_frame.node_id,
                    sequence=frame.sequence,
                    media_timestamp_us=media_timestamp_us,
                    apply_at_us=apply_at_us,
                    flags=flags,
                    outputs=tuple(
                        UdpV3Output(
                            output_id=output.output_id,
                            gpio=output.gpio,
                            pixels=tuple(
                                (round(r * 255), round(g * 255), round(b * 255))
                                for r, g, b in output.pixels
                            ),
                        )
                        for output in digital_frame.outputs
                    ),
                ).encode()
                self._send_datagram(packet, (digital_frame.host, digital_frame.port))
                self._health.packets_sent += 1
                self._health.mark_success()
            except Exception as exc:
                frame_ok = False
                self._health.packets_dropped += 1
                self._health.last_error = f"UDP v3 send error: {exc}"
                if self.mode is OutputMode.PRODUCTION:
                    self._health.healthy = False
                    raise
        if frame_ok:
            self._health.logical_frames_sent += 1
            self._health.mark_success()
        else:
            self._health.frames_dropped += 1

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(
            {
                "protocol": "UDP complete multi-output physical node frame v3",
                "max_pixels": 300,
                "hardware_verified": False,
                "not_hardware_verified": True,
            }
        )
        return caps
