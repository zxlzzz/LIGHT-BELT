"""Focused Host contract for staged Node8 and concurrent breath playback."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.ddp_output import DDP_HEADER_LEN, DdpOutput
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-two-node-blue-breath-staged-75s.yaml")
FPS = 15.0
BLACK = (0, 0, 0)
NODE_SPECS = {
    2: (("192.168.31.58", 4048), 10),
    8: (("192.168.31.208", 4048), 20),
}


def _active(node_id: int, timestamp: float) -> bool:
    if node_id == 2:
        return 40.0 <= timestamp < 70.0
    return 5.0 <= timestamp < 35.0 or 40.0 <= timestamp < 70.0


def test_two_node_breath_packets_are_uniform_blue_and_in_phase() -> None:
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
        output = DdpOutput()
        output.open()
        levels_by_node = {2: set(), 8: set()}
        last_physical_pixels = {2: None, 8: None}
        physical_writes = {2: 0, 8: 0}
        identical_skips = {2: 0, 8: 0}

        logical_frames = int(round(show.duration * FPS))
        assert config.get("system.output_fps") == FPS
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
            chunk = output.get_sent_datagrams()[-2:]
            packets = {}
            for raw, address in chunk:
                node_id = 2 if address[0] == "192.168.31.58" else 8
                expected_address, pixel_count = NODE_SPECS[node_id]
                assert address == expected_address
                payload = raw[DDP_HEADER_LEN:]
                pixels = tuple(tuple(payload[offset:offset + 3]) for offset in range(0, len(payload), 3))
                if pixels != last_physical_pixels[node_id]:
                    physical_writes[node_id] += 1
                    last_physical_pixels[node_id] = pixels
                else:
                    identical_skips[node_id] += 1
                assert len(set(pixels)) == 1
                if _active(node_id, timestamp):
                    red, green, blue = pixels[0]
                    assert red == green == 0
                    assert 5 <= blue <= 37
                    levels_by_node[node_id].add(blue)
                else:
                    assert pixels == (BLACK,) * pixel_count
                packets[node_id] = pixels
            if 40.0 <= timestamp < 70.0:
                assert packets[2][0] == packets[8][0]

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
            node_id = 2 if address[0] == "192.168.31.58" else 8
            _, pixel_count = NODE_SPECS[node_id]
            payload = raw[DDP_HEADER_LEN:]
            pixels = tuple(tuple(payload[offset:offset + 3]) for offset in range(0, len(payload), 3))
            assert pixels == (BLACK,) * pixel_count
            physical_writes[node_id] += 1
            last_physical_pixels[node_id] = pixels

        assert len(levels_by_node[2]) == 32
        assert len(levels_by_node[8]) == 32
        assert output.health().logical_frames_sent == logical_frames
        assert output.health().packets_sent == logical_frames * 2
        assert physical_writes == {2: 313, 8: 624}
        assert identical_skips == {2: 812, 8: 501}
    finally:
        Config.reset()
