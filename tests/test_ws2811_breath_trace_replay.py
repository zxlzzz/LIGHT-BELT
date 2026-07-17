"""Frozen breath trace preparation and replay-file contracts."""

from scripts.replay_ws2811_breath_trace import (
    DEFAULT_PROFILE,
    DEFAULT_SHOW,
    build_trace,
    read_trace,
    write_trace,
)

EXPECTED_TRACE_SHA256 = (
    "A07C59FD0AA9AD18E8BE1FD421CAFFBAF5E46947D8B1956E2ED016BAB7431436"
)


def test_frozen_breath_trace_round_trips_without_semantic_drift(tmp_path) -> None:
    datagrams, oracle = build_trace(DEFAULT_PROFILE, DEFAULT_SHOW)
    assert oracle.logical_frames == 600
    assert oracle.active_frames == 450
    assert len(oracle.visible_levels) == 32
    assert oracle.visible_levels[0] == 5
    assert oracle.visible_levels[-1] == 37
    assert oracle.trace_sha256 == EXPECTED_TRACE_SHA256

    path = tmp_path / "breath-trace.json"
    write_trace(path, datagrams, oracle)
    loaded, loaded_oracle = read_trace(path)
    assert loaded == datagrams
    assert loaded_oracle == oracle
