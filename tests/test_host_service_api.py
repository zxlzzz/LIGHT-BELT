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
        json={"target_id": "ceiling_left", "brightness": 0.1},
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
            "entries": [{"target_id": "ceiling_left", "brightness": 0.05}],
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
