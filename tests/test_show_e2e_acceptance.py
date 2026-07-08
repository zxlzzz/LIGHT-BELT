from __future__ import annotations

import json
import math
from pathlib import Path

from scripts.show_acceptance import run_acceptance


SHOW = Path("config/show_acceptance.yaml")
LAYOUT = Path("config/layout_acceptance.yaml")


def test_phase_17_show_acceptance_outputs_required_evidence() -> None:
    summary = run_acceptance(SHOW, LAYOUT)

    assert summary["frame_count"] == 9000
    assert summary["two_run_digests"][0] == summary["two_run_digests"][1]
    assert summary["offline_capacity_fps"] > 30.0
    assert summary["not_hardware_verified"] == "NOT HARDWARE VERIFIED"

    seam = summary["evidence"]["seam_frames"]
    assert [item["virtual_coordinate"] for item in seam] == [71, 72, 73]
    assert seam[0]["expected_destination"] == {"strip_id": "front", "pixel_index": 71}
    assert seam[1]["expected_destination"] == {"strip_id": "wall_right", "pixel_index": 99}
    assert seam[2]["expected_destination"] == {"strip_id": "wall_right", "pixel_index": 98}
    assert [item["destination_pixel"] for item in seam] == [[1.0, 0.0, 0.0]] * 3
    assert [item["lit_pixel_count_on_path"] for item in seam] == [1, 1, 1]

    concurrent = summary["evidence"]["concurrent_frame"]["targets"]
    assert [item["effect_id"] for item in concurrent] == [
        "seam-chase",
        "concurrent-wall-wave",
        "concurrent-ceiling-analog",
    ]
    assert concurrent[0]["pixel_16"] == [1.0, 0.0, 0.0]
    assert concurrent[1]["pixel_0"] != concurrent[0]["pixel_16"]
    assert concurrent[2]["channels"]["g"] > concurrent[2]["channels"]["r"] > 0.0

    fade = {item["timestamp"]: item for item in summary["evidence"]["fade_samples"]}
    assert fade[100.0]["weight"] == 0.0
    assert fade[102.0]["weight"] == 0.5
    assert fade[104.0]["weight"] == 1.0
    assert fade[108.0]["weight"] == 0.5
    assert fade[110.0]["weight"] == 0.0
    assert fade[102.0]["front_pixel_0"] == [0.4, 0.1, 0.05]
    assert fade[104.0]["front_pixel_0"] == [0.8, 0.2, 0.1]
    assert fade[108.0]["front_pixel_0"] == [0.4, 0.1, 0.05]

    music = summary["evidence"]["music_timeline"]
    sync_modes = {item["sync_mode"] for item in music}
    reason_codes = {item["reason_code"] for item in music}
    assert {"beat_sync", "event_sync", "envelope_sync", "free_run"} <= sync_modes
    assert {"BEAT_CONFIDENT", "EVENT_FALLBACK", "ENVELOPE_FALLBACK", "FREE_RUN_FALLBACK"} <= reason_codes
    assert all(item["speed"] > 0.0 for item in music)

    bass = summary["evidence"]["bass_pulse_trace"]
    assert bass[0]["bass_pulse"] > bass[1]["bass_pulse"] > bass[2]["bass_pulse"] > bass[3]["bass_pulse"]
    assert all(item["bass_ambient"] >= 0.78 for item in bass)

    for trace in summary["evidence"]["protocol_sequence_trace"]:
        seq = trace["logical_sequence"]
        assert trace["physical_sequence"] == seq
        assert set(trace["rs485_sequences"]) == {seq & 0xFF}
        assert set(trace["udp_sequences"]) == {seq}

    bounded = summary["evidence"]["bounded_state"]
    assert bounded["runtime_jobs"] == 5
    assert bounded["retained_protocol_trace_frames"] <= 14
    assert bounded["transport_pending_frames"] == 0

    soak = summary["soak_metrics"]
    assert soak["actual_output_fps"] > 30.0
    assert soak["dropped_frames"] == 0
    assert soak["late_frames"] == 0
    assert soak["sequence_mismatches"] == 0
    assert soak["peak_queue_depth"] == 1

    artifact_hashes = summary["artifact_sha256"]
    required = {
        "artifacts/show_acceptance/golden_hashes.json",
        "artifacts/show_acceptance/two_run_digests.json",
        "artifacts/show_acceptance/seam_concurrency_frames.json",
        "artifacts/show_acceptance/music_decision_timeline.json",
        "artifacts/show_acceptance/protocol_sequence_trace.json",
        "artifacts/show_acceptance/benchmark_soak_metrics.json",
        "artifacts/show_acceptance/firmware_build_logs.json",
    }
    assert required <= set(artifact_hashes)
    assert all(len(value) == 64 for value in artifact_hashes.values())
    _assert_finite(summary)

    persisted = json.loads(Path("artifacts/show_acceptance/summary.json").read_text(encoding="utf-8"))
    assert persisted["two_run_digests"] == summary["two_run_digests"]


def _assert_finite(value: object) -> None:
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for item in value.values():
            _assert_finite(item)
    elif isinstance(value, list):
        for item in value:
            _assert_finite(item)
