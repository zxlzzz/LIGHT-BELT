"""
Smoke tests for host_services API.

All tests use FastAPI TestClient and in-memory state only.
No mpv, no hardware, no filesystem (shows manifest is monkeypatched).
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from host_services.main import app
from host_services import engine_adapter


@pytest.fixture(autouse=True)
def reset_engine_state(monkeypatch):
    """Reset shared module-level state before each test."""
    monkeypatch.setattr(engine_adapter, "_shows", [
        {
            "show_id": "test-show",
            "name": "Test Show",
            "duration_ms": 60000,
            "description": "Smoke-test fixture show",
            "media_path": "/dev/null",
        }
    ])
    monkeypatch.setattr(engine_adapter, "_scenes", {})
    monkeypatch.setattr(engine_adapter, "_save_scenes", lambda: None)
    monkeypatch.setattr(engine_adapter, "_manual_targets", {})
    monkeypatch.setitem(engine_adapter._state, "playback_state", "idle")
    monkeypatch.setitem(engine_adapter._state, "show_id", None)
    monkeypatch.setitem(engine_adapter._state, "position_ms", 0)
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 0)
    monkeypatch.setitem(engine_adapter._state, "scene_id", None)
    monkeypatch.setitem(engine_adapter._state, "volume", 0.5)
    monkeypatch.setitem(engine_adapter._state, "muted", False)
    monkeypatch.setitem(engine_adapter._state, "brightness", 1.0)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


_PAIR_BODY = {
    "pairing_code": "123456",
    "client_id": "test-client",
    "client_name": "Test Client",
    "client_type": "debug",
    "app_version": "1.0",
}


@pytest.fixture()
def auth_headers(client):
    r = client.post("/api/v1/auth/pair", json=_PAIR_BODY)
    assert r.status_code == 200
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Status ────────────────────────────────────────────────────────────────────

def test_status(client):
    r = client.get("/api/v1/status")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["data"]["service"] == "light-belt-host"
    assert "api_version" in d["data"]


# ── Auth / pair ───────────────────────────────────────────────────────────────

def test_pair_success(client):
    r = client.post("/api/v1/auth/pair", json=_PAIR_BODY)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "access_token" in d
    assert "refresh_token" in d
    assert d["token_type"] == "Bearer"


def test_pair_wrong_code(client):
    body = {**_PAIR_BODY, "pairing_code": "000000"}
    r = client.post("/api/v1/auth/pair", json=body)
    assert r.status_code == 400


def test_pair_invalid_client_type(client):
    body = {**_PAIR_BODY, "client_type": "unknown"}
    r = client.post("/api/v1/auth/pair", json=body)
    assert r.status_code == 400


# ── State ─────────────────────────────────────────────────────────────────────

def test_state(client, auth_headers):
    r = client.get("/api/v1/state", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "playback_state" in d
    assert "devices" in d


# ── Shows ─────────────────────────────────────────────────────────────────────

def test_shows_listed(client, auth_headers):
    r = client.get("/api/v1/shows", headers=auth_headers)
    assert r.status_code == 200
    shows = r.json()["data"]["shows"]
    assert len(shows) == 1
    assert shows[0]["show_id"] == "test-show"


def test_shows_no_media_path(client, auth_headers):
    r = client.get("/api/v1/shows", headers=auth_headers)
    shows = r.json()["data"]["shows"]
    for s in shows:
        assert "media_path" not in s


# ── Capabilities ──────────────────────────────────────────────────────────────

def test_capabilities(client, auth_headers):
    r = client.get("/api/v1/capabilities", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "targets" in d
    assert "effects" in d
    assert "websocket" in d
    assert "supports" in d


# ── Playback: play + stop ─────────────────────────────────────────────────────

def test_playback_play_stop(client, auth_headers, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "test-show"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "playing"
    mock_mpv.play_file.assert_called_once_with("/dev/null")

    r = client.post("/api/v1/playback/stop", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "stopped"


def test_playback_play_unknown_show(client, auth_headers):
    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "no-such-show"},
        headers=auth_headers,
    )
    assert r.status_code == 404


# ── Lights ────────────────────────────────────────────────────────────────────

def test_lights_set_brightness(client, auth_headers):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": 0.5},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["brightness"] == 0.5


def test_lights_set_unknown_target(client, auth_headers):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "nonexistent", "brightness": 0.5},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_lights_set_missing_params(client, auth_headers):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all"},
        headers=auth_headers,
    )
    assert r.status_code == 400


# ── Audio ─────────────────────────────────────────────────────────────────────

def test_audio_get(client, auth_headers):
    r = client.get("/api/v1/audio", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "volume" in d
    assert "muted" in d


def test_audio_set_volume(client, auth_headers):
    r = client.post(
        "/api/v1/audio/set",
        json={"volume": 0.8},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["volume"] == pytest.approx(0.8)


def test_audio_set_muted(client, auth_headers):
    r = client.post(
        "/api/v1/audio/set",
        json={"muted": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["muted"] is True


# ── Scenes: save + apply + delete ─────────────────────────────────────────────

def test_scenes_save_apply_delete(client, auth_headers):
    # save
    r = client.post(
        "/api/v1/scenes/save",
        json={
            "name": "Smoke Scene",
            "entries": [{"target_id": "all", "brightness": 0.7}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    scene_id = r.json()["data"]["scene_id"]
    assert scene_id

    # list
    r = client.get("/api/v1/scenes", headers=auth_headers)
    assert r.status_code == 200
    ids = [s["scene_id"] for s in r.json()["data"]["scenes"]]
    assert scene_id in ids

    # apply
    r = client.post(
        "/api/v1/scenes/apply",
        json={"scene_id": scene_id},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["accepted"] is True

    # delete
    r = client.post(
        "/api/v1/scenes/delete",
        json={"scene_id": scene_id},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] is True


def test_scene_apply_not_found(client, auth_headers):
    r = client.post(
        "/api/v1/scenes/apply",
        json={"scene_id": "no-such-scene"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_scene_delete_not_found(client, auth_headers):
    r = client.post(
        "/api/v1/scenes/delete",
        json={"scene_id": "no-such-scene"},
        headers=auth_headers,
    )
    assert r.status_code == 404


# ── Audio: mpv IPC sync (item 8) ─────────────────────────────────────────────

def test_audio_set_calls_mpv_when_running(client, auth_headers, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    r = client.post(
        "/api/v1/audio/set",
        json={"volume": 0.6, "muted": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    mock_mpv.set_volume.assert_called_once_with(0.6)
    mock_mpv.set_mute.assert_called_once_with(True)


def test_audio_set_no_mpv_still_succeeds(client, auth_headers, monkeypatch):
    monkeypatch.setattr(engine_adapter, "_mpv", None)

    r = client.post(
        "/api/v1/audio/set",
        json={"volume": 0.3},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["volume"] == pytest.approx(0.3)


def test_audio_set_volume_scale_to_mpv(client, auth_headers, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    client.post("/api/v1/audio/set", json={"volume": 1.0}, headers=auth_headers)
    mock_mpv.set_volume.assert_called_once_with(1.0)
    # MpvClient.set_volume internally multiplies by 100 — verify via the method
    from host_services.engine_adapter import MpvClient
    sent = []
    mc = MpvClient.__new__(MpvClient)
    mc._send = lambda cmd: sent.append(cmd) or {}
    mc.set_volume(0.75)
    assert sent == [["set_property", "volume", 75.0]]


# ── Playback: start_position_ms > duration_ms → 400 (item 9) ────────────────

def test_playback_play_start_beyond_duration(client, auth_headers, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "test-show", "start_position_ms": 999999},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ARGUMENT"


# ── Lights: master state only for target "all" (item 10) ─────────────────────

def test_lights_set_non_all_does_not_change_master_state(client, auth_headers):
    # record the master brightness before
    r = client.get("/api/v1/state", headers=auth_headers)
    before = r.json()["data"]["brightness"]

    # set brightness on a specific (non-all) target
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "strip_11", "brightness": 0.1},
        headers=auth_headers,
    )
    assert r.status_code == 200

    # master brightness in /state must be unchanged
    r = client.get("/api/v1/state", headers=auth_headers)
    assert r.json()["data"]["brightness"] == before


def test_lights_set_all_updates_master_state(client, auth_headers):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": 0.42},
        headers=auth_headers,
    )
    assert r.status_code == 200

    r = client.get("/api/v1/state", headers=auth_headers)
    assert r.json()["data"]["brightness"] == pytest.approx(0.42)


# ── Scene apply: only "all" entries touch master state (item 10) ─────────────

def test_scene_apply_non_all_entry_does_not_change_master_state(client, auth_headers):
    # save scene with a non-"all" entry
    r = client.post(
        "/api/v1/scenes/save",
        json={
            "name": "Zone scene",
            "entries": [{"target_id": "strip_11", "brightness": 0.05}],
        },
        headers=auth_headers,
    )
    scene_id = r.json()["data"]["scene_id"]

    before = client.get("/api/v1/state", headers=auth_headers).json()["data"]["brightness"]

    client.post("/api/v1/scenes/apply", json={"scene_id": scene_id}, headers=auth_headers)

    after = client.get("/api/v1/state", headers=auth_headers).json()["data"]["brightness"]
    assert after == before


def test_scene_apply_all_entry_updates_master_state(client, auth_headers):
    r = client.post(
        "/api/v1/scenes/save",
        json={
            "name": "Master scene",
            "entries": [{"target_id": "all", "brightness": 0.33}],
        },
        headers=auth_headers,
    )
    scene_id = r.json()["data"]["scene_id"]

    client.post("/api/v1/scenes/apply", json={"scene_id": scene_id}, headers=auth_headers)

    after = client.get("/api/v1/state", headers=auth_headers).json()["data"]["brightness"]
    assert after == pytest.approx(0.33)


# ── Round-2 fixes ─────────────────────────────────────────────────────────────

def test_lights_set_color_only(client, auth_headers):
    """lights/set with only color (no brightness/CT) must return 200."""
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "color": {"r": 255, "g": 0, "b": 128}},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["color"] == {"r": 255, "g": 0, "b": 128}


def test_playback_play_clears_scene_id(client, auth_headers, monkeypatch):
    """Starting playback must clear scene_id in state."""
    monkeypatch.setitem(engine_adapter._state, "scene_id", "some-scene")
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post("/api/v1/playback/play", json={"show_id": "test-show"}, headers=auth_headers)
    assert r.status_code == 200
    assert engine_adapter._state["scene_id"] is None


def test_ensure_mpv_stale_socket(monkeypatch):
    """_ensure_mpv must detect a stale socket, remove it, and restart mpv."""
    exists_calls = []

    def mock_exists(p):
        # First call: socket appears to exist (stale).
        # Subsequent calls: socket is gone (after unlink) → triggers mpv start.
        exists_calls.append(p)
        return len(exists_calls) == 1

    unlinked = []
    mock_probe = MagicMock()
    mock_probe.connect.side_effect = ConnectionRefusedError("stale")

    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_popen = MagicMock(return_value=mock_proc)

    monkeypatch.setattr(engine_adapter.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_mpv_proc", None)
    monkeypatch.setattr(engine_adapter.os.path, "exists", mock_exists)
    monkeypatch.setattr(engine_adapter.os, "makedirs", MagicMock())
    monkeypatch.setattr(engine_adapter.os, "unlink", lambda p: unlinked.append(p))
    monkeypatch.setattr(engine_adapter.socket, "socket", MagicMock(return_value=mock_probe))
    monkeypatch.setattr(engine_adapter.subprocess, "Popen", mock_popen)
    monkeypatch.setattr(engine_adapter, "_wait_until", lambda *a, **kw: True)

    result = engine_adapter._ensure_mpv()

    assert result is not None
    assert len(unlinked) == 1           # stale socket was removed
    assert mock_popen.called            # mpv was relaunched


# ── New: color params passed through (problems 1 & 2) ────────────────────────

def test_effects_set_with_color(client, auth_headers):
    r = client.post(
        "/api/v1/effects/set",
        json={
            "target_id": "all",
            "effect_type": "static",
            "params": {"color": {"r": 255, "g": 128, "b": 0}},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["effect_type"] == "static"
    assert data["params"]["color"] == {"r": 255, "g": 128, "b": 0}


def test_lights_set_with_color(client, auth_headers):
    r = client.post(
        "/api/v1/lights/set",
        json={
            "target_id": "all",
            "brightness": 0.8,
            "color": {"r": 100, "g": 200, "b": 50},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["brightness"] == pytest.approx(0.8)
    assert data["color"] == {"r": 100, "g": 200, "b": 50}


def test_playback_play_no_media(client, auth_headers, monkeypatch):
    monkeypatch.setattr(engine_adapter, "_shows", [{
        "show_id": "no-media-show",
        "name": "No Media Show",
        "duration_ms": 30000,
        "description": None,
        "media_path": None,
    }])
    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "no-media-show"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "playing"


# ── Round-3 fixes ─────────────────────────────────────────────────────────────

def test_global_exception_handler_returns_structured_error(monkeypatch):
    """Problem 2: unhandled exceptions must return ok=false JSON (not bare 500)."""
    def _boom(*_a, **_kw):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(engine_adapter, "get_state", _boom)

    # raise_server_exceptions=False lets the FastAPI exception handler respond
    # instead of propagating the exception to the test process.
    with TestClient(app, raise_server_exceptions=False) as c:
        # Acquire a token via pairing so we have valid auth headers.
        pair = c.post("/api/v1/auth/pair", json=_PAIR_BODY)
        token = pair.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = c.get("/api/v1/state", headers=headers)

    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "RuntimeError" in body["error"]["message"]
    assert "request_id" in body


def test_playback_play_mpv_unavailable_returns_503(client, auth_headers, monkeypatch):
    """Problem 3: MpvUnavailableError must surface as 503 MPV_UNAVAILABLE."""
    from host_services.engine_adapter import MpvUnavailableError

    def _raise(*_a, **_kw):
        raise MpvUnavailableError("mpv not found")
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", _raise)

    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "test-show"},
        headers=auth_headers,
    )

    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "MPV_UNAVAILABLE"


# ── Fix 1: Pydantic 422 → project envelope 400 ───────────────────────────────

def test_validation_error_missing_field_returns_envelope(client):
    """Missing required field must return ok=false INVALID_ARGUMENT at 400, not 422."""
    r = client.post("/api/v1/auth/pair", json={"pairing_code": "123456"})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert "validation_errors" in body["error"].get("details", {})


def test_validation_error_wrong_type_returns_envelope(client, auth_headers):
    """Wrong field type (brightness='abc') must return INVALID_ARGUMENT envelope at 400."""
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": "abc"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"


def test_validation_error_no_content_type_returns_envelope(client, auth_headers):
    """POST with body but no Content-Type must return INVALID_ARGUMENT envelope at 400."""
    r = client.post(
        "/api/v1/lights/set",
        content=b'{"target_id": "all", "brightness": 0.5}',
        headers={**auth_headers, "Content-Type": "text/plain"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"


# ── Fix 3: ws_url uses request Host header ────────────────────────────────────

def test_ws_ticket_url_uses_request_host(client, auth_headers):
    """ws_url must use the Host header from the request, not hardcoded 0.0.0.0."""
    r = client.post(
        "/api/v1/session/ws-ticket",
        json={"subscribe": ["heartbeat"]},
        headers={**auth_headers, "host": "cabin.local:8443"},
    )
    assert r.status_code == 200
    ws_url = r.json()["data"]["ws_url"]
    assert "cabin.local" in ws_url
    assert "0.0.0.0" not in ws_url


# ── Fix 4: devices last_output_ms is 0 on start, updated after lights/set ────

def test_devices_last_output_ms_zero_on_start(client, auth_headers, monkeypatch):
    """Before any command, last_output_ms and last_seen_ms must be 0."""
    fake_device = {
        "device_id": "node_1", "device_type": "wled_board",
        "status": "online",
        "last_output_ms": 0, "last_seen_ms": 0,
        "connection_confirmed": True, "error_code": None,
    }
    monkeypatch.setattr(engine_adapter, "_devices", [fake_device])

    r = client.get("/api/v1/state", headers=auth_headers)
    assert r.status_code == 200
    devices = r.json()["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["last_output_ms"] == 0
    assert devices[0]["last_seen_ms"] == 0


def test_devices_last_output_ms_updated_after_lights_set(client, auth_headers, monkeypatch):
    """After lights/set, last_output_ms must be non-zero."""
    fake_device = {
        "device_id": "node_1", "device_type": "wled_board",
        "status": "online",
        "last_output_ms": 0, "last_seen_ms": 0,
        "connection_confirmed": True, "error_code": None,
    }
    monkeypatch.setattr(engine_adapter, "_devices", [fake_device])

    client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": 0.5},
        headers=auth_headers,
    )

    r = client.get("/api/v1/state", headers=auth_headers)
    devices = r.json()["data"]["devices"]
    assert devices[0]["last_output_ms"] > 0


# ── Fix 5: CORS middleware ────────────────────────────────────────────────────

def test_cors_header_present(client):
    """Requests with Origin header must get Access-Control-Allow-Origin in response."""
    r = client.get("/api/v1/status", headers={"Origin": "http://cabin.local"})
    assert r.status_code == 200
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}
