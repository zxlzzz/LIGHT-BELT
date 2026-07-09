"""DEMO effect - auto-cycles through multiple effects for demonstration."""

from light_engine.config import Config
from light_engine.effects.base import BaseEffect, create_effect, runtime_float, runtime_param
from light_engine.models import EffectContext, PixelFrame


class DemoEffect(BaseEffect):
    """Auto-rotates through a list of effects at a configurable interval."""

    def __init__(self, name: str = "demo"):
        super().__init__(name)
        config = Config.get_instance()
        self._cycle_interval = config.get("effects.demo.cycle_interval", 10.0)
        effect_names = config.get(
            "effects.demo.effects",
            ["static", "breath", "color_wave", "chase", "audio_pulse", "spectrum"],
        )
        self._effect_names: list[str] = list(effect_names)
        self._current_index = 0
        self._elapsed = 0.0
        self._effects: list[BaseEffect] = []
        self._init_effects()

    def _init_effects(self) -> None:
        self._effects = []
        for ename in self._effect_names:
            try:
                eff = create_effect(ename)
                self._effects.append(eff)
            except KeyError:
                pass
        if not self._effects:
            self._effects = [create_effect("static")]

    def _apply_runtime_parameters(self, ctx: EffectContext) -> None:
        self._cycle_interval = max(
            0.001, runtime_float(ctx, "cycle_interval", self._cycle_interval)
        )
        effect_names = list(runtime_param(ctx, "effects", self._effect_names))
        if effect_names != self._effect_names:
            self._effect_names = effect_names
            self._current_index = 0
            self._elapsed = 0.0
            self._init_effects()

    @property
    def current_effect_name(self) -> str:
        if self._effects:
            return self._effects[self._current_index].name
        return "unknown"

    def process(self, ctx: EffectContext) -> PixelFrame:
        self._apply_runtime_parameters(ctx)
        self._elapsed += ctx.delta_time
        if self._elapsed >= self._cycle_interval:
            self._elapsed = 0.0
            self._current_index = (self._current_index + 1) % len(self._effects)
            self._effects[self._current_index].reset()

        if not self._effects:
            return PixelFrame(timestamp=ctx.timestamp, sequence=ctx.sequence)

        frame = self._effects[self._current_index].process(ctx)
        frame.metadata["demo_current"] = self.current_effect_name
        frame.metadata["demo_progress"] = round(self._elapsed / self._cycle_interval, 2)
        return frame

    def reset(self) -> None:
        self._current_index = 0
        self._elapsed = 0.0
        for eff in self._effects:
            eff.reset()
