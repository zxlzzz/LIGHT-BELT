"""JSON output - writes frames as JSON Lines for debugging."""

from __future__ import annotations

import json
import os
from pathlib import Path

from light_engine.mapping.physical import PhysicalFrame
from light_engine.models import PixelFrame
from light_engine.outputs import LightOutput


class JsonOutput(LightOutput):
    """Writes lighting frames as JSON Lines (one JSON object per line)."""

    def __init__(self, path: str = "output/light_data.jsonl", pretty: bool = False):
        super().__init__()
        self._path = Path(path)
        self._pretty = pretty
        self._file = None

    def open(self) -> None:
        os.makedirs(self._path.parent, exist_ok=True)
        self._file = open(self._path, "w", encoding="utf-8")
        self._open = True

    def send_frame(self, frame: PhysicalFrame | PixelFrame) -> None:
        if self._file is None:
            self._health.frames_dropped += 1
            return
        if isinstance(frame, PixelFrame):
            data = self._logical_frame_data(frame)
        else:
            data = self._physical_frame_data(frame)
        if self._pretty:
            json.dump(data, self._file, ensure_ascii=False)
            self._file.write("\n")
        else:
            self._file.write(json.dumps(data, ensure_ascii=False) + "\n")
        self._file.flush()
        self._health.logical_frames_sent += 1
        self._health.mark_success()

    def _physical_frame_data(self, frame: PhysicalFrame) -> dict:
        data = {
            "timestamp": frame.timestamp,
            "sequence": frame.sequence,
            "digital_nodes": [
                {
                    "node_id": digital.node_id,
                    "host": digital.host,
                    "port": digital.port,
                    "pixel_count": len(digital.pixels),
                    "pixels": [
                        (round(r * 255), round(g * 255), round(b * 255))
                        for r, g, b in digital.pixels
                    ],
                }
                for digital in frame.digital_frames
            ],
            "analog_nodes": [
                {
                    "node_id": command.node_id,
                    "zone_id": command.zone_id,
                    "fade_ms": command.fade_ms,
                    "r": command.color.to_uint8()["r"],
                    "g": command.color.to_uint8()["g"],
                    "b": command.color.to_uint8()["b"],
                    "warm_white": command.color.to_uint8()["warm_white"],
                    "cool_white": command.color.to_uint8()["cool_white"],
                }
                for command in frame.analog_commands
            ],
            "metadata": frame.metadata,
        }
        data["digital_frames"] = data["digital_nodes"]
        data["analog_commands"] = data["analog_nodes"]
        return data

    def _logical_frame_data(self, frame: PixelFrame) -> dict:
        return {
            "timestamp": frame.timestamp,
            "sequence": frame.sequence,
            "strips": [
                {
                    "strip_id": strip.strip_id,
                    "pixel_count": strip.pixel_count,
                    "pixels": strip.to_uint8(),
                }
                for strip in frame.strips
            ],
            "zones": [
                {
                    "zone_id": zone.zone_id,
                    "r": zone.color.to_uint8()["r"],
                    "g": zone.color.to_uint8()["g"],
                    "b": zone.color.to_uint8()["b"],
                    "warm_white": zone.color.to_uint8()["warm_white"],
                    "cool_white": zone.color.to_uint8()["cool_white"],
                }
                for zone in frame.zones
            ],
            "metadata": frame.metadata,
        }

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        self._open = False
