import json
import subprocess
from pathlib import Path

from light_engine.outputs.rs485_v2 import RS485v2Packet
from light_engine.outputs.udp_v2 import UdpV2Packet


ROOT = Path("firmware/shared")


def test_golden_json_fields_and_codecs():
    rs485 = json.loads((ROOT / "rs485_v2_golden.json").read_text(encoding="utf-8"))
    udp = json.loads((ROOT / "udp_v2_golden.json").read_text(encoding="utf-8"))
    assert rs485["protocol"] == "rs485_v2"
    assert udp["protocol"] == "udp_v2"

    rs_vector = rs485["vectors"][0]
    rs_packet = RS485v2Packet(
        command=rs_vector["command"],
        node_id=rs_vector["node_id"],
        sequence=rs_vector["sequence"],
        r=rs_vector["r"],
        g=rs_vector["g"],
        b=rs_vector["b"],
        warm_white=rs_vector["warm_white"],
        cool_white=rs_vector["cool_white"],
        fade_ms=rs_vector["fade_ms"],
        flags=rs_vector["flags"],
    )
    assert rs_packet.encode().hex() == rs_vector["encoded_hex"]

    udp_vector = udp["vectors"][0]
    udp_packet = UdpV2Packet(
        message_type=udp_vector["message_type"],
        digital_node_id=udp_vector["digital_node_id"],
        flags=udp_vector["flags"],
        sequence=udp_vector["sequence"],
        pixels=[tuple(pixel) for pixel in udp_vector["pixels"]],
    )
    assert udp_packet.encode().hex() == udp_vector["encoded_hex"]


def test_header_generator_is_deterministic():
    subprocess.run(
        [".\\.python\\Scripts\\python.exe", "firmware/shared/generate_golden_headers.py"],
        check=True,
    )
    first = {
        path.name: path.read_text(encoding="utf-8")
        for path in (ROOT / "rs485_v2_golden.h", ROOT / "udp_v2_golden.h")
    }
    subprocess.run(
        [".\\.python\\Scripts\\python.exe", "firmware/shared/generate_golden_headers.py"],
        check=True,
    )
    second = {
        path.name: path.read_text(encoding="utf-8")
        for path in (ROOT / "rs485_v2_golden.h", ROOT / "udp_v2_golden.h")
    }
    assert first == second
    assert "0xA5, 0x5A" in first["rs485_v2_golden.h"]
    assert "0x4C, 0x45" in first["udp_v2_golden.h"]


def test_project_golden_headers_are_generated():
    subprocess.run(
        [".\\.python\\Scripts\\python.exe", "firmware/shared/generate_golden_headers.py"],
        check=True,
    )
    stm32 = Path("firmware/stm32_rgbcct_node/test/golden_vectors.h").read_text(
        encoding="utf-8"
    )
    esp32 = Path("firmware/esp32_ws2811_node/test/golden_vectors.h").read_text(
        encoding="utf-8"
    )
    assert "Generated from firmware/shared" in stm32
    assert "../../shared/rs485_v2_golden.h" in stm32
    assert "Generated from firmware/shared" in esp32
    assert "../../shared/udp_v2_golden.h" in esp32
