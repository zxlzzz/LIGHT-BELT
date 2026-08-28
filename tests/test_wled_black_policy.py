from __future__ import annotations

import json
from urllib.request import Request

from host_services import engine_adapter, wled_brightness


class _Response:
    def __init__(self, payload: dict | None = None, status: int = 200) -> None:
        self._payload = payload
        self._status = status
        self.closed = False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def close(self) -> None:
        self.closed = True


def _payload(request: Request) -> dict:
    assert request.data is not None
    return json.loads(request.data.decode())


def test_apply_scale_atomically_enables_solid_black(monkeypatch) -> None:
    requests: list[Request] = []
    monkeypatch.setattr(
        wled_brightness.urllib.request,
        "urlopen",
        lambda request, timeout: requests.append(request) or _Response(),
    )

    wled_brightness.apply_scale([{"host": "192.0.2.10"}], 0.5)

    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "http://192.0.2.10/json/state"
    assert _payload(request) == {
        "on": True,
        "bri": 128,
        "transition": 0,
        "seg": [{"id": 0, "on": True, "fx": 0, "col": [[0, 0, 0, 0]]}],
        "v": False,
    }


def test_apply_off_clears_local_fallback_before_master_off(monkeypatch) -> None:
    requests: list[Request] = []
    monkeypatch.setattr(
        wled_brightness.urllib.request,
        "urlopen",
        lambda request, timeout: requests.append(request) or _Response(),
    )

    wled_brightness.apply_off([{"host": "192.0.2.11"}])

    assert _payload(requests[0]) == {
        "on": False,
        "transition": 0,
        "seg": [{"id": 0, "on": True, "fx": 0, "col": [[0, 0, 0, 0]]}],
        "v": False,
    }


def test_boot_policy_rewrites_only_unsafe_boot_defaults(monkeypatch) -> None:
    requests: list[str | Request] = []

    def _urlopen(request: str | Request, timeout: float) -> _Response:
        requests.append(request)
        if isinstance(request, str):
            return _Response({"def": {"on": True, "ps": 7, "bri": 90}})
        return _Response({"success": True})

    monkeypatch.setattr(wled_brightness.urllib.request, "urlopen", _urlopen)

    result = wled_brightness.apply_black_boot_policy([{"host": "192.0.2.12"}])

    assert result == {"192.0.2.12": True}
    assert requests[0] == "http://192.0.2.12/json/cfg"
    assert isinstance(requests[1], Request)
    assert requests[1].full_url == "http://192.0.2.12/json/cfg"
    assert _payload(requests[1]) == {"def": {"on": False, "ps": 0}}


def test_boot_policy_does_not_rewrite_already_safe_config(monkeypatch) -> None:
    requests: list[str | Request] = []
    monkeypatch.setattr(
        wled_brightness.urllib.request,
        "urlopen",
        lambda request, timeout: requests.append(request)
        or _Response({"def": {"on": False, "ps": 0, "bri": 128}}),
    )

    result = wled_brightness.apply_black_boot_policy([{"host": "192.0.2.13"}])

    assert result == {"192.0.2.13": True}
    assert requests == ["http://192.0.2.13/json/cfg"]


def test_host_initialization_provisions_only_enabled_wled_and_forces_off(monkeypatch) -> None:
    devices = [
        {"host": "192.0.2.20", "enabled": True, "device_type": "wled_board"},
        {"host": "192.0.2.21", "enabled": False, "device_type": "wled_board"},
        {"host": "192.0.2.22", "enabled": True, "device_type": "custom_esp32_udp_v3"},
    ]
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_devices", devices)
    monkeypatch.setattr(engine_adapter, "_wled_boot_policy_hosts", set())
    monkeypatch.setattr(
        wled_brightness,
        "apply_black_boot_policy",
        lambda selected, timeout=1.0: calls.append(("boot", selected))
        or {selected[0]["host"]: True},
    )
    monkeypatch.setattr(
        wled_brightness,
        "apply_off",
        lambda selected, timeout=1.0: calls.append(("off", selected)),
    )

    result = engine_adapter.initialize_wled_safe_state(force_off=True)

    assert result == {"192.0.2.20": True}
    assert calls == [("boot", [devices[0]]), ("off", [devices[0]])]

