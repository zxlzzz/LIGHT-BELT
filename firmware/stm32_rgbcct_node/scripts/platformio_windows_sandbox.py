# NOT HARDWARE VERIFIED.
import os
from pathlib import Path

Import("env")

if os.name == "nt":
    cxx_root = (
        Path.home()
        / ".platformio"
        / "packages"
        / "toolchain-gccarmnoneeabi"
        / "arm-none-eabi"
        / "include"
        / "c++"
        / "12.3.1"
    )
    cxx_target = cxx_root / "arm-none-eabi"
    if cxx_root.exists() and cxx_target.exists():
        env.Prepend(CPPPATH=[str(cxx_target), str(cxx_root)])
