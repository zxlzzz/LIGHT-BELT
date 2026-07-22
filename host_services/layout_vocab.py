"""Derive target_id and device_id vocabularies from a light_engine Layout.

Functions here are pure: they take a Layout and return plain Python objects.
They are intentionally independent of host_services config so they can be
unit-tested with a fixture Layout without touching real file paths.
"""

from __future__ import annotations

from light_engine.mapping import Layout

STARRY_SKY_TARGET_ID = "starry_sky"

# Chinese display names for known target IDs.
# Targets not listed here fall back to their logical ID (safe for future strips).
TARGET_DISPLAY_NAMES: dict[str, str] = {
    "all":        "全部灯带",
    "strip_11":   "屏幕上方",
    "strip_21":   "屏幕下方",
    "strip_31":   "屏幕左侧",
    "strip_41":   "屏幕右侧",
    "strip_12":   "顶棚边缘",
    "strip_22":   "地面边缘",
    "strip_32":   "左侧舷窗",
    "strip_43":   "右墙波浪一",
    "strip_44":   "右墙波浪二",
    "starry_sky": "星空灯",
}


def _display_name(target_id: str) -> str:
    return TARGET_DISPLAY_NAMES.get(target_id, target_id)


def derive_target_ids(layout: Layout) -> frozenset[str]:
    """All valid target IDs: strip logical IDs from layout + 'all' + 'starry_sky'."""
    return frozenset(s.id for s in layout.strips) | {"all", STARRY_SKY_TARGET_ID}


def derive_capabilities_targets(layout: Layout) -> list[dict]:
    """Return the capabilities targets list: [{target_id, name}, ...].

    'all' comes first, then each strip in layout order, then 'starry_sky'
    with its supported_effects field to distinguish it as a special device.
    Unknown target IDs fall back to using the logical ID as the display name.
    """
    targets: list[dict] = [{"target_id": "all", "name": _display_name("all")}]
    for strip in layout.strips:
        targets.append({"target_id": strip.id, "name": _display_name(strip.id)})
    targets.append({
        "target_id": STARRY_SKY_TARGET_ID,
        "name": _display_name(STARRY_SKY_TARGET_ID),
        "supported_effects": ["twinkle"],
    })
    return targets

def derive_device_list(layout: Layout) -> list[dict]:
    devices = []
    for node in layout.digital_nodes:
        devices.append({
            "device_id": f"node_{node.node_id}",
            "device_type": "wled_board",
            "host": node.host,            # ← 新增
            "status": "offline",
            "last_output_ms": 0,
            "last_seen_ms": 0,
            "connection_confirmed": False,
            "error_code": None,
        })
    return devices