"""Tests for effect registry show-schema metadata."""

from light_engine.effects import list_effects
from light_engine.effects.base import get_effect_parameter_keys


def test_registered_effects_have_v1_parameter_metadata() -> None:
    effects = set(list_effects())

    assert "chase" in effects
    assert "breath" in effects
    assert get_effect_parameter_keys("chase") >= {
        "speed",
        "width",
        "gap",
        "color_source",
    }
    assert "period" in get_effect_parameter_keys("breath")
