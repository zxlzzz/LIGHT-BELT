"""Focused contract for the two-node virtual-path comet Show."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout
from light_engine.models import EffectContext
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-two-node-virtual-path-color-comet-32s.yaml")
FPS = 15.0


def _head_position(frame) -> int:
    strips = {strip.strip_id: strip for strip in frame.strips}
    pixels = strips["strip_41"].pixels + strips["strip_42"].pixels
    return max(range(len(pixels)), key=lambda index: max(pixels[index]))


def _head_color(frame) -> tuple[float, float, float]:
    strips = {strip.strip_id: strip for strip in frame.strips}
    pixels = strips["strip_41"].pixels + strips["strip_42"].pixels
    return pixels[_head_position(frame)]


def test_comet_crosses_the_two_strip_path_in_both_directions() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)

        assert show.duration == 32.0
        assert tuple(target.id for target in show.virtual_paths[0].targets) == (
            "strip_41",
            "strip_42",
        )
        assert [cue.origin for cue in show.cues] == ["start", "end"]
        assert all(cue.effect.name == "comet" for cue in show.cues)
        assert all(cue.color.mode == "effect_default" for cue in show.cues)

        sample_times = {1.5, 3.0, 5.0, 16.5, 18.0, 20.0}
        color_sample_times = {2.0, 7.0, 12.5}
        samples = {}
        colors = {}
        for index in range(int(show.duration * FPS)):
            timestamp = (index + 1) / FPS
            frame = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / FPS,
                    sequence=index + 1,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=index + 1,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            for sample in sample_times:
                if sample not in samples and timestamp >= sample:
                    samples[sample] = _head_position(frame)
            for sample in color_sample_times:
                if sample not in colors and timestamp >= sample:
                    colors[sample] = tuple(round(channel, 3) for channel in _head_color(frame))

        forward = [samples[1.5], samples[3.0], samples[5.0]]
        reverse = [samples[16.5], samples[18.0], samples[20.0]]
        assert forward[0] < 10 <= forward[1] < forward[2]
        assert reverse[0] > reverse[1] >= 10 > reverse[2]
        assert len(set(colors.values())) == 3
    finally:
        Config.reset()
