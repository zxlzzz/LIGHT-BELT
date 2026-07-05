"""JSON output - writes frames as JSON Lines for debugging."""

from __future__ import annotations

import json
import os
from pathlib import Path

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

    def send_frame(self, frame: PixelFrame) -> None:
        if self._file is None:
            self._health.frames_dropped += 1
            return
        data = {
            "timestamp": frame.timestamp,
            "sequence": frame.sequence,
            "strips": [
                {
                    "strip_id": s.strip_id,
                    "pixel_count": s.pixel_count,
                    "pixels": s.to_uint8(),
                }
                for s in frame.strips
            ],
            "zones": [
                {
                    "zone_id": z.zone_id,
                    "r": z.color.to_uint8()["r"],
                    "g": z.color.to_uint8()["g"],
                    "b": z.color.to_uint8()["b"],
                    "warm_white": z.color.to_uint8()["warm_white"],
                    "cool_white": z.color.to_uint8()["cool_white"],
                }
                for z in frame.zones
            ],
            "metadata": frame.metadata,
        }
        if self._pretty:
            json.dump(data, self._file, ensure_ascii=False)
            self._file.write("\n")
        else:
            self._file.write(json.dumps(data, ensure_ascii=False) + "\n")
        self._file.flush()
        self._health.logical_frames_sent += 1
        self._health.mark_success()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        self._open = False
