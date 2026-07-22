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
        strip_ids=frozenset({"strip_11", "strip_12", "strip_21", "strip_22"}),
    )


_SHOW_WITH_YAML = {
    "show_id": "test-show",
    "name": "Test",
    "duration_ms": 60000,
    "media_path": "/fake/show.mp4",
    "show_yaml": "/fake/show.yaml",
}

_SHOW_WITH_AUDIO = {
    "show_id": "test-show-audio",
    "name": "Audio Show",
    "duration_ms": 60000,
    "media_path": "/fake/track.mp3",
    "show_yaml": "/fake/show.yaml",
}

_SHOW_NO_YAML = {
    "show_id": "test-show-no-yaml",
    "name": "No YAML",
    "duration_ms": 30000,
    "media_path": "/fake/audio.mp3",
    "show_yaml": None,
}


def _make_mock_proc():
    m = MagicMock()
    m.poll.return_value = None
    m.stderr = iter([])
    return m


# ── on_playback_start ─────────────────────────────────────────────────────────

def test_playback_start_launches_subprocess(adapter):
    with patch("host_services.real_engine_adapter.subprocess.Popen",
               return_value=_make_mock_proc()) as mock_popen:
        adapter.on_playback_start(_SHOW_WITH_YAML, None)

    cmd = mock_popen.call_args[0][0]
    assert "-m" in cmd
    assert "light_engine" in cmd
    assert "--show" in cmd
    assert "/fake/show.yaml" in cmd
    assert "--clock" in cmd
    assert "mpv" in cmd


def test_playback_start_with_audio_file_adds_audio_flag(adapter):
    """mp3 media → --audio flag must be present in the command."""
    with patch("host_services.real_engine_adapter.subprocess.Popen",
               return_value=_make_mock_proc()) as mock_popen:
        adapter.on_playback_start(_SHOW_WITH_AUDIO, None)

    cmd = mock_popen.call_args[0][0]
    assert "--audio" in cmd
    assert "/fake/track.mp3" in cmd


def test_playback_start_no_yaml_skips_subprocess(adapter):
    with patch("host_services.real_engine_adapter.subprocess.Popen") as mock_popen:
        adapter.on_playback_start(_SHOW_NO_YAML, None)
    mock_popen.assert_not_called()


# ── Fix 2: video files must not receive --audio flag ─────────────────────────

def test_playback_start_video_file_no_audio_flag(adapter):
    """mp4 video file must NOT add --audio to the command."""
    with patch("host_services.real_engine_adapter.subprocess.Popen",
               return_value=_make_mock_proc()) as mock_popen:
        adapter.on_playback_start(_SHOW_WITH_YAML, None)

    cmd = mock_popen.call_args[0][0]
    assert "--audio" not in cmd


def test_playback_start_wav_case_insensitive(adapter):
    """WAV (uppercase) is an audio suffix — --audio must be added."""
    show = {**_SHOW_WITH_YAML, "media_path": "/fake/track.WAV"}
    with patch("host_services.real_engine_adapter.subprocess.Popen",
               return_value=_make_mock_proc()) as mock_popen:
        adapter.on_playback_start(show, None)

    cmd = mock_popen.call_args[0][0]
    assert "--audio" in cmd
    assert "/fake/track.WAV" in cmd


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


# ── Problem 4: stderr=PIPE on subprocesses ───────────────────────────────────

def test_playback_popen_uses_stderr_pipe(adapter):
    """on_playback_start must open the subprocess with stderr=PIPE (not DEVNULL)."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stderr = iter([])
    with patch("host_services.real_engine_adapter.subprocess.Popen",
               return_value=mock_proc) as mock_popen:
        adapter.on_playback_start(_SHOW_WITH_YAML, None)

    _, kwargs = mock_popen.call_args
    assert kwargs.get("stderr") == -1, "stderr must be subprocess.PIPE (-1)"


def test_manual_popen_uses_stderr_pipe(adapter):
    """on_manual_command must open the subprocess with stderr=PIPE (not DEVNULL)."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stderr = iter([])
    states = [{"target_id": "strip_11", "effect_type": "static", "color": [1.0, 0.0, 0.0]}]
    with patch("host_services.real_engine_adapter.subprocess.Popen",
               return_value=mock_proc) as mock_popen:
        adapter.on_manual_command(states)

    _, kwargs = mock_popen.call_args
    assert kwargs.get("stderr") == -1, "stderr must be subprocess.PIPE (-1)"


# ── Problem 5: _build_manual_show target filtering ───────────────────────────

def test_build_manual_show_filters_unknown_target():
    """With non-empty strip_ids, targets not in the set are silently skipped."""
    a = RealEngineAdapter(
        profile_path=_PROFILE,
        mpv_socket_path=_SOCKET,
        strip_ids=frozenset({"strip_11"}),
    )
    result = a._build_manual_show([
        {"target_id": "strip_99", "effect_type": "static", "color": [1.0, 1.0, 1.0]},
    ])
    assert result is None, "No known targets → no cues → should return None"


def test_build_manual_show_no_strip_ids_passes_all():
    """With empty strip_ids (degraded mode) every target is included unchanged."""
    a = RealEngineAdapter(
        profile_path=_PROFILE,
        mpv_socket_path=_SOCKET,
        strip_ids=None,
    )
    import yaml, os
    result = a._build_manual_show([
        {"target_id": "anything", "effect_type": "static", "color": [1.0, 1.0, 1.0]},
    ])
    assert result is not None
    with open(result) as f:
        doc = yaml.safe_load(f)
    cue_targets = [c["target"]["id"] for c in doc["show"]["cues"]]
    assert "anything" in cue_targets
    os.unlink(result)
