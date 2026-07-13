"""Strict YAML loader and validator for authored shows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from light_engine.effects import list_effects, validate_effect_params
from light_engine.effects.base import get_effect_parameter_keys
from light_engine.show.audio_modulation import SOURCE_FIELDS
from light_engine.show.models import (
    AudioControlSpec,
    AudioModulationChannelSpec,
    AudioModulationSpec,
    BrightnessKeyframe,
    BrightnessTrackSpec,
    ColorSpec,
    Cue,
    CueBranchSpec,
    EffectSpec,
    ShowDefinition,
    TargetSelector,
    TransitionSpec,
    VirtualPathSpec,
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
V2_TARGET_KINDS = frozenset(
    {"analog_zone", "digital_strip", "digital_set", "digital_group", "virtual_path"}
)
ORIGINS = frozenset({"start", "end", "center", "edges"})
COLOR_MODES = frozenset({"effect_default", "solid", "palette"})
BLEND_MODES = frozenset({"replace", "add"})
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
MODULATION_CHANNELS = frozenset({"brightness", "speed", "intensity"})
BRIGHTNESS_INTERPOLATIONS = frozenset({"linear", "step"})


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

    @classmethod
    def from_layout(cls, layout: Any) -> "TargetCatalog":
        """Build a show target catalog from a validated layout."""
        return cls(
            analog_zones=(zone.id for zone in layout.zones),
            digital_strips=(strip.id for strip in layout.strips),
            virtual_paths=(path.id for path in layout.virtual_paths),
        )

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
    if version not in {1, 2}:
        raise ShowValidationError("show.schema_version", version, "must be 1 or 2")
    show = _mapping(root.get("show"), "show.show")
    allowed_show = {"id", "duration", "defaults", "cues"}
    if version == 2:
        allowed_show.update({"virtual_paths", "brightness_tracks"})
    _unknown(show, allowed_show, "show.show")
    show_id = _nonempty_str(show.get("id"), "show.show.id")
    duration = _number(show.get("duration"), "show.show.duration", min_exclusive=0.0)
    defaults = _transition(show.get("defaults", {}), "show.show.defaults")
    virtual_paths = (
        _virtual_paths(show.get("virtual_paths", []), target_catalog)
        if version == 2
        else ()
    )
    cue_catalog = TargetCatalog(
        analog_zones=target_catalog.analog_zones,
        digital_strips=target_catalog.digital_strips,
        analog_groups=target_catalog.analog_groups,
        digital_groups=target_catalog.digital_groups,
        virtual_paths=target_catalog.virtual_paths | frozenset(path.id for path in virtual_paths),
    )
    cues = _cues(show.get("cues"), duration, cue_catalog, defaults, version=version)
    brightness_tracks = (
        _brightness_tracks(
            show.get("brightness_tracks", []), duration, cue_catalog
        )
        if version == 2
        else ()
    )
    if version == 2:
        paths_by_id = {path.id: path for path in virtual_paths}
        for cue_index, cue in enumerate(cues):
            if cue.branches and cue.effect.mode != "fixed":
                raise ShowValidationError(
                    f"show.cues[{cue_index}].effect.mode",
                    cue.effect.mode,
                    "bounded branches require a fixed effect",
                )
            for branch_index, branch in enumerate(cue.branches):
                if branch.target.kind != "digital_set":
                    raise ShowValidationError(
                        f"show.cues[{cue_index}].branches[{branch_index}].target.type",
                        branch.target.kind,
                        "bounded branch target must be digital_set",
                    )
                path_spec = paths_by_id.get(branch.path_id)
                if path_spec is None:
                    # Layout-defined v1 paths have no logical member contract and
                    # therefore cannot drive deterministic v2 branch timing.
                    raise ShowValidationError(
                        f"show.cues[{cue_index}].branches[{branch_index}].after.virtual_path",
                        branch.path_id,
                        "branch trigger requires a Show v2 virtual_path",
                    )
                if branch.after_target_id not in {target.id for target in path_spec.targets}:
                    raise ShowValidationError(
                        f"show.cues[{cue_index}].branches[{branch_index}].after.target",
                        branch.after_target_id,
                        "must be a member of the trigger virtual_path",
                    )
    return ShowDefinition(
        schema_version=version,
        id=show_id,
        duration=duration,
        defaults=defaults,
        cues=tuple(cues),
        virtual_paths=tuple(virtual_paths),
        brightness_tracks=brightness_tracks,
    )


def _cues(
    value: Any,
    duration: float,
    target_catalog: TargetCatalog,
    defaults: TransitionSpec,
    *,
    version: int,
) -> list[Cue]:
    cues_value = _list(value, "show.cues")
    cue_ids: set[str] = set()
    cues: list[Cue] = []
    for index, raw_cue in enumerate(cues_value):
        path = f"show.cues[{index}]"
        cue = _mapping(raw_cue, path)
        allowed_cue = {
            "id", "start", "end", "priority", "target", "effect", "transition",
            "audio_control", "audio_modulation",
        }
        if version == 2:
            allowed_cue.update({"color", "origin", "branches"})
        _unknown(
            cue,
            allowed_cue,
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
                target=_target(cue.get("target"), f"{path}.target", target_catalog, version=version),
                effect=_effect(cue.get("effect"), f"{path}.effect", version=version),
                color=(
                    _color_spec(cue.get("color", {"mode": "effect_default"}), f"{path}.color")
                    if version == 2 else ColorSpec()
                ),
                origin=(
                    _choice(cue["origin"], f"{path}.origin", ORIGINS)
                    if version == 2 and "origin" in cue else
                    (None if version == 2 else "start")
                ),
                branches=(
                    _branches(cue.get("branches", []), f"{path}.branches", target_catalog)
                    if version == 2 else ()
                ),
                transition=_transition(
                    cue.get("transition", {}), f"{path}.transition", defaults
                ),
                audio_control=(
                    None
                    if "audio_control" not in cue
                    else _audio_control(cue["audio_control"], f"{path}.audio_control")
                ),
                audio_modulation=(
                    None
                    if "audio_modulation" not in cue
                    else _audio_modulation(
                        cue["audio_modulation"], f"{path}.audio_modulation"
                    )
                ),
            )
        )
    return cues


def _target(
    value: Any, path: str, catalog: TargetCatalog, *, version: int = 1
) -> TargetSelector:
    target = _mapping(value, path)
    _unknown(target, {"type", "id", "ids"}, path)
    kinds = V2_TARGET_KINDS if version == 2 else TARGET_KINDS
    kind = _choice(target.get("type"), f"{path}.type", kinds)
    if version == 2:
        if kind == "digital_set":
            if "id" in target:
                raise ShowValidationError(f"{path}.id", target["id"], "not allowed for digital_set")
            ids = tuple(
                _nonempty_str(item, f"{path}.ids[{idx}]")
                for idx, item in enumerate(_list(target.get("ids"), f"{path}.ids"))
            )
            if not ids:
                raise ShowValidationError(f"{path}.ids", [], "must be non-empty")
            if len(set(ids)) != len(ids):
                raise ShowValidationError(f"{path}.ids", list(ids), "must contain unique IDs")
            for idx, item in enumerate(ids):
                if item not in catalog.digital_strips:
                    raise ShowValidationError(f"{path}.ids[{idx}]", item, "unknown digital_strip")
            return TargetSelector(kind=kind, ids=ids)
        if "ids" in target:
            raise ShowValidationError(f"{path}.ids", target["ids"], "not allowed for target type")
        target_id = _nonempty_str(target.get("id"), f"{path}.id")
        _validate_target_ref(kind, target_id, path, catalog)
        return TargetSelector(kind=kind, id=target_id)
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


def _effect(value: Any, path: str, *, version: int = 1) -> EffectSpec:
    effect = _mapping(value, path)
    if version == 2:
        _unknown(effect, {"mode", "id", "params", "allowed", "fallback"}, path)
    else:
        _unknown(effect, {"mode", "name", "parameters", "allowed", "fallback"}, path)
    mode = _choice(effect.get("mode"), f"{path}.mode", EFFECT_MODES)
    if mode == "fixed":
        if "allowed" in effect:
            raise ShowValidationError(f"{path}.allowed", effect["allowed"], "not allowed for fixed effect")
        if "fallback" in effect:
            raise ShowValidationError(f"{path}.fallback", effect["fallback"], "not allowed for fixed effect")
        id_key = "id" if version == 2 else "name"
        params_key = "params" if version == 2 else "parameters"
        effect_id = _effect_name(effect.get(id_key), f"{path}.{id_key}")
        parameters = _parameters(effect.get(params_key, {}), f"{path}.{params_key}", effect_id)
        return EffectSpec(mode=mode, id=effect_id, params=parameters)
    forbidden_id = "id" if version == 2 else "name"
    forbidden_params = "params" if version == 2 else "parameters"
    if forbidden_id in effect:
        raise ShowValidationError(f"{path}.{forbidden_id}", effect[forbidden_id], "not allowed for adaptive effect")
    if forbidden_params in effect:
        raise ShowValidationError(
            f"{path}.{forbidden_params}",
            effect[forbidden_params],
            "not allowed for adaptive effect",
        )
    allowed = _mapping(effect.get("allowed"), f"{path}.allowed")
    _unknown(allowed, AUDIO_STATES, f"{path}.allowed")
    resolved: dict[str, str] = {}
    for state, effect_name in allowed.items():
        resolved[state] = _effect_name(effect_name, f"{path}.allowed.{state}")
    fallback = _effect_name(effect.get("fallback"), f"{path}.fallback")
    if fallback not in set(resolved.values()):
        raise ShowValidationError(f"{path}.fallback", fallback, "must be one of allowed effects")
    return EffectSpec(mode=mode, allowed=resolved, fallback=fallback)


def _virtual_paths(value: Any, catalog: TargetCatalog) -> tuple[VirtualPathSpec, ...]:
    raw_paths = _list(value, "show.virtual_paths")
    seen: set[str] = set()
    paths: list[VirtualPathSpec] = []
    for index, raw in enumerate(raw_paths):
        path = f"show.virtual_paths[{index}]"
        item = _mapping(raw, path)
        _unknown(item, {"id", "targets", "origin"}, path)
        path_id = _nonempty_str(item.get("id"), f"{path}.id")
        if path_id in seen or path_id in catalog.virtual_paths:
            raise ShowValidationError(f"{path}.id", path_id, "duplicate virtual path id")
        seen.add(path_id)
        targets = tuple(
            _target(target, f"{path}.targets[{target_index}]", catalog, version=2)
            for target_index, target in enumerate(_list(item.get("targets"), f"{path}.targets"))
        )
        if not targets:
            raise ShowValidationError(f"{path}.targets", [], "must be non-empty")
        if any(target.kind not in {"analog_zone", "digital_strip"} for target in targets):
            raise ShowValidationError(f"{path}.targets", item["targets"], "members must be analog_zone or digital_strip")
        target_ids = [target.id for target in targets]
        if len(set(target_ids)) != len(target_ids):
            raise ShowValidationError(f"{path}.targets", item["targets"], "must contain unique logical targets")
        paths.append(VirtualPathSpec(
            id=path_id,
            targets=targets,
            origin=_choice(item.get("origin", "start"), f"{path}.origin", ORIGINS),
        ))
    return tuple(paths)


def _brightness_tracks(
    value: Any,
    duration: float,
    catalog: TargetCatalog,
) -> tuple[BrightnessTrackSpec, ...]:
    raw_tracks = _list(value, "show.brightness_tracks")
    seen: set[str] = set()
    tracks: list[BrightnessTrackSpec] = []
    for index, raw in enumerate(raw_tracks):
        path = f"show.brightness_tracks[{index}]"
        item = _mapping(raw, path)
        _unknown(
            item,
            {"id", "target", "start", "end", "interpolation", "keyframes"},
            path,
        )
        track_id = _nonempty_str(item.get("id"), f"{path}.id")
        if track_id in seen:
            raise ShowValidationError(
                f"{path}.id", track_id, "duplicate brightness track id"
            )
        seen.add(track_id)
        keyframes = _brightness_keyframes(
            item.get("keyframes"), f"{path}.keyframes", duration
        )
        start = _number(
            item.get("start", keyframes[0].time),
            f"{path}.start",
            minimum=0.0,
            maximum=duration,
        )
        end = _number(
            item.get("end", keyframes[-1].time),
            f"{path}.end",
            minimum=0.0,
            maximum=duration,
        )
        if end <= start:
            raise ShowValidationError(f"{path}.end", end, "must be > start")
        if keyframes[0].time < start:
            raise ShowValidationError(
                f"{path}.keyframes[0].time",
                keyframes[0].time,
                "must be >= track start",
            )
        if keyframes[-1].time > end:
            raise ShowValidationError(
                f"{path}.keyframes[{len(keyframes) - 1}].time",
                keyframes[-1].time,
                "must be <= track end",
            )
        tracks.append(
            BrightnessTrackSpec(
                id=track_id,
                target=_target(
                    item.get("target"), f"{path}.target", catalog, version=2
                ),
                start=start,
                end=end,
                interpolation=_choice(
                    item.get("interpolation", "linear"),
                    f"{path}.interpolation",
                    BRIGHTNESS_INTERPOLATIONS,
                ),
                keyframes=keyframes,
            )
        )
    return tuple(tracks)


def _brightness_keyframes(
    value: Any,
    path: str,
    duration: float,
) -> tuple[BrightnessKeyframe, ...]:
    raw_keyframes = _list(value, path)
    if len(raw_keyframes) < 2:
        raise ShowValidationError(
            path, raw_keyframes, "must contain at least two keyframes"
        )
    keyframes: list[BrightnessKeyframe] = []
    previous_time: float | None = None
    for index, raw in enumerate(raw_keyframes):
        item_path = f"{path}[{index}]"
        item = _mapping(raw, item_path)
        _unknown(item, {"time", "value"}, item_path)
        time = _number(
            item.get("time"), f"{item_path}.time", minimum=0.0, maximum=duration
        )
        if previous_time is not None and time <= previous_time:
            raise ShowValidationError(
                f"{item_path}.time",
                time,
                "must be strictly greater than the previous keyframe time",
            )
        previous_time = time
        keyframes.append(
            BrightnessKeyframe(
                time=time,
                value=_number(
                    item.get("value"),
                    f"{item_path}.value",
                    minimum=0.0,
                    maximum=1.0,
                ),
            )
        )
    return tuple(keyframes)


def _branches(value: Any, path: str, catalog: TargetCatalog) -> tuple[CueBranchSpec, ...]:
    branches: list[CueBranchSpec] = []
    for index, raw in enumerate(_list(value, path)):
        item_path = f"{path}[{index}]"
        item = _mapping(raw, item_path)
        _unknown(item, {"after", "target", "origin"}, item_path)
        after = _mapping(item.get("after"), f"{item_path}.after")
        _unknown(after, {"virtual_path", "target"}, f"{item_path}.after")
        path_id = _nonempty_str(after.get("virtual_path"), f"{item_path}.after.virtual_path")
        if path_id not in catalog.virtual_paths:
            raise ShowValidationError(f"{item_path}.after.virtual_path", path_id, "unknown virtual_path")
        branches.append(CueBranchSpec(
            path_id=path_id,
            after_target_id=_nonempty_str(after.get("target"), f"{item_path}.after.target"),
            target=_target(item.get("target"), f"{item_path}.target", catalog, version=2),
            origin=_choice(item.get("origin", "start"), f"{item_path}.origin", ORIGINS),
        ))
    return tuple(branches)


def _color_spec(value: Any, path: str) -> ColorSpec:
    item = _mapping(value, path)
    _unknown(item, {"mode", "color", "colors"}, path)
    mode = _choice(item.get("mode"), f"{path}.mode", COLOR_MODES)
    if mode == "effect_default":
        if "color" in item:
            raise ShowValidationError(f"{path}.color", item["color"], "not allowed for effect_default")
        if "colors" in item:
            raise ShowValidationError(f"{path}.colors", item["colors"], "not allowed for effect_default")
        return ColorSpec()
    if mode == "solid":
        if "colors" in item:
            raise ShowValidationError(f"{path}.colors", item["colors"], "not allowed for solid")
        return ColorSpec(mode=mode, color=_rgb_color(item.get("color"), f"{path}.color"))
    if "color" in item:
        raise ShowValidationError(f"{path}.color", item["color"], "not allowed for palette")
    colors = tuple(
        _rgb_color(raw, f"{path}.colors[{index}]")
        for index, raw in enumerate(_list(item.get("colors"), f"{path}.colors"))
    )
    if not colors:
        raise ShowValidationError(f"{path}.colors", [], "must be non-empty")
    return ColorSpec(mode=mode, palette=colors)


def _parameters(value: Any, path: str, effect_name: str) -> dict[str, Any]:
    params = _mapping(value, path)
    allowed = get_effect_parameter_keys(effect_name)
    _unknown(params, allowed, path)
    validated: dict[str, Any] = {}
    for key, item in params.items():
        item_path = f"{path}.{key}"
        if key == "color_timeline":
            validated[key] = _color_timeline(item, item_path)
        else:
            _parameter_value(item, item_path)
            validated[key] = item
    try:
        return dict(validate_effect_params(effect_name, validated))
    except (TypeError, ValueError) as exc:
        raise ShowValidationError(path, value, str(exc)) from exc


def _color_timeline(value: Any, path: str) -> dict[str, Any]:
    timeline = _mapping(value, path)
    _unknown(timeline, {"interpolation", "keyframes"}, path)
    interpolation = _choice(
        timeline.get("interpolation"),
        f"{path}.interpolation",
        {"rgb_linear"},
    )
    keyframes_value = _list(timeline.get("keyframes"), f"{path}.keyframes")
    if len(keyframes_value) < 2:
        raise ShowValidationError(
            f"{path}.keyframes",
            keyframes_value,
            "must contain at least 2 keyframes",
        )
    keyframes: list[dict[str, Any]] = []
    previous_time: float | None = None
    for index, raw_keyframe in enumerate(keyframes_value):
        keyframe_path = f"{path}.keyframes[{index}]"
        keyframe = _mapping(raw_keyframe, keyframe_path)
        _unknown(keyframe, {"time", "color"}, keyframe_path)
        time_value = _number(
            keyframe.get("time"),
            f"{keyframe_path}.time",
            minimum=0.0,
        )
        if previous_time is not None and time_value <= previous_time:
            raise ShowValidationError(
                f"{keyframe_path}.time",
                keyframe.get("time"),
                f"must be > previous keyframe time {previous_time}",
            )
        color = _rgb_color(keyframe.get("color"), f"{keyframe_path}.color")
        keyframes.append({"time": time_value, "color": color})
        previous_time = time_value
    return {"interpolation": interpolation, "keyframes": tuple(keyframes)}


def _rgb_color(value: Any, path: str) -> tuple[float, float, float]:
    channels = _list(value, path)
    if len(channels) != 3:
        raise ShowValidationError(path, value, "must contain exactly 3 RGB channels")
    return tuple(
        _number(channel, f"{path}[{index}]", minimum=0.0, maximum=1.0)
        for index, channel in enumerate(channels)
    )


def _transition(
    value: Any,
    path: str,
    defaults: TransitionSpec | None = None,
) -> TransitionSpec:
    transition = _mapping(value, path)
    _unknown(
        transition,
        {"fade_in", "fade_out", "blend", "min_effect_hold", "switch_cooldown"},
        path,
    )
    return TransitionSpec(
        fade_in=_number(
            transition.get("fade_in", defaults.fade_in if defaults else 0.0),
            f"{path}.fade_in",
            minimum=0.0,
        ),
        fade_out=_number(
            transition.get("fade_out", defaults.fade_out if defaults else 0.0),
            f"{path}.fade_out",
            minimum=0.0,
        ),
        blend=_choice(
            transition.get("blend", defaults.blend if defaults else "replace"),
            f"{path}.blend",
            BLEND_MODES,
        ),
        min_effect_hold=(
            _number(transition["min_effect_hold"], f"{path}.min_effect_hold", minimum=0.0)
            if "min_effect_hold" in transition
            else (defaults.min_effect_hold if defaults else None)
        ),
        switch_cooldown=(
            _number(transition["switch_cooldown"], f"{path}.switch_cooldown", minimum=0.0)
            if "switch_cooldown" in transition
            else (defaults.switch_cooldown if defaults else None)
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
            "beats_per_cycle",
            "beat_subdivision",
            "speed_smoothing_seconds",
            "state_confirmation_seconds",
            "min_effect_hold",
            "switch_cooldown",
        },
        path,
    )
    return AudioControlSpec(
        tempo_sync=_choice(audio.get("tempo_sync", "off"), f"{path}.tempo_sync", {"off", "auto"}),
        tempo_confidence_min=_number(audio.get("tempo_confidence_min", 0.0), f"{path}.tempo_confidence_min", minimum=0.0, maximum=1.0),
        beat_regularity_min=_number(audio.get("beat_regularity_min", 0.0), f"{path}.beat_regularity_min", minimum=0.0, maximum=1.0),
        beats_per_cycle=(
            None
            if "beats_per_cycle" not in audio
            else _number(audio["beats_per_cycle"], f"{path}.beats_per_cycle", min_exclusive=0.0)
        ),
        beat_subdivision=_choice_number(
            audio.get("beat_subdivision", 1.0),
            f"{path}.beat_subdivision",
            {0.25, 0.5, 1.0, 2.0, 4.0},
        ),
        speed_smoothing_seconds=_number(audio.get("speed_smoothing_seconds", 0.0), f"{path}.speed_smoothing_seconds", minimum=0.0),
        state_confirmation_seconds=_number(audio.get("state_confirmation_seconds", 0.0), f"{path}.state_confirmation_seconds", minimum=0.0),
        min_effect_hold=_number(audio.get("min_effect_hold", 0.0), f"{path}.min_effect_hold", minimum=0.0),
        switch_cooldown=_number(audio.get("switch_cooldown", 0.0), f"{path}.switch_cooldown", minimum=0.0),
    )


def _audio_modulation(value: Any, path: str) -> AudioModulationSpec:
    modulation = _mapping(value, path)
    _unknown(modulation, {"enabled", *MODULATION_CHANNELS}, path)
    enabled = modulation.get("enabled", True)
    if type(enabled) is not bool:
        raise ShowValidationError(f"{path}.enabled", enabled, "must be a boolean")
    channels = {
        name: _audio_modulation_channel(modulation[name], f"{path}.{name}")
        for name in MODULATION_CHANNELS
        if name in modulation
    }
    if enabled and not channels:
        raise ShowValidationError(path, modulation, "must define at least one modulation channel when enabled")
    return AudioModulationSpec(enabled=enabled, **channels)


def _audio_modulation_channel(value: Any, path: str) -> AudioModulationChannelSpec:
    channel = _mapping(value, path)
    _unknown(
        channel,
        {"source", "amount", "min_multiplier", "max_multiplier", "smoothing_seconds"},
        path,
    )
    required = ("source", "amount", "min_multiplier", "max_multiplier", "smoothing_seconds")
    for field_name in required:
        if field_name not in channel:
            raise ShowValidationError(f"{path}.{field_name}", None, "is required")
    source = _choice(channel["source"], f"{path}.source", SOURCE_FIELDS)
    amount = _number(channel["amount"], f"{path}.amount", minimum=0.0, maximum=1.0)
    minimum = _number(channel["min_multiplier"], f"{path}.min_multiplier", minimum=0.0, maximum=10.0)
    maximum = _number(channel["max_multiplier"], f"{path}.max_multiplier", minimum=0.0, maximum=10.0)
    if minimum > maximum:
        raise ShowValidationError(
            f"{path}.max_multiplier",
            maximum,
            "must be >= min_multiplier",
        )
    return AudioModulationChannelSpec(
        source=source,
        amount=amount,
        min_multiplier=minimum,
        max_multiplier=maximum,
        smoothing_seconds=_number(
            channel["smoothing_seconds"],
            f"{path}.smoothing_seconds",
            minimum=0.0,
        ),
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


def _choice_number(value: Any, path: str, choices: Iterable[float]) -> float:
    number = _number(value, path, min_exclusive=0.0)
    allowed = set(choices)
    if number not in allowed:
        raise ShowValidationError(path, value, f"must be one of {sorted(allowed)}")
    return number


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
