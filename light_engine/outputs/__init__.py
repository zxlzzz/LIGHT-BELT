"""Output abstraction layer for lighting data.

Provides a unified LightOutput interface and concrete implementations:
- NullOutput: discards all frames (benchmarking)
- JsonOutput: writes frames as JSON Lines (debugging)
- SimulatorOutput: feeds the simulator
- UdpOutput: sends binary packets via UDP (ESP32-S3)
- SerialOutput: sends legacy RGBW commands via serial (STM32)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from light_engine.models import PixelFrame


class OutputHealth:
    """Health status of an output device."""

    def __init__(self) -> None:
        self.healthy: bool = True
        self.last_error: Optional[str] = None
        self.frames_sent: int = 0
        self.packets_sent: int = 0
        self.frames_dropped: int = 0
        self.errors: list[str] = []


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
    def send_frame(self, frame: PixelFrame) -> None:
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
from light_engine.outputs.udp_output import UdpOutput
from light_engine.outputs.serial_output import SerialOutput


def create_outputs(config: Any) -> dict[str, LightOutput]:
    """Create output instances from configuration.

    Args:
        config: Config instance with outputs configuration.

    Returns:
        Dict mapping output name to instance.
    """
    outputs: dict[str, LightOutput] = {}
    enabled = config.get("outputs.enabled", ["simulator", "json"])

    if "null" in enabled:
        outputs["null"] = NullOutput()
    if "json" in enabled:
        outputs["json"] = JsonOutput(
            path=config.get("outputs.json.path", "output/light_data.jsonl"),
            pretty=config.get("outputs.json.pretty", False),
        )
    if "simulator" in enabled:
        outputs["simulator"] = SimulatorOutput()
    if "udp" in enabled:
        outputs["udp"] = UdpOutput(
            host=config.get("outputs.udp.host", "127.0.0.1"),
            port=config.get("outputs.udp.port", 9001),
            max_packet_size=config.get("outputs.udp.max_packet_size", 1400),
        )
    if "serial" in enabled:
        outputs["serial"] = SerialOutput(
            port=config.get("outputs.serial.port", "COM3"),
            baudrate=config.get("outputs.serial.baudrate", 115200),
        )

    return outputs


def open_all(outputs: dict[str, LightOutput]) -> None:
    """Open all outputs, suppressing individual failures."""
    for name, output in outputs.items():
        try:
            output.open()
        except Exception as e:
            output.health().healthy = False
            output.health().last_error = str(e)


def send_all(outputs: dict[str, LightOutput], frame: PixelFrame) -> None:
    """Send frame to all open outputs, isolating failures."""
    for name, output in outputs.items():
        health = output.health()
        if not health.healthy:
            continue
        try:
            frames_before = health.frames_sent
            drops_before = health.frames_dropped
            output.send_frame(frame)
            if (
                health.frames_sent == frames_before
                and health.frames_dropped == drops_before
            ):
                health.frames_sent += 1
        except Exception as e:
            health.healthy = False
            health.last_error = str(e)
            health.frames_dropped += 1
            health.errors.append(str(e))


def close_all(outputs: dict[str, LightOutput]) -> None:
    """Close all outputs."""
    for output in outputs.values():
        try:
            output.close()
        except Exception:
            pass
