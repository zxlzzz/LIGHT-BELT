"""Output abstraction layer for lighting data.

Provides a unified LightOutput interface and concrete implementations:
- NullOutput: discards all frames (benchmarking)
- JsonOutput: writes frames as JSON Lines (debugging)
- SimulatorOutput: feeds the simulator
- UdpOutputV2: legacy continuous-payload physical-node UDP v2 frames
- UdpOutputV3: complete multi-output physical-node UDP v3 frames (ESP32-S3)
- SerialOutputV2: sends RS-485 v2 RGB+CCT frames (STM32)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import time
import threading
from typing import Any, Generic, Optional, TypeVar

from light_engine.mapping.physical import PhysicalFrame


class OutputMode(Enum):
    """Explicit transport mode for hardware outputs."""

    PRODUCTION = "production"
    MEMORY = "memory"
    FAKE = "fake"

    @classmethod
    def from_config(cls, value: Any) -> "OutputMode":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValueError(f"outputs.mode must be one of: {allowed}") from exc


T = TypeVar("T")


class LatestFrameQueue(Generic[T]):
    """One-slot queue where a newer complete frame overwrites the older one."""

    def __init__(self) -> None:
        self._frame: Optional[T] = None
        self._lock = threading.Lock()

    def push(self, frame: T) -> bool:
        """Store frame and return True when an older frame was overwritten."""
        with self._lock:
            dropped = self._frame is not None
            self._frame = frame
            return dropped

    def pop_latest(self) -> Optional[T]:
        with self._lock:
            frame = self._frame
            self._frame = None
            return frame

    def __len__(self) -> int:
        with self._lock:
            return 1 if self._frame is not None else 0


class OutputHealth:
    """Health status of an output device."""

    def __init__(self) -> None:
        self.healthy: bool = True
        self.last_error: Optional[str] = None
        self.logical_frames_submitted: int = 0
        self.logical_frames_sent: int = 0
        self.packets_sent: int = 0
        self.frames_dropped: int = 0
        self.packets_dropped: int = 0
        self.last_success_time: float = 0.0

    @property
    def frames_sent(self) -> int:
        """Backward-compatible read-only alias for logical_frames_sent."""
        return self.logical_frames_sent or self.logical_frames_submitted

    def mark_success(self) -> None:
        self.last_success_time = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "last_error": self.last_error,
            "logical_frames_submitted": self.logical_frames_submitted,
            "logical_frames_sent": self.logical_frames_sent,
            "packets_sent": self.packets_sent,
            "frames_dropped": self.frames_dropped,
            "packets_dropped": self.packets_dropped,
            "last_success_time": self.last_success_time,
        }


class LightOutput(ABC):
    """Abstract base class for all lighting output backends."""

    def __init__(self) -> None:
        self._health = OutputHealth()
        self._open = False

    @abstractmethod
    def open(self) -> None:
        """Open/initialize the output device."""
        ...

    @abstractmethod
    def send_frame(self, frame: PhysicalFrame) -> None:
        """Send a single frame to the output device."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close/shutdown the output device."""
        ...

    def health(self) -> OutputHealth:
        """Return current health status."""
        return self._health

    def capabilities(self) -> dict[str, Any]:
        """Return capabilities of this output."""
        return {
            "type": self.__class__.__name__,
            "supports_rgbcct": False,
            "supports_digital": False,
            "max_pixels": 0,
        }

    def is_open(self) -> bool:
        """Check if output is currently open."""
        return self._open


from light_engine.outputs.null_output import NullOutput
from light_engine.outputs.json_output import JsonOutput
from light_engine.outputs.simulator_output import SimulatorOutput
from light_engine.outputs.udp_output import UdpOutputV2, UdpOutputV3
from light_engine.outputs.serial_output import SerialOutputV2


def create_outputs(config: Any) -> dict[str, LightOutput]:
    """Create output instances from configuration.

    Args:
        config: Config instance with outputs configuration.

    Returns:
        Dict mapping output name to instance.
    """
    outputs: dict[str, LightOutput] = {}
    enabled = config.get("outputs.enabled", ["simulator", "json"])
    mode = OutputMode.from_config(config.get("outputs.mode", OutputMode.MEMORY.value))
    legacy_enabled = {"serial", "udp"} & set(enabled)
    if legacy_enabled:
        names = ", ".join(sorted(legacy_enabled))
        raise ValueError(
            f"Legacy v1 outputs are removed in Phase 6: {names}. "
            "Use rs485_v2 and udp_v2."
        )

    if "null" in enabled:
        outputs["null"] = NullOutput()
    if "json" in enabled:
        outputs["json"] = JsonOutput(
            path=config.get("outputs.json.path", "output/light_data.jsonl"),
            pretty=config.get("outputs.json.pretty", False),
        )
    if "simulator" in enabled:
        outputs["simulator"] = SimulatorOutput()
    if "udp_v2" in enabled:
        outputs["udp_v2"] = UdpOutputV2(mode=mode)
    if "udp_v3" in enabled:
        outputs["udp_v3"] = UdpOutputV3(mode=mode)
    if "rs485_v2" in enabled:
        outputs["rs485_v2"] = SerialOutputV2(
            mode=mode,
            port=config.get("outputs.serial.port", "COM3"),
            baudrate=config.get("outputs.serial.baudrate", 115200),
        )

    return outputs


def open_all(outputs: dict[str, LightOutput]) -> None:
    """Open all outputs, isolating failures except strict production transports."""
    for name, output in outputs.items():
        try:
            output.open()
        except Exception as e:
            output.health().healthy = False
            output.health().last_error = str(e)
            if getattr(output, "mode", None) is OutputMode.PRODUCTION:
                raise


def send_all(outputs: dict[str, LightOutput], frame: PhysicalFrame) -> None:
    """Send a physical frame to all open outputs, isolating failures."""
    for name, output in outputs.items():
        health = output.health()
        health.logical_frames_submitted += 1
        if not health.healthy:
            continue
        try:
            output.send_frame(frame)
        except Exception as e:
            health.healthy = False
            health.last_error = str(e)


def health_summary(outputs: dict[str, LightOutput]) -> dict[str, Any]:
    """Return a JSON-serializable health summary for all outputs."""
    per_output = {name: output.health().to_dict() for name, output in outputs.items()}
    totals = {
        "outputs": len(outputs),
        "healthy_outputs": sum(1 for item in per_output.values() if item["healthy"]),
        "logical_frames_submitted": sum(
            item["logical_frames_submitted"] for item in per_output.values()
        ),
        "logical_frames_sent": sum(
            item["logical_frames_sent"] for item in per_output.values()
        ),
        "packets_sent": sum(item["packets_sent"] for item in per_output.values()),
        "frames_dropped": sum(item["frames_dropped"] for item in per_output.values()),
        "packets_dropped": sum(
            item["packets_dropped"] for item in per_output.values()
        ),
    }
    return {"outputs": per_output, "totals": totals}


def close_all(outputs: dict[str, LightOutput]) -> None:
    """Close all outputs."""
    for output in outputs.values():
        try:
            output.close()
        except Exception:
            pass
