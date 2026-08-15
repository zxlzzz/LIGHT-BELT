from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from host_services import config as host_config
from host_services import engine_adapter
from host_services import wled_brightness


def test_default_host_profile_is_the_wled_runtime_profile() -> None:
    assert Path(host_config._DEFAULT_PROFILE).resolve() == host_config.WLED_RUNTIME_PROFILE.resolve()
    assert host_config.WLED_RUNTIME_PROFILE == Path("config/runtime/wled-ddp-mdns.yaml").resolve()


def test_real_mode_resolves_only_the_default_wled_runtime_profile(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(host_config.WLED_RUNTIME_PROFILE))
    monkeypatch.setattr(
        engine_adapter.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0, stderr=""),
    )

    engine_adapter._run_resolve_nodes()

    assert len(calls) == 1
    assert calls[0][1:] == [
        str(Path("scripts/resolve_nodes.py").resolve()),
        "--template", str(host_config.WLED_TEMPLATE_PROFILE),
        "--out", str(host_config.WLED_RUNTIME_PROFILE),
    ]


def test_real_mode_custom_udp_v3_profile_does_not_run_wled_resolver(monkeypatch) -> None:
    calls: list[list[str]] = []
    maintenance = Path("config/profiles/udp-v3-nine-strip-maintenance.yaml").resolve()
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(maintenance))
    monkeypatch.setattr(engine_adapter.subprocess, "run", lambda *args, **kwargs: calls.append(args[0]))

    engine_adapter._run_resolve_nodes()

    assert calls == []


def test_maintenance_profile_derives_custom_udp_v3_devices(monkeypatch) -> None:
    monkeypatch.setattr(
        engine_adapter,
        "ENGINE_PROFILE_PATH",
        str(Path("config/profiles/udp-v3-nine-strip-maintenance.yaml").resolve()),
    )
    from light_engine.config import Config
    Config.reset()

    _, _, devices = engine_adapter._load_layout_vocab()

    assert len(devices) == 9
    assert {device["device_type"] for device in devices} == {"custom_esp32_udp_v3"}


def test_real_mode_wled_resolver_nonzero_exit_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(host_config.WLED_RUNTIME_PROFILE))
    monkeypatch.setattr(
        engine_adapter.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=7, stderr="resolver diagnostic"),
    )

    with pytest.raises(RuntimeError, match="7: resolver diagnostic"):
        engine_adapter._run_resolve_nodes()


def test_real_mode_wled_resolver_timeout_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(host_config.WLED_RUNTIME_PROFILE))
    monkeypatch.setattr(
        engine_adapter.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("resolve_nodes", 30)),
    )

    with pytest.raises(RuntimeError, match="timed out"):
        engine_adapter._run_resolve_nodes()


def test_disabled_devices_are_never_probed_or_sent_http_output(monkeypatch) -> None:
    disabled = {
        "host": "wled-strip-32.local", "enabled": False, "status": "online",
        "connection_confirmed": True, "error_code": None, "last_output_ms": 17,
        "device_type": "wled_board",
    }
    enabled = {
        "host": "192.168.31.50", "enabled": True, "last_output_ms": 0,
        "device_type": "wled_board",
    }
    monkeypatch.setattr(engine_adapter, "_devices", [disabled, enabled])
    calls: list[object] = []
    monkeypatch.setattr(engine_adapter.urllib.request, "urlopen", lambda *args, **kwargs: calls.append(args) or None)
    monkeypatch.setattr(engine_adapter, "_now_ms", lambda: 99)
    monkeypatch.setattr(wled_brightness, "apply_scale", lambda devices, *args: calls.append(("scale", devices)))
    monkeypatch.setattr(wled_brightness, "apply_off", lambda devices, *args: calls.append(("off", devices)))

    engine_adapter._probe_devices()
    engine_adapter._mark_devices_output()
    engine_adapter._push_brightness_scale()
    engine_adapter._push_wled_off()

    assert disabled["status"] == "offline"
    assert disabled["connection_confirmed"] is False
    assert disabled["error_code"] == "MDNS_UNRESOLVED"
    assert disabled["last_output_ms"] == 17
    assert enabled["last_output_ms"] == 99
    assert all("wled-strip-32.local" not in str(call) for call in calls)


def test_enabled_custom_udp_v3_device_skips_wled_http_but_records_output(monkeypatch) -> None:
    custom = {
        "host": "192.0.2.31", "enabled": True, "device_type": "custom_esp32_udp_v3",
        "status": "offline", "connection_confirmed": False, "error_code": None,
        "last_output_ms": 0,
    }
    monkeypatch.setattr(engine_adapter, "_devices", [custom])
    calls: list[object] = []
    monkeypatch.setattr(engine_adapter.urllib.request, "urlopen", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(engine_adapter, "_now_ms", lambda: 123)
    monkeypatch.setattr(wled_brightness, "apply_scale", lambda *args: calls.append(("scale", args)))
    monkeypatch.setattr(wled_brightness, "apply_off", lambda *args: calls.append(("off", args)))

    engine_adapter._probe_devices()
    engine_adapter._push_brightness_scale()
    engine_adapter._push_wled_off()
    engine_adapter._mark_devices_output()

    assert calls == []
    assert custom["status"] == "offline"
    assert custom["last_output_ms"] == 123
