"""Phase 28 config-derived topology inspection tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from light_engine.cli import build_topology_inspection, cmd_inspect_topology
from light_engine.config import Config


PROFILE = "config/profiles/cabin-lighting-v3-production.yaml"
SHOW = "config/shows/cabin-show-v2.yaml"


def test_cabin_show_inspection_traces_all_fourteen_fixtures() -> None:
    report = build_topology_inspection(Config(Path(PROFILE)), SHOW)

    assert report["summary"] == {
        "digital_strips": 13,
        "analog_zones": 1,
        "physical_fixtures": 14,
    }
    regions = [region for path in report["virtual_paths"] for region in path["regions"]]
    assert {region["logical_id"] for region in regions} == {
        "zone_32",
        "strip_11", "strip_12", "strip_21", "strip_22", "strip_31",
        "strip_41", "strip_42", "strip_43", "strip_44", "strip_45",
        "strip_91", "strip_92", "strip_93",
    }
    strip_42 = next(region for region in regions if region["logical_id"] == "strip_42")
    assert strip_42["node_id"] == 8
    assert strip_42["output_id"] == 1
    assert strip_42["gpio"] == 4
    assert strip_42["host"] == "192.0.2.8"
    assert strip_42["port"] == 9001
    assert strip_42["transport_enabled"] is True
    cob = next(region for region in regions if region["logical_id"] == "zone_32")
    assert cob["node_id"] == 17
    assert cob["gpio"] is None
    assert cob["port"] == "REPLACE_WITH_RS485_PORT"


def test_inspect_topology_cli_prints_validated_json(capsys) -> None:
    Config.reset()
    result = cmd_inspect_topology(argparse.Namespace(config=PROFILE, show=SHOW))

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source"] == {"kind": "show_v2", "path": SHOW}
    assert report["hardware_verification"] == "NOT HARDWARE VERIFIED"
