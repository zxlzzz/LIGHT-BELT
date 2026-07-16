from __future__ import annotations

import re
from pathlib import Path

import yaml


PROFILE = Path("config/profiles/cabin-lighting-v3-site-local.yaml")
FIRMWARE_DIR = Path("firmware/esp32_ws2811_node")
NODE_CONFIG_DIR = Path("firmware/esp32_ws2811_node/src/node_configs")
DEFINE_RE = re.compile(r"^#define\s+([A-Z0-9_]+)\s+(\d+)\s*$", re.MULTILINE)


def _defines(path: Path) -> dict[str, int]:
    return {
        name: int(value)
        for name, value in DEFINE_RE.findall(path.read_text(encoding="utf-8"))
    }


def _ini_section(text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\s*$([\s\S]*?)(?=^\[|\Z)",
        text,
        flags=re.MULTILINE,
    )
    assert match is not None, f"missing [{name}]"
    return match.group(1)


def test_site_esp32_headers_match_complete_udp_v3_mapping() -> None:
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    shared = _defines(FIRMWARE_DIR / "src/config.example.h")
    nodes = {item["node_id"]: item for item in profile["layout"]["digital_nodes"]}
    outputs: dict[int, list[dict]] = {node_id: [] for node_id in nodes}
    for output in profile["layout"]["digital_outputs"]:
        outputs[output["node_id"]].append(output)

    assert set(nodes) == set(range(1, 14))
    assert shared["UDP_PORT"] == 9001
    for node_id, node in nodes.items():
        configured = _defines(NODE_CONFIG_DIR / f"node_{node_id}.h")
        expected = sorted(outputs[node_id], key=lambda item: item["output_id"])

        assert configured["NODE_ID"] == node_id
        assert configured["NODE_IPV4_D"] == int(node["host"].rsplit(".", 1)[1])
        assert node["host"] == f"192.168.31.{configured['NODE_IPV4_D']}"
        assert node["port"] == shared["UDP_PORT"]
        assert configured["OUTPUT_COUNT"] == len(expected) == 1
        assert sum(item["pixel_count"] for item in expected) == node["pixel_count"]
        for index, output in enumerate(expected):
            assert configured[f"OUTPUT_{index}_ID"] == output["output_id"] == 1
            assert configured[f"OUTPUT_{index}_GPIO"] == output["gpio"] == 4
            assert configured[f"OUTPUT_{index}_PIXELS"] == output["pixel_count"]


def test_platformio_has_one_reproducible_environment_per_node() -> None:
    ini = (FIRMWARE_DIR / "platformio.ini").read_text(encoding="utf-8")
    expected_envs = {f"esp32-s3-node-{node_id}" for node_id in range(1, 14)}
    actual_envs = set(re.findall(r"^\[env:(esp32-s3-node-\d+)\]\s*$", ini, re.MULTILINE))

    assert actual_envs == expected_envs
    assert "[env:esp32-s3-devkitc-1]" not in ini
    platformio = _ini_section(ini, "platformio")
    assert re.search(r"^default_envs\s*=\s*native\s*$", platformio, re.MULTILINE)

    common = _ini_section(ini, "esp32-s3-common")
    assert "fastled" not in common.lower()
    production = _ini_section(ini, "esp32-s3-fixed-gpio4-production")
    assert re.search(
        r"^extends\s*=\s*esp32-s3-common\s*$", production, re.MULTILINE
    )
    assert "${esp32-s3-common.build_flags}" in production
    assert "-DLIGHT_BELT_FIXED_GPIO4_SPI=1" in production
    for node_id in range(1, 14):
        section = _ini_section(ini, f"env:esp32-s3-node-{node_id}")
        assert re.search(
            r"^extends\s*=\s*esp32-s3-fixed-gpio4-production\s*$",
            section,
            re.MULTILINE,
        )
        assert "${esp32-s3-fixed-gpio4-production.build_flags}" in section
        assert re.search(
            rf"^[ \t]*-DLIGHT_BELT_NODE_CONFIG={node_id}[ \t]*$",
            section,
            re.MULTILINE,
        )

    assert "platform = espressif32@7.0.1" in common
    assert "framework = arduino" in common
    assert "-DBOARD_HAS_PSRAM" in common
    assert "-DARDUINO_USB_CDC_ON_BOOT=1" in common

    legacy = _ini_section(ini, "esp32-s3-node2-legacy-diagnostic")
    assert re.search(
        r"^extends\s*=\s*esp32-s3-common\s*$", legacy, re.MULTILINE
    )
    assert "-DLIGHT_BELT_NODE_CONFIG=2" in legacy
    assert "-DLIGHT_BELT_NODE2_LEGACY_MULTI_OUTPUT=1" in legacy

    diagnostic = _ini_section(
        ini, "env:esp32-s3-node-2-fixed-gpio4-diagnostic"
    )
    assert re.search(
        r"^extends\s*=\s*esp32-s3-node2-legacy-diagnostic\s*$",
        diagnostic,
        re.MULTILINE,
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in diagnostic
    assert "-DLIGHT_BELT_FIXED_GPIO4_SPI=1" in diagnostic
    assert "-DLIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC=1" in diagnostic

    strip42_gpio4 = _ini_section(
        ini, "env:esp32-s3-node-2-fixed-gpio4-strip42-diagnostic"
    )
    assert "-DLIGHT_BELT_NODE_CONFIG=2" in strip42_gpio4
    assert "-DLIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC=1" in strip42_gpio4
    assert "-DLIGHT_BELT_NODE2_GPIO4_STRIP42_DIAGNOSTIC=1" in strip42_gpio4

    qio_diagnostic = _ini_section(
        ini, "env:esp32-s3-node-2-qio-parallel-diagnostic"
    )
    assert re.search(
        r"^extends\s*=\s*esp32-s3-node2-legacy-diagnostic\s*$",
        qio_diagnostic,
        re.MULTILINE,
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in qio_diagnostic
    assert "-DLIGHT_BELT_QIO_DIAGNOSTIC=1" in qio_diagnostic

    hybrid_diagnostic = _ini_section(
        ini, "env:esp32-s3-node-2-hybrid-fixed-diagnostic"
    )
    assert re.search(
        r"^extends\s*=\s*esp32-s3-node2-legacy-diagnostic\s*$",
        hybrid_diagnostic,
        re.MULTILINE,
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in hybrid_diagnostic
    assert "-DLIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC=1" in hybrid_diagnostic

    host_swap = _ini_section(
        ini, "env:esp32-s3-node-2-hybrid-spi-host-swap-diagnostic"
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in host_swap
    assert "-DLIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC=1" in host_swap
    assert "-DLIGHT_BELT_HYBRID_SPI_HOST_SWAP=1" in host_swap

    gpio5_spi3bit = _ini_section(
        ini, "env:esp32-s3-node-2-gpio5-spi3bit-diagnostic"
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in gpio5_spi3bit
    assert "-DLIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC=1" in gpio5_spi3bit
    assert "-DLIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC=1" in gpio5_spi3bit
    assert "-DLIGHT_BELT_HYBRID_SPI_HOST_SWAP=1" not in gpio5_spi3bit

    gpio5_short_t0 = _ini_section(
        ini, "env:esp32-s3-node-2-gpio5-short-t0-diagnostic"
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in gpio5_short_t0
    assert "-DLIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC=1" in gpio5_short_t0
    assert "-DLIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC=1" in gpio5_short_t0
    assert "-DLIGHT_BELT_HYBRID_SPI_HOST_SWAP=1" not in gpio5_short_t0

    gpio5_rmt = _ini_section(
        ini, "env:esp32-s3-node-2-gpio5-rmt-diagnostic"
    )
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in gpio5_rmt
    assert "-DLIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC=1" in gpio5_rmt
    assert "-DLIGHT_BELT_GPIO5_RMT_DIAGNOSTIC=1" in gpio5_rmt
    assert "-DLIGHT_BELT_HYBRID_SPI_HOST_SWAP=1" not in gpio5_rmt
    assert "-DLIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC=1" not in gpio5_rmt
    assert "-DLIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC=1" not in gpio5_rmt

    fastled = _ini_section(
        ini, "env:esp32-s3-node-2-fastled-diagnostic"
    )
    assert "fastled/FastLED @ 3.10.3" in fastled
    assert "${esp32-s3-node2-legacy-diagnostic.build_flags}" in fastled
    assert "-DLIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC=1" in fastled
    assert "-DFASTLED_RMT_BUILTIN_DRIVER=1" in fastled
    assert "-DFASTLED_RMT_MEM_BLOCKS=2" in fastled
    assert "-DFASTLED_RMT_MAX_CHANNELS=4" in fastled


def test_config_contract_keeps_topology_out_of_local_secrets() -> None:
    config = (FIRMWARE_DIR / "src/config.h").read_text(encoding="utf-8")
    shared = (FIRMWARE_DIR / "src/config.example.h").read_text(encoding="utf-8")
    local = (FIRMWARE_DIR / "src/config.local.example.h").read_text(
        encoding="utf-8"
    )
    node_headers = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(NODE_CONFIG_DIR.glob("*.h"))
    )

    for node_id in range(1, 14):
        assert f'#include "node_configs/node_{node_id}.h"' in config
        assert f"LIGHT_BELT_NODE_CONFIG == {node_id}" in config

    assert "node_configs/" not in local
    assert "NODE_ID" not in local
    assert "OUTPUT_COUNT" not in local
    assert "BRIGHTNESS_MAX" not in shared
    assert "#define COLOR_ORDER" not in shared
    assert "#define WS2811_COLOR_ORDER_GRB 1" in shared
    assert "#define WS2811_COLOR_ORDER WS2811_COLOR_ORDER_GRB" in shared
    assert not re.search(r"^#define\s+\S*DIR\S*", shared + node_headers, re.MULTILINE)


def test_native_environment_builds_all_pure_firmware_components() -> None:
    ini = (FIRMWARE_DIR / "platformio.ini").read_text(encoding="utf-8")
    native = _ini_section(ini, "env:native")

    for source in (
        "protocol.cpp",
        "frame_state.cpp",
        "owned_frame.cpp",
        "ws2811_spi_encoder.cpp",
        "ws2811_spi3_encoder.cpp",
        "ws2811_spi6_encoder.cpp",
        "ws2811_parallel_spi_encoder.cpp",
        "ws2811_rmt_encoder.cpp",
    ):
        assert f"+<{source}>" in native
