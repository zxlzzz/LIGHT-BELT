"""Unit tests for host_services/layout_vocab.py.

Builds a mock Layout (matching the dataclass interface) so no real file paths,
Config validation, or hardware are needed.
"""

import pytest
from types import SimpleNamespace

from host_services.layout_vocab import (
    STARRY_SKY_TARGET_ID,
    derive_target_ids,
    derive_capabilities_targets,
    derive_device_list,
)


def _make_strip(strip_id: str):
    return SimpleNamespace(id=strip_id)


def _make_node(node_id: int):
    return SimpleNamespace(node_id=node_id)


def _make_layout(strip_ids=("strip_11", "strip_22"), node_ids=(1, 2)):
    return SimpleNamespace(
        strips=[_make_strip(sid) for sid in strip_ids],
        digital_nodes=[_make_node(nid) for nid in node_ids],
    )


@pytest.fixture(scope="module")
def layout():
    return _make_layout()


# ── derive_target_ids ─────────────────────────────────────────────────────────

def test_derive_target_ids_contains_strips(layout):
    tids = derive_target_ids(layout)
    assert "strip_11" in tids
    assert "strip_22" in tids


def test_derive_target_ids_contains_all(layout):
    assert "all" in derive_target_ids(layout)


def test_derive_target_ids_contains_starry_sky(layout):
    assert STARRY_SKY_TARGET_ID in derive_target_ids(layout)


def test_derive_target_ids_returns_frozenset(layout):
    assert isinstance(derive_target_ids(layout), frozenset)


def test_derive_target_ids_count(layout):
    # 2 strips + "all" + "starry_sky"
    assert len(derive_target_ids(layout)) == 4


# ── derive_capabilities_targets ───────────────────────────────────────────────

def test_derive_capabilities_targets_first_is_all(layout):
    targets = derive_capabilities_targets(layout)
    assert targets[0]["target_id"] == "all"


def test_derive_capabilities_targets_last_is_starry_sky(layout):
    targets = derive_capabilities_targets(layout)
    assert targets[-1]["target_id"] == STARRY_SKY_TARGET_ID


def test_derive_capabilities_targets_starry_sky_has_supported_effects(layout):
    targets = derive_capabilities_targets(layout)
    ss = next(t for t in targets if t["target_id"] == STARRY_SKY_TARGET_ID)
    assert ss["supported_effects"] == ["twinkle"]


def test_derive_capabilities_targets_strips_present(layout):
    targets = derive_capabilities_targets(layout)
    ids = {t["target_id"] for t in targets}
    assert "strip_11" in ids
    assert "strip_22" in ids


def test_derive_capabilities_targets_each_has_name(layout):
    for t in derive_capabilities_targets(layout):
        assert "name" in t
        assert t["name"]  # non-empty


def test_derive_capabilities_targets_known_chinese_names(layout):
    targets = {t["target_id"]: t["name"] for t in derive_capabilities_targets(layout)}
    assert targets["all"] == "全部灯带"
    assert targets["strip_11"] == "屏幕上方"
    assert targets["strip_22"] == "地面边缘"
    assert targets[STARRY_SKY_TARGET_ID] == "星空灯"


def test_derive_capabilities_targets_unknown_strip_falls_back_to_id():
    layout = _make_layout(strip_ids=("strip_99",), node_ids=(1,))
    targets = {t["target_id"]: t["name"] for t in derive_capabilities_targets(layout)}
    assert targets["strip_99"] == "strip_99"


# ── derive_device_list ────────────────────────────────────────────────────────

def test_derive_device_list_node_ids(layout):
    devices = derive_device_list(layout)
    device_ids = {d["device_id"] for d in devices}
    assert "node_1" in device_ids
    assert "node_2" in device_ids


def test_derive_device_list_schema(layout):
    for d in derive_device_list(layout):
        assert d["device_type"] == "wled_board"
        assert d["status"] == "offline"
        assert d["connection_confirmed"] is False
        assert "error_code" in d


def test_derive_device_list_count(layout):
    assert len(derive_device_list(layout)) == 2


def test_derive_device_list_single_node():
    layout = _make_layout(strip_ids=("strip_11",), node_ids=(5,))
    devices = derive_device_list(layout)
    assert len(devices) == 1
    assert devices[0]["device_id"] == "node_5"
