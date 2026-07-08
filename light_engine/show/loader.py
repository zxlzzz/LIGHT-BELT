"""Strict YAML loader and validator for authored shows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from light_engine.effects import list_effects
from light_engine.effects.base import get_effect_parameter_keys
from light_engine.show.models import (
    AudioControlSpec,
    Cue,
    EffectSpec,
    ShowDefinition,
    TargetSelector,
    TransitionSpec,
)


TARGET_KINDS = frozenset(
    {
        "analog_zone",
        "digital_strip",
        "analog_group",
        "digital_group",
        "virtual_path",
        "all_analog",
        "all_digital",
        "all",
    }
)
BLEND_MODES = frozenset({"replace", "add", "max", "alpha"})
EFFECT_MODES = frozenset({"fixed", "adaptive"})
AUDIO_STATES = frozenset(
    {
        "silence",
        "calm",
        "flowing",
        "ambient",
        "rhythmic",
        "energetic",
        "impact",
        "transition",
    }
)


class ShowValidationError(ValueError):
    """Path-aware show validation error."""

    def __init__(self, path: str, value: Any, reason: str):
        self.path = path
        self.value = value
        self.reason = reason
        super().__init__(f"{path}: {value!r} invalid, {reason}")


@dataclass(frozen=True)
class TargetCatalog:
    """Explicit target catalog used to resolve authored show targets."""

    analog_zones: frozenset[str] = frozenset()
    digital_strips: frozenset[str] = frozenset()
    analog_groups: Mapping[str, frozenset[str]] | frozenset[str] = frozenset()
    digital_groups: Mapping[str, frozenset[str]] | frozenset[str] = frozenset()
    virtual_paths: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        analog_zones: Iterable[str] = (),
        digital_strips: Iterable[str] = (),
        analog_groups: Mapping[str, Iterable[str]] | Iterable[str] = (),
        digital_groups: Mapping[str, Iterable[str]] | Iterable[str] = (),
        virtual_paths: Iterable[str] = (),
    ):
        object.__setattr__(self, "analog_zones", frozenset(analog_zones))
        object.__setattr__(self, "digital_strips", frozenset(digital_strips))
        object.__setattr__(
            self, "analog_groups", self._freeze_groups(analog_groups)
        )
        object.__setattr__(
            self, "digital_groups", self._freeze_groups(digital_groups)
        )
        object.__setattr__(self, "virtual_paths", frozenset(virtual_paths))

    @staticmethod
    def _freeze_groups(
        groups: Mapping[str, Iterable[str]] | Iterable[str],
    ) -> Mapping[str, frozenset[str]] | frozenset[str]:
        if isinstance(groups, Mapping):
            return {key: frozenset(value) for key, value in groups.items()}
        return frozenset(groups)


def load_show(path: Path, target_catalog: TargetCatalog) -> ShowDefinition:
    """Load and strictly validate a versioned show YAML file."""
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    return validate_show_data(data, target_catalog)


def validate_show_data(data: Any, target_catalog: TargetCatalog) -> ShowDefinition:
    root = _mapping(data, "show")
    _unknown(root, {"schema_version", "show"}, "show")
    version = _int(root.get("schema_version"), "show.schema_version", minimum=1)
    if version != 1:
        raise ShowValidationError("show.schema_version", version, "must be 1")
    show = _mapping(root.get("show"), "show.show")
    _unknown(show, {"id", "duration", "defaults", "cues"}, "show.show")
    show_id = _nonempty_str(show.get("id"), "show.show.id")
    duration = _number(show.get("duration"), "show.show.duration", min_exclusive=0.0)
    defaults = _transition(show.get("defaults", {}), "show.show.defaults")
    cues = _cues(show.get("cues"), duration, target_catalog)
    return ShowDefinition(
        schema_version=version,
        id=show_id,
        duration=duration,
        defaults=defaults,
        cues=tuple(cues),
    )


def _cues(
    value: Any, duration: float, target_catalog: TargetCatalog
) -> list[Cue]:
    cues_value = _list(value, "show.cues")
    cue_ids: set[str] = set()
    cues: list[Cue] = []
    for index, raw_cue in enumerate(cues_value):
        path = f"show.cues[{index}]"
        cue = _mapping(raw_cue, path)
        _unknown(
            cue,
            {
                "id",
                "start",
                "end",
                "priority",
                "target",
                "effect",
                "transition",
                "audio_control",
            },
            path,
        )
        cue_id = _nonempty_str(cue.get("id"), f"{path}.id")
        if cue_id in cue_ids:
            raise ShowValidationError(f"{path}.id", cue_id, "duplicate cue id")
        cue_ids.add(cue_id)
        start = _number(cue.get("start"), f"{path}.start", minimum=0.0)
        end = _number(cue.get("end"), f"{path}.end", min_exclusive=start)
        if end > duration:
            raise ShowValidationError(f"{path}.end", end, f"must be <= duration {duration}")
        priority = _int(cue.get("priority", 0), f"{path}.priority", minimum=0)
        cues.append(
            Cue(
                id=cue_id,
                start=start,
                end=end,
                priority=priority,
                target=_target(cue.get("target"), f"{path}.target", target_catalog),
                effect=_effect(cue.get("effect"), f"{path}.effect"),
                transition=_transition(cue.get("transition", {}), f"{path}.transition"),
                audio_control=(
                    None
                    if "audio_control" not in cue
                    else _audio_control(cue["audio_control"], f"{path}.audio_control")
                ),
            )
        )
    return cues


def _target(value: Any, path: str, catalog: TargetCatalog) -> TargetSelector:
    target = _mapping(value, path)
    _unknown(target, {"type", "id", "ids"}, path)
    kind = _choice(target.get("type"), f"{path}.type", TARGET_KINDS)
    if kind in {"all_analog", "all_digital", "all"}:
        if "id" in target:
            raise ShowValidationError(f"{path}.id", target["id"], "not allowed for target type")
        if "ids" in target:
            raise ShowValidationError(f"{path}.ids", target["ids"], "not allowed for target type")
        return TargetSelector(kind=kind)
    if kind in {"analog_group", "digital_group"} and "ids" in target:
        ids = tuple(_nonempty_str(item, f"{path}.ids[{idx}]") for idx, item in enumerate(_list(target["ids"], f"{path}.ids")))
        allowed = catalog.analog_zones if kind == "analog_group" else catalog.digital_strips
        for idx, item in enumerate(ids):
            if item not in allowed:
                raise ShowValidationError(f"{path}.ids[{idx}]", item, f"unknown {kind} member")
        return TargetSelector(kind=kind, ids=ids)
    if "ids" in target:
        raise ShowValidationError(f"{path}.ids", target["ids"], "not allowed for target type")
    target_id = _nonempty_str(target.get("id"), f"{path}.id")
    _validate_target_ref(kind, target_id, path, catalog)
    return TargetSelector(kind=kind, id=target_id)


def _validate_target_ref(
    kind: str, target_id: str, path: str, catalog: TargetCatalog
) -> None:
    catalogs: dict[str, Any] = {
        "analog_zone": catalog.analog_zones,
        "digital_strip": catalog.digital_strips,
        "analog_group": catalog.analog_groups,
        "digital_group": catalog.digital_groups,
        "virtual_path": catalog.virtual_paths,
    }
    allowed = catalogs[kind]
    if target_id not in allowed:
        raise ShowValidationError(f"{path}.id", target_id, f"unknown {kind}")


def _effect(value: Any, path: str) -> EffectSpec:
    effect = _mapping(value, path)
    _unknown(effect, {"mode", "name", "parameters", "allowed", "fallback"}, path)
    mode = _choice(effect.get("mode"), f"{path}.mode", EFFECT_MODES)
    if mode == "fixed":
        if "allowed" in effect:
            raise ShowValidationError(f"{path}.allowed", effect["allowed"], "not allowed for fixed effect")
        if "fallback" in effect:
            raise ShowValidationError(f"{path}.fallback", effect["fallback"], "not allowed for fixed effect")
        name = _effect_name(effect.get("name"), f"{path}.name")
        parameters = _parameters(effect.get("parameters", {}), f"{path}.parameters", name)
        return EffectSpec(mode=mode, name=name, parameters=parameters)
    if "name" in effect:
        raise ShowValidationError(f"{path}.name", effect["name"], "not allowed for adaptive effect")
    allowed = _mapping(effect.get("allowed"), f"{path}.allowed")
    _unknown(allowed, AUDIO_STATES, f"{path}.allowed")
    resolved: dict[str, str] = {}
    for state, effect_name in allowed.items():
        resolved[state] = _effect_name(effect_name, f"{path}.allowed.{state}")
    fallback = _effect_name(effect.get("fallback"), f"{path}.fallback")
    return EffectSpec(mode=mode, allowed=resolved, fallback=fallback)


def _parameters(value: Any, path: str, effect_name: str) -> dict[str, Any]:
    params = _mapping(value, path)
    allowed = get_effect_parameter_keys(effect_name)
    _unknown(params, allowed, path)
    for key, item in params.items():
        _parameter_value(item, f"{path}.{key}")
    return dict(params)


def _transition(value: Any, path: str) -> TransitionSpec:
    transition = _mapping(value, path)
    _unknown(
        transition,
        {"fade_in", "fade_out", "blend", "min_effect_hold", "switch_cooldown"},
        path,
    )
    return TransitionSpec(
        fade_in=_number(transition.get("fade_in", 0.0), f"{path}.fade_in", minimum=0.0),
        fade_out=_number(transition.get("fade_out", 0.0), f"{path}.fade_out", minimum=0.0),
        blend=_choice(transition.get("blend", "replace"), f"{path}.blend", BLEND_MODES),
        min_effect_hold=(
            None
            if "min_effect_hold" not in transition
            else _number(transition["min_effect_hold"], f"{path}.min_effect_hold", minimum=0.0)
        ),
        switch_cooldown=(
            None
            if "switch_cooldown" not in transition
            else _number(transition["switch_cooldown"], f"{path}.switch_cooldown", minimum=0.0)
        ),
    )


def _audio_control(value: Any, path: str) -> AudioControlSpec:
    audio = _mapping(value, path)
    _unknown(
        audio,
        {
            "tempo_sync",
            "tempo_confidence_min",
            "beat_regularity_min",
            "no_beat_fallback",
            "beats_per_cycle",
            "speed_smoothing_seconds",
            "state_confirmation_seconds",
            "min_effect_hold",
            "switch_cooldown",
        },
        path,
    )
    return AudioControlSpec(
        tempo_sync=_choice(audio.get("tempo_sync", "off"), f"{path}.tempo_sync", {"off", "auto", "locked"}),
        tempo_confidence_min=_number(audio.get("tempo_confidence_min", 0.0), f"{path}.tempo_confidence_min", minimum=0.0, maximum=1.0),
        beat_regularity_min=_number(audio.get("beat_regularity_min", 0.0), f"{path}.beat_regularity_min", minimum=0.0, maximum=1.0),
        no_beat_fallback=_choice(audio.get("no_beat_fallback", "hold"), f"{path}.no_beat_fallback", {"hold", "auto", "fallback"}),
        beats_per_cycle=(
            None
            if "beats_per_cycle" not in audio
            else _number(audio["beats_per_cycle"], f"{path}.beats_per_cycle", min_exclusive=0.0)
        ),
        speed_smoothing_seconds=_number(audio.get("speed_smoothing_seconds", 0.0), f"{path}.speed_smoothing_seconds", minimum=0.0),
        state_confirmation_seconds=_number(audio.get("state_confirmation_seconds", 0.0), f"{path}.state_confirmation_seconds", minimum=0.0),
        min_effect_hold=_number(audio.get("min_effect_hold", 0.0), f"{path}.min_effect_hold", minimum=0.0),
        switch_cooldown=_number(audio.get("switch_cooldown", 0.0), f"{path}.switch_cooldown", minimum=0.0),
    )


def _parameter_value(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ShowValidationError(path, key, "parameter keys must be strings")
            _parameter_value(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _parameter_value(item, f"{path}[{index}]")
    elif type(value) in {str, bool} or value is None:
        return
    else:
        _number(value, path)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ShowValidationError(path, value, "must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ShowValidationError(path, value, "must be a list")
    return value


def _unknown(value: Mapping[str, Any], allowed: Iterable[str], path: str) -> None:
    allowed_set = set(allowed)
    for key in value:
        if key not in allowed_set:
            raise ShowValidationError(f"{path}.{key}", value[key], "unknown field")


def _nonempty_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ShowValidationError(path, value, "must be a non-empty string")
    return value


def _choice(value: Any, path: str, choices: Iterable[str]) -> str:
    if not isinstance(value, str) or value not in set(choices):
        raise ShowValidationError(path, value, f"must be one of {sorted(choices)}")
    return value


def _effect_name(value: Any, path: str) -> str:
    name = _nonempty_str(value, path)
    if name not in list_effects():
        raise ShowValidationError(path, name, "unknown effect")
    return name


def _int(value: Any, path: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise ShowValidationError(path, value, "must be an integer")
    if minimum is not None and value < minimum:
        raise ShowValidationError(path, value, f"must be >= {minimum}")
    return value


def _number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    min_exclusive: float | None = None,
) -> float:
    if type(value) not in {int, float}:
        raise ShowValidationError(path, value, "must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ShowValidationError(path, value, "must be finite")
    if minimum is not None and number < minimum:
        raise ShowValidationError(path, value, f"must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ShowValidationError(path, value, f"must be <= {maximum}")
    if min_exclusive is not None and number <= min_exclusive:
        raise ShowValidationError(path, value, f"must be > {min_exclusive}")
    return number
