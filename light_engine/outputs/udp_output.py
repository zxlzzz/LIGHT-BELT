"""UDP v2 output for ESP32-S3 WS2811 physical nodes."""

from __future__ import annotations

import time
from typing import Callable, Optional

from light_engine.mapping.physical import PhysicalFrame
from light_engine.outputs import LatestFrameQueue, LightOutput, OutputMode
from light_engine.outputs.udp_v2 import FLAG_SAFE_STATE, UdpV2Packet
from light_engine.outputs.udp_v3 import (
    FLAG_KEY_FRAME,
    FLAG_SCHEDULED_APPLY,
    MAX_UINT64,
    UdpV3ClockBeacon,
    UdpV3Output,
    UdpV3Packet,
)


DEFAULT_SCHEDULE_LEAD_US = 20_000
MAX_SCHEDULE_LEAD_US = 100_000
DEFAULT_SESSION_START_REPEATS = 3
DEFAULT_SESSION_START_SPACING_US = 2_000
DEFAULT_BEACON_ADDRESS = ("255.255.255.255", 9001)
DEFAULT_BEACON_INTERVAL_US = 500_000
DEFAULT_STARTUP_BEACONS = 5
DEFAULT_STARTUP_BEACON_SPACING_US = 10_000


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
        self._injected_socket = socket
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
        self._health.healthy = True
        self._health.last_error = None

    def send_frame(self, frame: PhysicalFrame) -> None:
        if not self._open:
            self._health.frames_dropped += 1
            self._health.last_error = "UDP output is not open"
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
        flags = FLAG_SAFE_STATE if frame.metadata.get("SAFE_STATE") is True else 0
        safe_state = bool(flags & FLAG_SAFE_STATE)
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
                    if safe_state:
                        continue
                    self._health.frames_dropped += 1
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
        self._socket = self._injected_socket
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

    def __init__(
        self,
        *args,
        scheduled_apply: bool = False,
        monotonic_us: Optional[Callable[[], int]] = None,
        lead_us: int = DEFAULT_SCHEDULE_LEAD_US,
        session_start_repeats: int = DEFAULT_SESSION_START_REPEATS,
        session_start_spacing_us: int = DEFAULT_SESSION_START_SPACING_US,
        beacon_address: tuple[str, int] = DEFAULT_BEACON_ADDRESS,
        beacon_addresses: Optional[tuple[tuple[str, int], ...]] = None,
        beacon_interval_us: int = DEFAULT_BEACON_INTERVAL_US,
        startup_beacons: int = DEFAULT_STARTUP_BEACONS,
        startup_beacon_spacing_us: int = DEFAULT_STARTUP_BEACON_SPACING_US,
        sleep_s: Optional[Callable[[float], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        if type(scheduled_apply) is not bool:
            raise ValueError("scheduled_apply must be a boolean")
        self._require_int_range("lead_us", lead_us, 1, MAX_SCHEDULE_LEAD_US)
        self._require_int_range("session_start_repeats", session_start_repeats, 2, 10)
        self._require_int_range(
            "session_start_spacing_us", session_start_spacing_us, 0, 10_000
        )
        self._require_int_range("beacon_interval_us", beacon_interval_us, 1, MAX_UINT64)
        self._require_int_range("startup_beacons", startup_beacons, 1, 0xFFFFFFFF)
        self._require_int_range(
            "startup_beacon_spacing_us", startup_beacon_spacing_us, 0, MAX_UINT64
        )
        if (
            not isinstance(beacon_address, tuple)
            or len(beacon_address) != 2
            or not isinstance(beacon_address[0], str)
            or not beacon_address[0]
        ):
            raise ValueError("beacon_address must be a non-empty (host, port) tuple")
        self._require_int_range("beacon_address port", beacon_address[1], 1, 65535)
        if beacon_addresses is None:
            resolved_beacon_addresses = (beacon_address,)
        else:
            if not isinstance(beacon_addresses, tuple) or not beacon_addresses:
                raise ValueError("beacon_addresses must be a non-empty tuple")
            resolved_beacon_addresses = beacon_addresses
            for index, address in enumerate(resolved_beacon_addresses):
                if (
                    not isinstance(address, tuple)
                    or len(address) != 2
                    or not isinstance(address[0], str)
                    or not address[0]
                ):
                    raise ValueError(
                        f"beacon_addresses[{index}] must be a non-empty "
                        "(host, port) tuple"
                    )
                self._require_int_range(
                    f"beacon_addresses[{index}] port", address[1], 1, 65535
                )
            if len(set(resolved_beacon_addresses)) != len(
                resolved_beacon_addresses
            ):
                raise ValueError("beacon_addresses entries must be unique")
        if monotonic_us is not None and not callable(monotonic_us):
            raise ValueError("monotonic_us must be callable")
        if sleep_s is not None and not callable(sleep_s):
            raise ValueError("sleep_s must be callable")

        self._scheduled_apply = scheduled_apply
        self._monotonic_us = (
            monotonic_us
            if monotonic_us is not None
            else (lambda: time.monotonic_ns() // 1_000)
        )
        self._lead_us = lead_us
        self._session_start_repeats = session_start_repeats
        self._session_start_spacing_us = session_start_spacing_us
        self._beacon_address = beacon_address
        self._beacon_addresses = resolved_beacon_addresses
        self._beacon_interval_us = beacon_interval_us
        self._startup_beacons = startup_beacons
        self._startup_beacon_spacing_us = startup_beacon_spacing_us
        self._sleep_s = sleep_s if sleep_s is not None else time.sleep
        self._needs_key_frame = True
        self._next_beacon_sequence = 1
        self._last_beacon_us: Optional[int] = None
        self._last_clock_read_us: Optional[int] = None

    @staticmethod
    def _require_int_range(name: str, value: int, minimum: int, maximum: int) -> None:
        if type(value) is not int or value < minimum or value > maximum:
            raise ValueError(
                f"{name} must be an integer in [{minimum}, {maximum}], got {value!r}"
            )

    def open(self) -> None:
        try:
            super().open()
        except Exception:
            self.close()
            raise
        self._needs_key_frame = True
        self._next_beacon_sequence = 1
        self._last_beacon_us = None
        self._last_clock_read_us = None
        if not self._scheduled_apply:
            return
        try:
            self._enable_broadcast()
            for index in range(self._startup_beacons):
                self._send_clock_beacon_round()
                if index + 1 < self._startup_beacons:
                    self._sleep_s(self._startup_beacon_spacing_us / 1_000_000)
            # Give the final broadcast one normal beacon interval to reach the
            # nodes before the first unicast KEY_FRAME can be submitted.
            if self._startup_beacon_spacing_us:
                self._sleep_s(self._startup_beacon_spacing_us / 1_000_000)
        except Exception as exc:
            self._health.healthy = False
            self._health.last_error = f"UDP v3 clock beacon startup error: {exc}"
            self.close()
            raise RuntimeError(self._health.last_error) from exc

    def _enable_broadcast(self) -> None:
        if self.mode is not OutputMode.PRODUCTION or self._socket is None:
            return
        setter = getattr(self._socket, "setsockopt", None)
        if not callable(setter):
            return
        import socket as _socket

        setter(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)

    def _read_monotonic_us(self) -> int:
        value = self._monotonic_us()
        self._require_int_range("monotonic_us result", value, 0, MAX_UINT64)
        if self._last_clock_read_us is not None and value < self._last_clock_read_us:
            raise ValueError("monotonic_us must not move backwards")
        self._last_clock_read_us = value
        return value

    def _send_clock_beacon(
        self,
        host_monotonic_us: int,
        address: tuple[str, int],
        sequence: int,
    ) -> None:
        packet = UdpV3ClockBeacon(
            sequence=sequence,
            host_monotonic_us=host_monotonic_us,
        ).encode()
        try:
            self._send_datagram(packet, address)
        except Exception as exc:
            self._health.packets_dropped += 1
            self._health.last_error = f"UDP v3 clock beacon send error: {exc}"
            if self.mode is OutputMode.PRODUCTION:
                self._health.healthy = False
            raise
        self._health.packets_sent += 1
        self._health.mark_success()

    def _send_clock_beacon_round(
        self, first_host_monotonic_us: Optional[int] = None
    ) -> int:
        sequence = self._next_beacon_sequence
        last_host_monotonic_us = 0
        for index, address in enumerate(self._beacon_addresses):
            host_monotonic_us = (
                first_host_monotonic_us
                if index == 0 and first_host_monotonic_us is not None
                else self._read_monotonic_us()
            )
            self._send_clock_beacon(host_monotonic_us, address, sequence)
            last_host_monotonic_us = host_monotonic_us
        self._last_beacon_us = last_host_monotonic_us
        self._next_beacon_sequence = (self._next_beacon_sequence + 1) & 0xFFFFFFFF
        return last_host_monotonic_us

    def _scheduled_apply_at(self) -> int:
        now_us = self._read_monotonic_us()
        if (
            self._last_beacon_us is None
            or now_us - self._last_beacon_us >= self._beacon_interval_us
        ):
            now_us = self._send_clock_beacon_round(now_us)
        if now_us > MAX_UINT64 - self._lead_us:
            raise ValueError("monotonic_us + lead_us exceeds uint64")
        return now_us + self._lead_us

    def flush_latest(self) -> None:
        frame = self._queue.pop_latest()
        if frame is None:
            return
        frame_ok = True
        last_exception: Optional[Exception] = None
        try:
            flags = FLAG_SAFE_STATE if frame.metadata.get("SAFE_STATE") is True else 0
            starts_new_session = self._needs_key_frame and frame.sequence == 1
            if starts_new_session:
                flags |= FLAG_KEY_FRAME
            media_timestamp_us = int(round(frame.timestamp * 1_000_000))
            metadata_apply_at_us = frame.metadata.get("apply_at_us")
            if metadata_apply_at_us is not None:
                self._require_int_range(
                    "PhysicalFrame metadata apply_at_us",
                    metadata_apply_at_us,
                    1,
                    MAX_UINT64,
                )
            if self._scheduled_apply:
                if metadata_apply_at_us is not None:
                    raise ValueError(
                        "scheduled UdpOutputV3 owns apply_at_us; PhysicalFrame metadata "
                        "must not override it"
                    )
                apply_at_us = self._scheduled_apply_at()
            else:
                apply_at_us = metadata_apply_at_us
            if apply_at_us is not None:
                flags |= FLAG_SCHEDULED_APPLY
        except Exception as exc:
            self._health.last_error = f"UDP v3 frame preparation error: {exc}"
            if self.mode is OutputMode.PRODUCTION:
                self._health.healthy = False
                self._health.frames_dropped += 1
            raise
        encoded_datagrams: list[tuple[bytes, tuple[str, int]]] = []
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
                encoded_datagrams.append(
                    (packet, (digital_frame.host, digital_frame.port))
                )
            except Exception as exc:
                frame_ok = False
                self._health.packets_dropped += 1
                self._health.last_error = f"UDP v3 frame encoding error: {exc}"
                if self.mode is OutputMode.PRODUCTION:
                    self._health.healthy = False
                    self._health.frames_dropped += 1
                    raise
                break
        if not frame_ok:
            self._health.frames_dropped += 1
            return

        send_rounds = (
            self._session_start_repeats
            if self._scheduled_apply and starts_new_session
            else 1
        )
        for round_index in range(send_rounds):
            for packet, address in encoded_datagrams:
                try:
                    self._send_datagram(packet, address)
                    self._health.packets_sent += 1
                    self._health.mark_success()
                except Exception as exc:
                    frame_ok = False
                    self._health.packets_dropped += 1
                    self._health.last_error = f"UDP v3 send error: {exc}"
                    if self.mode is OutputMode.PRODUCTION:
                        self._health.healthy = False
                        if flags & FLAG_SAFE_STATE:
                            last_exception = exc
                            continue
                        self._health.frames_dropped += 1
                        raise
            if round_index + 1 < send_rounds and self._session_start_spacing_us:
                try:
                    self._sleep_s(self._session_start_spacing_us / 1_000_000)
                except Exception as exc:
                    frame_ok = False
                    last_exception = exc
                    self._health.last_error = (
                        f"UDP v3 session-start spacing error: {exc}"
                    )
                    if self.mode is OutputMode.PRODUCTION:
                        self._health.healthy = False
                        self._health.frames_dropped += 1
                        raise
                    break
        if frame_ok:
            self._health.logical_frames_sent += 1
            self._health.mark_success()
            if starts_new_session:
                self._needs_key_frame = False
        else:
            self._health.frames_dropped += 1
            if self.mode is OutputMode.PRODUCTION and last_exception is not None:
                raise RuntimeError(self._health.last_error) from last_exception

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(
            {
                "protocol": "UDP complete multi-output physical node frame v3",
                "max_pixels": 300,
                "supports_scheduled_apply": True,
                "scheduled_apply_enabled": self._scheduled_apply,
                "schedule_lead_us": self._lead_us if self._scheduled_apply else None,
                "session_start_repeats": (
                    self._session_start_repeats if self._scheduled_apply else 1
                ),
                "session_start_spacing_us": (
                    self._session_start_spacing_us if self._scheduled_apply else 0
                ),
                "clock_beacon_interval_us": (
                    self._beacon_interval_us if self._scheduled_apply else None
                ),
                "clock_beacon_targets": (
                    len(self._beacon_addresses) if self._scheduled_apply else 0
                ),
                "hardware_verified": False,
                "not_hardware_verified": True,
            }
        )
        return caps
