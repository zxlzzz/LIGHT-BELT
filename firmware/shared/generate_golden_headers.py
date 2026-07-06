"""Generate deterministic C/C++ golden-vector headers from JSON."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _bytes_literal(hex_string: str) -> str:
    data = bytes.fromhex(hex_string)
    return ", ".join(f"0x{byte:02X}" for byte in data)


def _header_guard(name: str) -> str:
    return name.upper().replace(".", "_").replace("-", "_") + "_"


def _generate(input_path: Path, output_path: Path, symbol_prefix: str) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    vectors = data["vectors"]
    guard = _header_guard(output_path.name)
    lines = [
        "// Generated from firmware/shared/" + input_path.name + ". Do not edit.",
        "#ifndef " + guard,
        "#define " + guard,
        "",
        "#include <stdint.h>",
        "#include <stddef.h>",
        "",
    ]
    for index, vector in enumerate(vectors):
        encoded = vector["encoded_hex"]
        symbol = f"{symbol_prefix}_{index}"
        lines.extend(
            [
                f"static const uint8_t {symbol}[] = {{{_bytes_literal(encoded)}}};",
                f"static const size_t {symbol}_len = sizeof({symbol});",
                "",
            ]
        )
    lines.extend(["#endif", ""])
    new_text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_text, encoding="utf-8", newline="\n")


def _generate_project_header(
    output_path: Path,
    rs485_header: str | None = None,
    udp_header: str | None = None,
) -> None:
    guard = _header_guard(output_path.name)
    lines = [
        "// Generated from firmware/shared golden-vector headers. Do not edit.",
        "#ifndef " + guard,
        "#define " + guard,
        "",
    ]
    if rs485_header:
        lines.append(f'#include "{rs485_header}"')
    if udp_header:
        lines.append(f'#include "{udp_header}"')
    lines.extend(["", "#endif", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    _generate(ROOT / "rs485_v2_golden.json", ROOT / "rs485_v2_golden.h", "RS485_V2_GOLDEN")
    _generate(ROOT / "udp_v2_golden.json", ROOT / "udp_v2_golden.h", "UDP_V2_GOLDEN")
    _generate_project_header(
        ROOT.parent / "stm32_rgbcct_node" / "test" / "golden_vectors.h",
        rs485_header="../../shared/rs485_v2_golden.h",
    )
    _generate_project_header(
        ROOT.parent / "esp32_ws2811_node" / "test" / "golden_vectors.h",
        udp_header="../../shared/udp_v2_golden.h",
    )


if __name__ == "__main__":
    main()
