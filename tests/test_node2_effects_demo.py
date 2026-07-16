"""Contracts for the node 2 code-controlled therapeutic demonstration."""

import random
import re
from dataclasses import replace
from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import (
    AudioFeatures,
    DigitalStrip,
    EffectContext,
    MusicControlState,
    PixelFrame,
    VideoFeatures,
)
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import FLAG_KEY_FRAME, UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE_PATH = Path("config/profiles/node2-effects-demo.yaml")
SHOW_PATH = Path("config/shows/node2-effects-demo.yaml")
ACTIVE_STRIPS = ("strip_41", "strip_42")
CODE_EFFECTS = {
    "static",
    "breath",
    "color_wave",
    "calm",
    "color_wipe",
    "comet",
    "twinkle",
    "chase",
}


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * 0.95)]


def _path_pwm(frame) -> tuple[int, ...]:
    by_id = {strip.strip_id: strip for strip in frame.strips}
    return tuple(
        round(channel * 255)
        for strip_id in ACTIVE_STRIPS
        for pixel in by_id[strip_id].pixels
        for channel in pixel
    )


def _transform(config: Config) -> OutputTransform:
    transform = config.get("outputs.transform")
    return OutputTransform(
        global_brightness=config.get("system.smoothing.max_brightness"),
        gamma=config.get("system.smoothing.gamma"),
        power_limit=transform["power_limit"],
        per_zone_warm_bias=transform["per_zone_warm_bias"],
        per_zone_cool_bias=transform["per_zone_cool_bias"],
    )


def test_node2_show_uses_reference_style_digital_strip_targets() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE_PATH)
        layout = Layout.from_config(config)
        show = load_show(SHOW_PATH, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout)

        assert show.id == "node2-effects-demo"
        assert show.duration == 90.0
        assert not show.virtual_paths

        active = [cue for cue in show.cues if cue.priority > 0]
        assert {cue.effect.id for cue in active} == CODE_EFFECTS
        assert all(cue.effect.mode == "fixed" for cue in show.cues)
        assert all(cue.audio_control is None for cue in show.cues)
        assert all(cue.audio_modulation is None for cue in show.cues)
        assert all(cue.target.kind == "digital_strip" for cue in show.cues)
        assert {cue.target.id for cue in show.cues} == set(ACTIVE_STRIPS)
        assert all(track.target.kind == "digital_strip" for track in show.brightness_tracks)
        assert {track.id for track in show.brightness_tracks} == {"bt_dim_41", "bt_dim_42"}
        assert {track.target.id for track in show.brightness_tracks} == set(ACTIVE_STRIPS)

        pairs: dict[str, dict[str, object]] = {}
        for cue in show.cues:
            match = re.fullmatch(r"(.+)_(41|42)", cue.id)
            assert match is not None, cue.id
            base_id, suffix = match.groups()
            assert cue.target.id == f"strip_{suffix}"
            pairs.setdefault(base_id, {})[suffix] = cue
        for base_id, pair in pairs.items():
            assert set(pair) == {"41", "42"}, base_id
            left = pair["41"]
            right = pair["42"]
            assert (
                left.start,
                left.end,
                left.priority,
                left.effect,
                left.color,
                left.origin,
                left.transition,
            ) == (
                right.start,
                right.end,
                right.priority,
                right.effect,
                right.color,
                right.origin,
                right.transition,
            )

        for effect_id in CODE_EFFECTS:
            cues = [cue for cue in active if cue.effect.id == effect_id]
            assert len(cues) >= 4, effect_id
            fingerprints = {
                (
                    repr(dict(cue.effect.params)),
                    cue.origin,
                    repr(cue.color),
                )
                for cue in cues
            }
            assert len(fingerprints) >= 2, effect_id

        for cue in active:
            if cue.effect.id == "chase":
                assert cue.effect.params["color_source"] == "static"
                assert cue.effect.params["beat_boost"] == 0.0
            if cue.effect.id == "comet":
                assert cue.color.mode == "solid"

        for strip_id in ACTIVE_STRIPS:
            coverage_end = 0.0
            strip_cues = [cue for cue in active if cue.target.id == strip_id]
            for cue in sorted(strip_cues, key=lambda item: (item.start, item.end)):
                assert cue.start <= coverage_end
                coverage_end = max(coverage_end, cue.end)
            assert coverage_end == show.duration

        for job in runtime.jobs:
            assert tuple(strip.id for strip in job.resolved.digital_strips) == (
                job.cue.target.id,
            )
        assert {strip.id for strip in layout.strips} == {
            "strip_41",
            "strip_42",
            "strip_43",
        }
    finally:
        Config.reset()


def _render_media_trace(*, extreme_media: bool) -> tuple[tuple[int, ...], ...]:
    previous_random = random.getstate()
    random.seed(20260714)
    Config.reset()
    try:
        config = Config.get_instance(PROFILE_PATH)
        layout = Layout.from_config(config)
        show = load_show(SHOW_PATH, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout)
        transform = _transform(config)

        video = None
        audio = None
        music = None
        if extreme_media:
            video = VideoFeatures(
                timestamp=0.0,
                average_rgb=(1.0, 0.0, 1.0),
                dominant_rgb=(0.0, 1.0, 1.0),
                zone_colors={
                    "left": (1.0, 0.0, 0.0),
                    "right": (0.0, 0.0, 1.0),
                    "center": (1.0, 1.0, 1.0),
                    "top": (0.0, 1.0, 0.0),
                    "bottom": (1.0, 0.0, 1.0),
                },
                brightness=1.0,
                saturation=1.0,
                scene_change=1.0,
            )
            audio = AudioFeatures(
                timestamp=0.0,
                rms=1.0,
                bass=1.0,
                mid=1.0,
                treble=1.0,
                spectral_flux=1.0,
                beat=True,
                onset=1.0,
                silence=False,
            )
            music = MusicControlState(
                timestamp=0.0,
                tempo_bpm=180.0,
                tempo_confidence=1.0,
                beat_phase=1.0,
                beat_strength=1.0,
                beat_regularity=1.0,
                energy=1.0,
                energy_trend=1.0,
                transient=1.0,
                bass_ambient=1.0,
                bass_pulse=1.0,
                spectral_motion=1.0,
            )

        fps = 10.0
        trace = []
        for sequence in range(1, int(show.duration * fps)):
            timestamp = sequence / fps
            base = black_base_frame(
                timestamp=timestamp,
                sequence=sequence,
                analog_zones=layout.zones,
                digital_strips=layout.strips,
            )
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                    video_features=video,
                    audio_features=audio,
                    music_control_state=music,
                ),
                base,
            )
            by_id = {strip.strip_id: strip for strip in logical.strips}
            assert all(pixel == (0.0, 0.0, 0.0) for pixel in by_id["strip_43"].pixels)
            trace.append(_path_pwm(transform.apply_to_frame(logical)))
        return tuple(trace)
    finally:
        Config.reset()
        random.setstate(previous_random)


def test_node2_show_is_bit_exact_invariant_to_video_audio_and_beat() -> None:
    assert _render_media_trace(extreme_media=False) == _render_media_trace(
        extreme_media=True
    )


def test_node2_first_17_seconds_encode_one_exact_warm_udp_frame_at_30_fps() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE_PATH)
        layout = Layout.from_config(config)
        show = load_show(SHOW_PATH, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout)
        transform = _transform(config)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        expected_outputs = {1: (4, 10), 2: (5, 20), 3: (6, 20)}
        active_colors: set[tuple[int, int, int]] = set()
        fps = 30.0

        for sequence in range(1, int(17.0 * fps)):
            timestamp = sequence / fps
            base = black_base_frame(
                timestamp=timestamp,
                sequence=sequence,
                analog_zones=layout.zones,
                digital_strips=layout.strips,
            )
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                ),
                base,
            )
            transformed = transform.apply_to_frame(logical)
            expected_pixels = {
                strip.strip_id: tuple(
                    tuple(round(channel * 255) for channel in pixel)
                    for pixel in strip.pixels
                )
                for strip in transformed.strips
            }
            output.send_frame(mapping.map(transformed))

            datagrams = output.get_sent_datagrams()
            assert len(datagrams) == sequence
            raw, address = datagrams[-1]
            assert address == ("192.168.31.202", 9001)
            assert len(raw) == 201
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=2,
                expected_outputs=expected_outputs,
            )
            assert packet is not None
            assert packet.sequence == sequence
            assert packet.media_timestamp_us == round(timestamp * 1_000_000)
            assert packet.flags == (FLAG_KEY_FRAME if sequence == 1 else 0)
            assert packet.apply_at_us is None
            assert [
                (item.output_id, item.gpio, len(item.pixels))
                for item in packet.outputs
            ] == [(1, 4, 10), (2, 5, 20), (3, 6, 20)]

            pixels = {item.output_id: item.pixels for item in packet.outputs}
            assert pixels[1] == expected_pixels["strip_41"]
            assert pixels[2] == expected_pixels["strip_42"]
            assert pixels[3] == expected_pixels["strip_43"]
            assert all(len(set(item)) == 1 for item in pixels.values())
            assert pixels[1][0] == pixels[2][0]
            assert pixels[3][0] == (0, 0, 0)
            red, green, blue = pixels[1][0]
            assert red > 0
            assert red >= green >= blue
            active_colors.add(pixels[1][0])

        assert len(active_colors) >= 25
    finally:
        Config.reset()


def test_node2_mapping_preserves_distinct_strip_identity_and_direction() -> None:
    Config.reset()
    try:
        layout = Layout.from_config(Config.get_instance(PROFILE_PATH))
        strip_pixels = {
            "strip_41": [(index / 20.0, 0.0, 0.0) for index in range(1, 11)],
            "strip_42": [(0.0, index / 40.0, 0.0) for index in range(1, 21)],
            "strip_43": [(0.0, 0.0, index / 40.0) for index in range(1, 21)],
        }
        frame = PixelFrame(
            timestamp=1.0,
            sequence=77,
            strips=[
                DigitalStrip(strip_id, len(pixels), pixels)
                for strip_id, pixels in strip_pixels.items()
            ],
        )
        output = UdpOutputV3()
        output.open()
        output.send_frame(PhysicalMapping(layout).map(frame))

        datagrams = output.get_sent_datagrams()
        assert len(datagrams) == 1
        packet = UdpV3Packet.decode(
            datagrams[0][0],
            expected_node_id=2,
            expected_outputs={1: (4, 10), 2: (5, 20), 3: (6, 20)},
        )
        assert packet is not None
        by_output = {item.output_id: item.pixels for item in packet.outputs}
        for output_id, strip_id in (
            (1, "strip_41"),
            (2, "strip_42"),
            (3, "strip_43"),
        ):
            assert by_output[output_id] == tuple(
                tuple(round(channel * 255) for channel in pixel)
                for pixel in strip_pixels[strip_id]
            )
    finally:
        Config.reset()


def test_node2_show_is_visible_comparative_and_bounded_at_final_pwm() -> None:
    previous_random = random.getstate()
    random.seed(20260714)
    Config.reset()
    try:
        config = Config.get_instance(PROFILE_PATH)
        layout = Layout.from_config(config)
        show = load_show(SHOW_PATH, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout)
        reference = replace(
            show,
            cues=tuple(cue for cue in show.cues if cue.priority == 0),
        )
        reference_runtime = ShowRuntime.from_layout(reference, layout)
        transform = _transform(config)
        active = [cue for cue in show.cues if cue.priority > 0]
        visibility = {cue.id: [] for cue in active}
        snapshots: dict[str, tuple[int, ...]] = {}
        snapshot_distance = {cue.id: float("inf") for cue in active}

        frame_max_steps: list[float] = []
        frame_mean_steps: list[float] = []
        previous_pwm = (0,) * 90
        peak_pwm = 0
        fps = float(config.get("system.output_fps"))
        for sequence in range(1, int(show.duration * fps)):
            timestamp = sequence / fps
            context = EffectContext(
                timestamp=timestamp,
                delta_time=1.0 / fps,
                sequence=sequence,
            )
            base = black_base_frame(
                timestamp=timestamp,
                sequence=sequence,
                analog_zones=layout.zones,
                digital_strips=layout.strips,
            )
            final = transform.apply_to_frame(runtime.render(context, base))
            reference_final = transform.apply_to_frame(
                reference_runtime.render(context, base)
            )
            pwm = _path_pwm(final)
            reference_pwm = _path_pwm(reference_final)
            peak_pwm = max(peak_pwm, *pwm)
            steps = [abs(current - previous) for current, previous in zip(pwm, previous_pwm)]
            frame_max_steps.append(max(steps))
            frame_mean_steps.append(sum(steps) / len(steps))
            previous_pwm = pwm

            for cue in active:
                if not cue.start <= timestamp < cue.end:
                    continue
                delta = [abs(current - bed) for current, bed in zip(pwm, reference_pwm)]
                visibility[cue.id].append(max(delta))
                midpoint = (cue.start + cue.end) / 2.0
                distance = abs(timestamp - midpoint)
                if distance < snapshot_distance[cue.id]:
                    snapshot_distance[cue.id] = distance
                    snapshots[cue.id] = pwm

        shutdown_steps = list(previous_pwm)
        frame_max_steps.append(max(shutdown_steps))
        frame_mean_steps.append(sum(shutdown_steps) / len(shutdown_steps))

        for cue_id, deltas in visibility.items():
            assert deltas, cue_id
            assert max(deltas) >= 2, (cue_id, max(deltas))
            assert sum(delta >= 1 for delta in deltas) >= len(deltas) * 0.2, cue_id

        comparisons = (
            ("static_warm_orange_41", "static_orange_to_warm_yellow_41"),
            ("breath_five_second_low_floor_41", "breath_eight_second_high_floor_41"),
            ("comet_warm_yellow_baseline_41", "comet_faster_41"),
            ("comet_faster_41", "comet_long_soft_tail_41"),
            ("calm_warm_six_second_41", "calm_green_twelve_second_41"),
            ("wave_broad_and_slow_41", "wave_narrower_with_hue_drift_41"),
            ("wipe_from_start_41", "wipe_from_end_fast_41"),
            ("wipe_from_center_41", "wipe_from_edges_fast_41"),
            ("chase_forward_41", "chase_reverse_narrow_41"),
            ("chase_reverse_narrow_41", "chase_bounce_complete_return_41"),
            ("twinkle_sparse_long_fade_41", "twinkle_denser_shorter_palette_41"),
        )
        for left, right in comparisons:
            difference = [
                abs(a - b) for a, b in zip(snapshots[left], snapshots[right])
            ]
            assert max(difference) >= 2, (left, right, max(difference))

        assert 10 <= peak_pwm <= 50, peak_pwm
        assert _p95(frame_max_steps) <= 18, _p95(frame_max_steps)
        assert max(frame_max_steps) <= 20, max(frame_max_steps)
        assert _p95(frame_mean_steps) <= 1.5, _p95(frame_mean_steps)
        assert max(frame_mean_steps) <= 4.0, max(frame_mean_steps)
    finally:
        Config.reset()
        random.setstate(previous_random)
