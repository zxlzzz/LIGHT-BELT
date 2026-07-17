"""Focused Host contract for the first unrestricted strip41 breath gate."""

from pathlib import Path

import pytest

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


SHOW = Path("config/shows/ws2811-ab-strip41-blue-breath-40s.yaml")
BLACK = (0, 0, 0)


@pytest.mark.parametrize(
    ("profile", "fps"),
    (
        (Path("config/profiles/ws2811-ab-node2-strip41-immediate.yaml"), 30.0),
        (
            Path("config/profiles/ws2811-ab-node2-strip41-immediate-15fps.yaml"),
            15.0,
        ),
        (
            Path("config/profiles/ws2811-ab-node2-strip41-immediate-5fps.yaml"),
            5.0,
        ),
    ),
)
def test_breath_show_is_uniform_blue_with_black_guards(
    profile: Path,
    fps: float,
) -> None:
    Config.reset()
    try:
        config = Config.get_instance(profile)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=config.get("outputs.transform.power_limit"),
        )
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        visible_levels: set[int] = set()

        assert config.get("system.output_fps") == fps
        assert config.get("outputs.udp_v3.presentation.mode") == "immediate"
        assert show.duration == 40.0
        for index in range(int(show.duration * fps) - 1):
            timestamp = (index + 1) / fps
            sequence = index + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))
            raw, address = output.get_sent_datagrams()[-1]
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=2,
                expected_outputs={1: (4, 10)},
            )
            assert address == ("192.168.31.202", 9001)
            assert packet is not None
            pixels = packet.outputs[0].pixels
            assert len(set(pixels)) == 1
            if 5.0 <= timestamp < 35.0:
                red, green, blue = pixels[0]
                assert red == green == 0
                assert blue > 0
                visible_levels.add(blue)
            else:
                assert pixels == (BLACK,) * 10

        assert min(visible_levels) <= 6
        assert max(visible_levels) >= 36
        if fps == 5.0:
            assert len(visible_levels) == 14
        else:
            assert len(visible_levels) >= 25
    finally:
        Config.reset()
