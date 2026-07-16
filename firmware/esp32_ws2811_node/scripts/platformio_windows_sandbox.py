# NOT HARDWARE VERIFIED.
import os
import re
from pathlib import Path

Import("env")


def _path_from_subst(token: str, project_dir: Path) -> Path | None:
    value = env.subst(token)
    if not value or value == token:
        return None

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return path


def _dedupe_paths(paths: list[Path | None]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []

    for path in paths:
        if path is None:
            continue

        try:
            key = os.path.normcase(str(path.resolve()))
        except OSError:
            key = os.path.normcase(str(path.absolute()))

        if key in seen:
            continue

        seen.add(key)
        result.append(path)

    return result


def _package_roots(project_dir: Path) -> list[Path]:
    return _dedupe_paths(
        [
            _path_from_subst("$PROJECT_PACKAGES_DIR", project_dir),
            project_dir / ".pio" / "packages",
        ]
    )


def _version_key(path: Path) -> tuple[tuple[int, object], ...]:
    parts: list[tuple[int, object]] = []
    for part in re.split(r"(\d+)", path.name):
        if part.isdigit():
            parts.append((0, int(part)))
        elif part:
            parts.append((1, part))
    return tuple(parts)


def _find_toolchain(package_roots: list[Path], package_name: str) -> Path | None:
    for package_root in package_roots:
        toolchain_root = package_root / package_name
        if toolchain_root.is_dir():
            return toolchain_root
    return None


def _find_cxx_include_paths(
    toolchain_root: Path | None, target_triple: str
) -> list[Path]:
    if toolchain_root is None:
        return []

    cxx_base = toolchain_root / target_triple / "include" / "c++"
    try:
        version_dirs = [path for path in cxx_base.iterdir() if path.is_dir()]
    except OSError:
        return []

    for cxx_root in sorted(version_dirs, key=_version_key, reverse=True):
        cxx_target = cxx_root / target_triple
        if (cxx_target / "bits" / "c++config.h").is_file():
            return [cxx_target, cxx_root]

    return []


def _print_diagnostics(
    package_roots: list[Path],
    toolchain_root: Path | None,
    include_paths: list[Path],
) -> None:
    print("[platformio-windows-sandbox] package roots considered:")
    for package_root in package_roots:
        print(f"  - {package_root}")

    if toolchain_root is not None:
        print(f"[platformio-windows-sandbox] selected toolchain: {toolchain_root}")
    else:
        print("[platformio-windows-sandbox] WARNING: toolchain-xtensa-esp32s3 not found")

    if include_paths:
        print("[platformio-windows-sandbox] C++ include paths added:")
        for include_path in include_paths:
            print(f"  - {include_path}")
    else:
        print(
            "[platformio-windows-sandbox] WARNING: valid Xtensa C++ include paths not found"
        )


if os.name == "nt":
    project_dir = Path(env.subst("$PROJECT_DIR")).expanduser()
    temp_dir = project_dir / ".pio" / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    for variable in ("TEMP", "TMP", "TMPDIR"):
        os.environ[variable] = str(temp_dir)
        env["ENV"][variable] = str(temp_dir)

    shim_dir = project_dir / "tools"
    env.PrependENVPath("PYTHONPATH", str(shim_dir))

    package_roots = _package_roots(project_dir)
    toolchain_root = _find_toolchain(package_roots, "toolchain-xtensa-esp32s3")
    include_paths = _find_cxx_include_paths(toolchain_root, "xtensa-esp32s3-elf")

    if include_paths:
        env.Prepend(CPPPATH=[str(path) for path in include_paths])

    print(f"[platformio-windows-sandbox] compiler temp: {temp_dir}")
    _print_diagnostics(package_roots, toolchain_root, include_paths)
