"""Strict versioned show schema loader."""

from light_engine.show.adaptive_selector import (
    AdaptiveEffectSelector,
    REASON_CODES,
    SelectionDecision,
    classify_music_state,
    choose_sync,
)
from light_engine.show.compositor import (
    AnalogContribution,
    CueRenderJob,
    DigitalContribution,
    FrameContribution,
    ResolvedTarget,
    ShowRuntime,
    TargetResolver,
    black_base_frame,
    compose_frame,
    frame_to_contribution,
    make_scoped_context,
    transition_weight,
)
from light_engine.show.loader import (
    ShowValidationError,
    TargetCatalog,
    load_show,
    validate_show_data,
)
from light_engine.show.models import (
    AudioControlSpec,
    Cue,
    EffectSpec,
    ShowDefinition,
    TargetSelector,
    TransitionSpec,
)

__all__ = [
    "AnalogContribution",
    "AdaptiveEffectSelector",
    "AudioControlSpec",
    "Cue",
    "CueRenderJob",
    "DigitalContribution",
    "EffectSpec",
    "FrameContribution",
    "ResolvedTarget",
    "REASON_CODES",
    "SelectionDecision",
    "ShowRuntime",
    "ShowDefinition",
    "ShowValidationError",
    "TargetCatalog",
    "TargetResolver",
    "TargetSelector",
    "TransitionSpec",
    "black_base_frame",
    "classify_music_state",
    "compose_frame",
    "choose_sync",
    "frame_to_contribution",
    "load_show",
    "make_scoped_context",
    "transition_weight",
    "validate_show_data",
]
