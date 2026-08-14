from __future__ import annotations

import os
from pathlib import Path
import threading
from collections import Counter

import pytest
import yaml

from scripts import resolve_nodes


TEMPLATE = Path("config/profiles/rk3588-host-service.yaml")


def test_resolver_uses_stable_strip_mdns_names_and_disables_unresolved_nodes(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], timeout: int) -> str:
        commands.append(command)
        return "wled-strip-32.local\t192.168.31.50\n" if command[-1] == "wled-strip-32.local" else ""

    output = tmp_path / "wled-ddp-mdns.yaml"
    disabled = resolve_nodes.resolve_profile(TEMPLATE, output, runner)
    profile = yaml.safe_load(output.read_text(encoding="utf-8"))
    nodes = profile["layout"]["digital_nodes"]

    assert disabled == 8
    assert nodes[0]["host"] == "192.168.31.50" and nodes[0]["enabled"] is True
    assert all(node["enabled"] is False for node in nodes[1:])
    assert nodes[1]["host"] == "wled-strip-41.local"
    assert Counter(tuple(command) for command in commands) == Counter(
        ("avahi-resolve", "-4", "-n", f"wled-strip-{strip}.local")
        for strip in ("32", "41", "44", "12", "22", "31", "43", "11", "21")
    )


def test_resolver_has_no_identity_or_old_address_fallback_mechanism() -> None:
    source = Path("scripts/resolve_nodes.py").read_text(encoding="utf-8").lower()
    for forbidden in ("node_macs", "urllib", "http", "cache", "scan", "getaddrinfo"):
        assert forbidden not in source


def test_resolver_refuses_to_overwrite_a_tracked_template(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not overwrite"):
        resolve_nodes.resolve_profile(TEMPLATE, TEMPLATE, lambda command, timeout: "")


def test_resolver_runs_missing_nodes_concurrently_and_keeps_partial_results(tmp_path: Path) -> None:
    started = threading.Event()
    lock = threading.Lock()
    active = 0
    peak_active = 0

    def runner(command: list[str], timeout: int) -> str:
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
            if active >= 2:
                started.set()
        assert started.wait(0.5), "resolver calls were serialized"
        with lock:
            active -= 1
        return "wled-strip-32.local\t192.168.31.50\n" if command[-1] == "wled-strip-32.local" else ""

    output = tmp_path / "wled-ddp-mdns.yaml"
    assert resolve_nodes.resolve_profile(TEMPLATE, output, runner) == 8
    nodes = yaml.safe_load(output.read_text(encoding="utf-8"))["layout"]["digital_nodes"]

    assert peak_active >= 2
    assert nodes[0]["host"] == "192.168.31.50" and nodes[0]["enabled"] is True
    assert all(node["enabled"] is False for node in nodes[1:])


def test_resolver_atomically_replaces_runtime_without_changing_template(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "wled-ddp-mdns.yaml"
    template_before = TEMPLATE.read_bytes()
    observed: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def replace(source: Path, destination: Path) -> None:
        observed.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(resolve_nodes.os, "replace", replace)
    resolve_nodes.resolve_profile(TEMPLATE, output, lambda command, timeout: "")

    assert TEMPLATE.read_bytes() == template_before
    assert observed == [(observed[0][0], output)]
    assert observed[0][0].parent == output.parent
    assert observed[0][0].name.startswith(f".{output.name}.")
    assert observed[0][0].suffix == ".tmp"


def test_resolver_cleans_temporary_file_when_atomic_replace_fails(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "wled-ddp-mdns.yaml"
    output.write_text("previous runtime", encoding="utf-8")
    monkeypatch.setattr(resolve_nodes.os, "replace", lambda source, destination: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        resolve_nodes.resolve_profile(TEMPLATE, output, lambda command, timeout: "")

    assert output.read_text(encoding="utf-8") == "previous runtime"
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


@pytest.mark.parametrize("address", ("not-an-ip", "2001:db8::1", "300.1.1.1", "192.168.1.1:4048"))
def test_resolver_rejects_non_ipv4_avahi_results(address: str) -> None:
    assert resolve_nodes.resolve_avahi(
        "wled-strip-32.local",
        lambda command, timeout: f"wled-strip-32.local\t{address}\n",
    ) is None


def test_malformed_avahi_result_disables_runtime_node(tmp_path: Path) -> None:
    output = tmp_path / "wled-ddp-mdns.yaml"
    resolve_nodes.resolve_profile(
        TEMPLATE,
        output,
        lambda command, timeout: "wled-strip-32.local\t2001:db8::1\n",
    )
    node = yaml.safe_load(output.read_text(encoding="utf-8"))["layout"]["digital_nodes"][0]
    assert node["enabled"] is False
    assert node["host"] == "wled-strip-32.local"
