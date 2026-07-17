"""Focused contract for the exploratory two-node all-effects Show."""

from pathlib import Path

from light_engine.config import Config
from light_engine.data.generators import SyntheticDataSource
from light_engine.effects import list_effects
from light_engine.mapping import Layout
from light_engine.models import EffectContext
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-two-node-all-effects-171s.yaml")


def test_all_registered_effects_render_for_both_strips() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)
        media = SyntheticDataSource(seed=20260717)

        assert show.duration == 171.0
        assert {cue.effect.name for cue in show.cues} == set(list_effects())

        for sequence, cue in enumerate(show.cues, start=1):
            timestamp = (cue.start + cue.end) / 2.0
            frame = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / 15.0,
                    sequence=sequence,
                    video_features=media.get_video_features(timestamp),
                    audio_features=media.get_audio_features(timestamp),
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            assert {strip.strip_id for strip in frame.strips} == {
                "strip_41",
                "strip_42",
            }
            assert {strip.pixel_count for strip in frame.strips} == {10, 20}
    finally:
        Config.reset()
