"""Lighting effects - each effect produces a PixelFrame from an EffectContext.

All effects implement the BaseEffect interface.
P0 minimum: STATIC, VIDEO_AMBIENT, AUDIO_PULSE, COLOR_WAVE, CHASE, BREATH,
            VIDEO_AUDIO_FUSION, DEMO (8 effects).
"""

from light_engine.effects.base import (
    BaseEffect,
    EffectRegistration,
    _EFFECT_REGISTRY,
    create_effect,
    get_effect_registration,
    list_effects,
    register_effect,
    validate_effect_params,
)


def _register_all() -> None:
    """Register all built-in effects."""
    from light_engine.effects.static import StaticEffect
    from light_engine.effects.breath import BreathEffect
    from light_engine.effects.color_wave import ColorWaveEffect
    from light_engine.effects.chase import ChaseEffect
    from light_engine.effects.comet import CometEffect
    from light_engine.effects.audio_pulse import AudioPulseEffect
    from light_engine.effects.bass_pulse import BassPulseEffect
    from light_engine.effects.spectrum import SpectrumEffect
    from light_engine.effects.video_ambient import VideoAmbientEffect
    from light_engine.effects.video_audio_fusion import VideoAudioFusionEffect
    from light_engine.effects.calm import CalmEffect
    from light_engine.effects.color_wipe import (
        ColorWipeEffect,
        validate_color_wipe_params,
    )
    from light_engine.effects.twinkle import TwinkleEffect, validate_twinkle_params
    from light_engine.effects.demo import DemoEffect
    from light_engine.effects.single_dot import SingleDotEffect
    from light_engine.effects.step_pulse import StepPulseEffect
    from light_engine.effects.theater_phase import TheaterPhaseEffect

    register_effect("static", StaticEffect)
    register_effect("breath", BreathEffect)
    register_effect("color_wave", ColorWaveEffect)
    register_effect("chase", ChaseEffect)
    register_effect("comet", CometEffect)
    register_effect("audio_pulse", AudioPulseEffect)
    register_effect("bass_pulse", BassPulseEffect)
    register_effect("spectrum", SpectrumEffect)
    register_effect("video_ambient", VideoAmbientEffect)
    register_effect("video_audio_fusion", VideoAudioFusionEffect)
    register_effect("calm", CalmEffect)
    register_effect("color_wipe", ColorWipeEffect, validate_color_wipe_params)
    register_effect("twinkle", TwinkleEffect, validate_twinkle_params)
    register_effect("demo", DemoEffect)
    register_effect("step_pulse", StepPulseEffect)
    register_effect("single_dot", SingleDotEffect)
    register_effect("theater_phase", TheaterPhaseEffect)


# Auto-register on first import
_register_all()
