"""Focused contract for the short strip41/strip42 breath isolation Show."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import FLAG_SAFE_STATE, UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-two-node-blue-breath-isolation-74s.yaml")
FPS = 15.0
BLACK = (0, 0, 0)
NODE_SPECS = {2: ("192.168.31.202", 10), 8: ("192.168.31.208", 20)}


def _active(node_id: int, timestamp: float) -> bool:
    if node_id == 2:
        return 1.0 <= timestamp < 21.0 or 43.0 <= timestamp < 73.0
    return 22.0 <= timestamp < 42.0 or 43.0 <= timestamp < 73.0


def test_short_breath_isolation_packets_match_each_stage() -> None:
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
        logical_frames = int(round(show.duration * FPS))

        for index in range(logical_frames - 1):
            timestamp = (index + 1) / FPS
            sequence = index + 1
            logical = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=1.0 / FPS, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))
            pixels_by_node = {}
            for raw, address in output.get_sent_datagrams()[-2:]:
                node_id = 2 if address[0].endswith(".202") else 8
                host, pixel_count = NODE_SPECS[node_id]
                assert address == (host, 9001)
                packet = UdpV3Packet.decode(
                    raw,
                    expected_node_id=node_id,
                    expected_outputs={1: (4, pixel_count)},
                )
                assert packet is not None
                pixels = packet.outputs[0].pixels
                assert len(set(pixels)) == 1
                if _active(node_id, timestamp):
                    red, green, blue = pixels[0]
                    assert red == green == 0
                    assert 5 <= blue <= 37
                else:
                    assert pixels == (BLACK,) * pixel_count
                pixels_by_node[node_id] = pixels
            if 43.0 <= timestamp < 73.0:
                assert pixels_by_node[2][0] == pixels_by_node[8][0]

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
        for raw, address in output.get_sent_datagrams()[-2:]:
            node_id = 2 if address[0].endswith(".202") else 8
            _, pixel_count = NODE_SPECS[node_id]
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=node_id,
                expected_outputs={1: (4, pixel_count)},
            )
            assert packet is not None
            assert packet.flags & FLAG_SAFE_STATE
            assert packet.outputs[0].pixels == (BLACK,) * pixel_count

        assert logical_frames == 1110
        assert output.health().logical_frames_sent == 1110
        assert output.health().packets_sent == 2220
    finally:
        Config.reset()
