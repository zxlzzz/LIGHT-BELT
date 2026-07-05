"""Tests for configuration system."""

import os
import pytest
import tempfile
from pathlib import Path

from light_engine.config import Config, ConfigError, validate_range, validate_choice, validate_positive_int


class TestValidators:
    def test_validate_range_ok(self):
        assert validate_range(0.5, "test", "cfg", 0.0, 1.0) == 0.5

    def test_validate_range_low(self):
        with pytest.raises(ConfigError):
            validate_range(-0.1, "test", "cfg", 0.0, 1.0)

    def test_validate_range_high(self):
        with pytest.raises(ConfigError):
            validate_range(1.5, "test", "cfg", 0.0, 1.0)

    def test_validate_choice_ok(self):
        assert validate_choice("a", "test", "cfg", ["a", "b"]) == "a"

    def test_validate_choice_bad(self):
        with pytest.raises(ConfigError):
            validate_choice("c", "test", "cfg", ["a", "b"])

    def test_validate_positive_int_ok(self):
        assert validate_positive_int(5, "test", "cfg") == 5

    def test_validate_positive_int_negative(self):
        with pytest.raises(ConfigError):
            validate_positive_int(-1, "test", "cfg")


class TestConfig:
    def test_load_defaults(self):
        Config.reset()
        config = Config()
        assert config.get("system.version") == "0.1.0"
        assert config.get("system.output_fps") == 30.0
        assert config.get("system.smoothing.max_brightness") == 0.85

    def test_nonexistent_key(self):
        Config.reset()
        config = Config()
        assert config.get("nonexistent.key") is None

    def test_default_value(self):
        Config.reset()
        config = Config()
        assert config.get("nonexistent.key", 42) == 42

    def test_get_or_raise(self):
        Config.reset()
        config = Config()
        with pytest.raises(KeyError):
            config.get_or_raise("nonexistent.key")

    def test_singleton(self):
        Config.reset()
        c1 = Config.get_instance()
        c2 = Config.get_instance()
        assert c1 is c2

    def test_layout_config(self):
        Config.reset()
        config = Config()
        strips = config.get("layout.strips")
        assert len(strips) == 6
        assert strips[0]["id"] == "ceiling_left"

    def test_effects_config(self):
        Config.reset()
        config = Config()
        assert config.get("effects.active") == "demo"

    def test_to_dict(self):
        Config.reset()
        config = Config()
        d = config.to_dict()
        assert "system" in d
        assert "layout" in d
        assert "effects" in d
        assert "outputs" in d

    def test_windows_dev_profile_loads(self):
        Config.reset()
        config = Config(Path("config/profiles/windows_dev.yaml"))
        assert config.get("outputs.mode") == "memory"
        assert config.get("system.clock.mode") == "internal"
        assert config.get("system.platform") == "windows"

    def test_rk3588_production_profile_loads_without_verification_claim(self):
        Config.reset()
        profile = Path("config/profiles/rk3588_production.yaml")
        config = Config(profile)
        assert config.get("outputs.mode") == "production"
        assert config.get("system.clock.mode") == "mpv"
        assert config.get("system.platform") == "linux_arm64"
        text = profile.read_text(encoding="utf-8").lower()
        assert "verified" not in text
