"""Focused Host contract for true Node8-only breath isolation."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import FLAG_SAFE_STATE, UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-node8-strip42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-strip42-blue-breath-40s.yaml")
FPS = 15.0
BLACK = (0, 0, 0)


def test_node8_breath_targets_only_208_with_uniform_blue() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
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
        visible_levels = set()
        logical_frames = int(round(show.duration * FPS))

        for index in range(logical_frames - 1):
            timestamp = (index + 1) / FPS
            sequence = index + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / FPS,
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
            assert address == ("192.168.31.208", 9001)
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=8,
                expected_outputs={1: (4, 20)},
            )
            assert packet is not None
            pixels = packet.outputs[0].pixels
            assert len(set(pixels)) == 1
            if 5.0 <= timestamp < 35.0:
                red, green, blue = pixels[0]
                assert red == green == 0
                assert 5 <= blue <= 37
                visible_levels.add(blue)
            else:
                assert pixels == (BLACK,) * 20

        safe = OutputTransform.generate_safe_frame(
            timestamp=show.duration,
            sequence=logical_frames,
            zone_ids=[zone.id for zone in layout.zones],
            strips=[
                {"id": strip.id, "pixel_count": strip.pixel_count}
                for strip in layout.strips
            ],
        )
        output.send_frame(mapping.map(safe))
        raw, address = output.get_sent_datagrams()[-1]
        packet = UdpV3Packet.decode(
            raw,
            expected_node_id=8,
            expected_outputs={1: (4, 20)},
        )
        assert address == ("192.168.31.208", 9001)
        assert packet is not None
        assert packet.flags & FLAG_SAFE_STATE
        assert packet.outputs[0].pixels == (BLACK,) * 20
        assert len(visible_levels) == 32
        assert output.health().logical_frames_sent == logical_frames
        assert output.health().packets_sent == logical_frames
    finally:
        Config.reset()
