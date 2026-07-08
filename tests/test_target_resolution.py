"""Tests for Phase 13 show target resolution."""

from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.show import (
    Cue,
    EffectSpec,
    TargetResolver,
    TargetSelector,
    TransitionSpec,
    make_scoped_context,
)
from light_engine.models import EffectContext


def _resolver() -> TargetResolver:
    strips = (
        ZoneDef(id="strip_a", pixel_count=3, video_zone="left"),
        ZoneDef(id="strip_b", pixel_count=2, video_zone="right"),
    )
    zones = (
        ZoneDef(id="zone_a", zone_type="rgbcct"),
        ZoneDef(id="zone_b", zone_type="rgbcct"),
    )
    paths = build_virtual_paths(
        [
            {
                "id": "path_ab",
                "segments": [
                    {
                        "strip_id": "strip_a",
                        "source_start": 0,
                        "pixel_count": 2,
                        "direction": "forward",
                        "gap_after_pixels": 1,
                    },
                    {
                        "strip_id": "strip_b",
                        "source_start": 0,
                        "pixel_count": 2,
                        "direction": "reverse",
                    },
                ],
            }
        ],
        {"strip_a": 3, "strip_b": 2},
    )
    return TargetResolver(
        zones,
        strips,
        analog_groups={"warm": ("zone_b", "zone_a")},
        digital_groups={"edge": ("strip_b", "strip_a")},
        virtual_paths=paths,
    )


def test_resolves_all_phase_11_target_kinds() -> None:
    resolver = _resolver()

    assert [z.id for z in resolver.resolve(TargetSelector("analog_zone", id="zone_a")).analog_zones] == ["zone_a"]
    assert [s.id for s in resolver.resolve(TargetSelector("digital_strip", id="strip_b")).digital_strips] == ["strip_b"]
    assert [z.id for z in resolver.resolve(TargetSelector("analog_group", id="warm")).analog_zones] == ["zone_b", "zone_a"]
    assert [s.id for s in resolver.resolve(TargetSelector("digital_group", id="edge")).digital_strips] == ["strip_b", "strip_a"]
    assert [z.id for z in resolver.resolve(TargetSelector("all_analog")).analog_zones] == ["zone_a", "zone_b"]
    assert [s.id for s in resolver.resolve(TargetSelector("all_digital")).digital_strips] == ["strip_a", "strip_b"]

    all_target = resolver.resolve(TargetSelector("all"))
    assert [z.id for z in all_target.analog_zones] == ["zone_a", "zone_b"]
    assert [s.id for s in all_target.digital_strips] == ["strip_a", "strip_b"]


def test_virtual_path_resolves_to_global_path_view() -> None:
    resolved = _resolver().resolve(TargetSelector("virtual_path", id="path_ab"))

    assert resolved.virtual_path is not None
    assert resolved.virtual_path.total_length == 5
    assert [s.id for s in resolved.digital_strips] == ["strip_a", "strip_b"]

    scoped = make_scoped_context(
        EffectContext(timestamp=1.0, delta_time=0.1),
        resolved,
    )
    assert scoped.mode_parameters["strip_defs"] == (
        {
            "id": "__virtual_path__:path_ab",
            "pixel_count": 5,
            "video_zone": "center",
            "direction": "forward",
        },
    )
    assert scoped.mode_parameters["zone_defs"] == ()


def test_scoped_context_contains_cue_metadata_and_effect_parameters() -> None:
    resolved = _resolver().resolve(TargetSelector("analog_zone", id="zone_a"))
    cue = Cue(
        id="breath-zone-a",
        start=0.0,
        end=5.0,
        priority=3,
        target=TargetSelector("analog_zone", id="zone_a"),
        effect=EffectSpec(
            mode="fixed",
            name="breath",
            parameters={"period": 2.5, "min_brightness": 0.2},
        ),
        transition=TransitionSpec(blend="add"),
    )

    scoped = make_scoped_context(
        EffectContext(timestamp=1.0, delta_time=0.1),
        resolved,
        cue=cue,
        declaration_index=4,
    )

    assert scoped.mode_parameters["strip_defs"] == ()
    assert scoped.mode_parameters["zone_defs"][0]["id"] == "zone_a"
    assert scoped.mode_parameters["period"] == 2.5
    assert scoped.mode_parameters["min_brightness"] == 0.2
    assert scoped.mode_parameters["cue_id"] == "breath-zone-a"
    assert scoped.mode_parameters["priority"] == 3
    assert scoped.mode_parameters["declaration_index"] == 4
    assert scoped.mode_parameters["blend"] == "add"


def test_missing_target_raises_instead_of_materializing_black() -> None:
    resolver = _resolver()

    try:
        resolver.resolve(TargetSelector("digital_strip", id="missing"))
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing digital strip should not resolve")
