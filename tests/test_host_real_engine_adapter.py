"""Unit tests for host_services/real_engine_adapter.py.

All subprocess and socket calls are monkeypatched.  No real processes start.
"""

import threading
from unittest.mock import MagicMock, patch, call

import pytest

from host_services.real_engine_adapter import RealEngineAdapter


_PROFILE = "/fake/profile.yaml"
_SOCKET = "/fake/mpv.sock"


@pytest.fixture
def adapter():
    return RealEngineAdapter(
        profile_path=_PROFILE,
        mpv_socket_path=_SOCKET,
        python_executable="python",
    )


_SHOW_WITH_YAML = {
    "show_id": "test-show",
    "name": "Test",
    "duration_ms": 60000,
    "media_path": "/fake/show.mp4",
    "show_yaml": "/fake/show.yaml",
}

_SHOW_NO_YAML = {
    "show_id": "test-show-no-yaml",
    "name": "No YAML",
    "duration_ms": 30000,
    "media_path": "/fake/audio.mp3",
    "show_yaml": None,
}


# ── on_playback_start ─────────────────────────────────────────────────────────

def test_playback_start_launches_subprocess(adapter):
    with patch("host_services.real_engine_adapter.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        adapter.on_playback_start(_SHOW_WITH_YAML, None)

    cmd = mock_popen.call_args[0][0]
    assert "-m" in cmd
    assert "light_engine" in cmd
    assert "--show" in cmd
    assert "/fake/show.yaml" in cmd
    assert "--clock" in cmd
    assert "mpv" in cmd


def test_playback_start_with_media_adds_audio_flag(adapter):
    with patch("host_services.real_engine_adapter.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        adapter.on_playback_start(_SHOW_WITH_YAML, None)

    cmd = mock_popen.call_args[0][0]
    assert "--audio" in cmd
    assert "/fake/show.mp4" in cmd


def test_playback_start_no_yaml_skips_subprocess(adapter):
    with patch("host_services.real_engine_adapter.subprocess.Popen") as mock_popen:
        adapter.on_playback_start(_SHOW_NO_YAML, None)
    mock_popen.assert_not_called()


# ── on_playback_stop ──────────────────────────────────────────────────────────

def test_playback_stop_terminates_process(adapter):
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    adapter._playback_proc = mock_proc

    with patch("host_services.starry_sky.ensure_off"):
        adapter.on_playback_stop()

    mock_proc.terminate.assert_called_once()


def test_playback_stop_calls_ensure_off(adapter):
    with patch("host_services.real_engine_adapter.subprocess.Popen", return_value=MagicMock()):
        adapter.on_playback_start(_SHOW_WITH_YAML, None)

    with patch("host_services.starry_sky.ensure_off") as mock_off:
        adapter.on_playback_stop()

    mock_off.assert_called_once()


# ── on_manual_command ─────────────────────────────────────────────────────────

def test_manual_command_launches_subprocess(adapter):
    states = [{"target_id": "strip_11", "effect_type": "static", "color": [1.0, 0.0, 0.0]}]
    with patch("host_services.real_engine_adapter.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        adapter.on_manual_command(states)

    cmd = mock_popen.call_args[0][0]
    assert "--clock" in cmd
    assert "internal" in cmd


def test_manual_command_replaces_previous_manual(adapter):
    states = [{"target_id": "strip_11", "effect_type": "static", "color": [1.0, 1.0, 1.0]}]
    mock_proc1 = MagicMock()
    mock_proc1.poll.return_value = None
    adapter._manual_proc = mock_proc1

    with patch("host_services.real_engine_adapter.subprocess.Popen", return_value=MagicMock()):
        adapter.on_manual_command(states)

    mock_proc1.terminate.assert_called_once()


def test_manual_command_skips_all_target(adapter):
    states = [{"target_id": "all", "effect_type": "static", "color": [1.0, 1.0, 1.0]}]
    with patch("host_services.real_engine_adapter.subprocess.Popen") as mock_popen:
        adapter.on_manual_command(states)
    # No cues generated for "all"; subprocess should not launch.
    mock_popen.assert_not_called()


# ── shutdown ──────────────────────────────────────────────────────────────────

def test_shutdown_stops_both_procs(adapter):
    p1 = MagicMock()
    p1.poll.return_value = None
    p2 = MagicMock()
    p2.poll.return_value = None
    adapter._playback_proc = p1
    adapter._manual_proc = p2

    with patch("host_services.starry_sky.ensure_off"):
        adapter.shutdown()

    p1.terminate.assert_called_once()
    p2.terminate.assert_called_once()


def test_shutdown_calls_ensure_off(adapter):
    with patch("host_services.starry_sky.ensure_off") as mock_off:
        adapter.shutdown()
    mock_off.assert_called_once()
