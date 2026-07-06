# NOT HARDWARE VERIFIED.
import os
from pathlib import Path

Import("env")


def _matching_sandbox_project() -> Path | None:
    sandbox_cwd = Path("C:/Users/CodexSandboxOffline/.codex/.sandbox/cwd")

    try:
        if not sandbox_cwd.exists():
            return None

        matches = [
            path
            for path in sandbox_cwd.iterdir()
            if (path / "platformio.ini").is_file()
            and (path / "src" / "protocol.h").is_file()
        ]
    except OSError:
        # The Codex sandbox path may exist but be inaccessible to the
        # current Windows user. It is only an optional compatibility path.
        return None

    if len(matches) != 1:
        return None

    return matches[0]


if os.name == "nt":
    project_dir = Path(env.subst("$PROJECT_DIR"))
    shim_dir = project_dir / "tools"
    env.PrependENVPath("PYTHONPATH", str(shim_dir))

    sandbox_project = _matching_sandbox_project()
    if sandbox_project is not None:
        cxx_root = (
            sandbox_project
            / ".pio"
            / "packages"
            / "toolchain-xtensa-esp32s3"
            / "xtensa-esp32s3-elf"
            / "include"
            / "c++"
            / "8.4.0"
        )
        cxx_target = cxx_root / "xtensa-esp32s3-elf"
        if cxx_root.exists() and cxx_target.exists():
            env.Prepend(CPPPATH=[str(cxx_target), str(cxx_root)])
