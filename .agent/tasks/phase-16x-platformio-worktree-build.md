# Phase ID

phase-16x-platformio-worktree-build

# Goal

Repair PlatformIO firmware build reproducibility in isolated agent worktrees so Phase 17 can pass its required firmware build gates.

This is an infrastructure-only fix. Do not modify show orchestration runtime, show acceptance scripts, show configs, tests/goldens, audio fixtures, protocol encoders, or firmware runtime behavior.

# Context

Phase 17 software acceptance previously reached and passed its core show orchestration checks, including:

- targeted show end-to-end acceptance test
- `scripts/show_acceptance.py`
- `scripts/show_acceptance.py --realtime-soak 300`
- full `pytest -q`
- `light_engine validate-show`
- `light_engine benchmark`

The remaining blocker was PlatformIO firmware compilation inside the isolated agent worktree.

Important distinction:

- Main repository firmware builds now pass:
  - `pio run -d firmware/stm32_rgbcct_node`
  - `pio run -d firmware/esp32_ws2811_node`
- But Phase 17 runs inside `.agent-worktrees/<phase>`, not the main repository.
- Therefore the fix must prove that firmware builds also pass in a fresh isolated git worktree.

Known failure pattern:

- STM32 may fail with:
  - `fatal error: bits/c++config.h: No such file or directory`
- ESP32 may fail due to package/platform/toolchain path resolution in isolated worktrees.

This is not a show orchestration runtime defect. It is a PlatformIO worktree build reproducibility defect.

# In Scope

Allowed files:

- `firmware/stm32_rgbcct_node/scripts/platformio_windows_sandbox.py`
- `firmware/esp32_ws2811_node/scripts/platformio_windows_sandbox.py`
- `firmware/stm32_rgbcct_node/platformio.ini` only if strictly necessary
- `firmware/esp32_ws2811_node/platformio.ini` only if strictly necessary
- `AGENTS.md` or `docs/CLOSED_LOOP_SPEC.md` only if needed to document the build rule
- `.agent/tasks/phase-16x-platformio-worktree-build.md`

# Out of Scope

Do not modify:

- `light_engine/**`
- `config/**`
- `scripts/show_acceptance.py`
- `scripts/agent_pipeline.py`
- `scripts/agent_campaign.py`
- `tests/test_show_e2e_acceptance.py`
- `tests/goldens/**`
- `tests/fixtures/audio/show_orchestration_v1/**`
- `.agent/tasks/phase-17-show-acceptance.md`
- protocol encoders
- firmware runtime behavior
- generated protocol golden vectors

Do not regenerate or modify these files:

- `firmware/esp32_ws2811_node/test/golden_vectors.h`
- `firmware/shared/rs485_v2_golden.h`
- `firmware/shared/udp_v2_golden.h`
- `firmware/stm32_rgbcct_node/test/golden_vectors.h`

# Required Implementation

## 1. STM32 PlatformIO package discovery

Update the STM32 Windows sandbox/prebuild script so it does not rely on only one hard-coded package directory.

It must search all relevant PlatformIO package locations:

1. `$PROJECT_PACKAGES_DIR`, if available from PlatformIO env substitution
2. `project_dir/.pio/packages`
3. `Path.home()/.platformio/packages`

The script must tolerate missing paths.

The script must de-duplicate candidate paths.

The script must be Windows-safe.

## 2. STM32 GCC ARM C++ include paths

When `toolchain-gccarmnoneeabi` is found, discover the C++ version directory dynamically.

Do not hard-code only `12.3.1` if the version directory can be discovered.

Expected structure is similar to:

- `toolchain-gccarmnoneeabi/arm-none-eabi/include/c++/<version>`
- `toolchain-gccarmnoneeabi/arm-none-eabi/include/c++/<version>/arm-none-eabi`

If the target `bits/c++config.h` exists under the target-specific include directory, prepend both paths to `CPPPATH`.

The final behavior must allow STM32 firmware to compile in a fresh isolated worktree.

## 3. ESP32 PlatformIO package discovery

Update the ESP32 Windows sandbox/prebuild script so it also searches:

1. `$PROJECT_PACKAGES_DIR`, if available from PlatformIO env substitution
2. `project_dir/.pio/packages`
3. `Path.home()/.platformio/packages`

The script must tolerate missing paths and de-duplicate candidate paths.

## 4. ESP32 Xtensa C++ include paths

When `toolchain-xtensa-esp32s3` is found, discover the C++ version directory dynamically.

Expected structure is similar to:

- `toolchain-xtensa-esp32s3/xtensa-esp32s3-elf/include/c++/<version>`
- `toolchain-xtensa-esp32s3/xtensa-esp32s3-elf/include/c++/<version>/xtensa-esp32s3-elf`

If the target `bits/c++config.h` exists under the target-specific include directory, prepend both paths to `CPPPATH`.

The final behavior must allow ESP32 firmware to compile in a fresh isolated worktree.

## 5. Diagnostic output

When running under Windows, each script should print concise diagnostic information showing:

- which package roots were considered
- which toolchain root was selected, if any
- which C++ include paths were added, if any

Do not print excessive recursive directory dumps.

If no valid toolchain include path is found, the script should print a clear warning but should not crash the build script itself. Let the compiler produce the final build error if the include path remains unavailable.

## 6. Avoid platformio.ini changes unless required

Prefer fixing only the two `platformio_windows_sandbox.py` scripts.

Only modify `platformio.ini` if the script-only fix cannot make fresh-worktree firmware builds pass.

If `platformio.ini` is modified, explain why in the final report.

# Required Verification

Run these commands from the main repository:

```powershell
.\.python\Scripts\python.exe scripts\agent_pipeline.py --preflight
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
```

Then verify in a fresh temporary git worktree, not the main repo:

```powershell
git worktree add -b tmp/platformio-worktree-smoke .agent-worktrees\_platformio-smoke HEAD

pio run -d .agent-worktrees\_platformio-smoke\firmware\stm32_rgbcct_node
pio run -d .agent-worktrees\_platformio-smoke\firmware\esp32_ws2811_node

git worktree remove .agent-worktrees\_platformio-smoke --force
git branch -D tmp/platformio-worktree-smoke
git worktree prune
```

Also run:

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

If PlatformIO regenerates or touches golden vector files only because of line endings, restore them before finalizing:

```powershell
git restore -- firmware/esp32_ws2811_node/test/golden_vectors.h `
  firmware/shared/rs485_v2_golden.h `
  firmware/shared/udp_v2_golden.h `
  firmware/stm32_rgbcct_node/test/golden_vectors.h
```

# Acceptance Criteria

This phase is successful only if all of the following are true:

* STM32 firmware builds in the main repository.
* ESP32 firmware builds in the main repository.
* STM32 firmware builds in a fresh temporary git worktree.
* ESP32 firmware builds in a fresh temporary git worktree.
* Full `pytest -q` passes.
* `git diff --check` passes.
* `git status --short` is clean except for intentional allowed changes.
* No show orchestration runtime files are modified.
* No show acceptance files are modified.
* No firmware runtime logic is modified.
* No protocol or firmware golden vectors are regenerated or modified.

# Required Report Evidence

Final report must include this table:

| Requirement | Implementation | Test | Evidence |
| ----------- | -------------- | ---- | -------- |

It must also include:

* exact files changed
* exact commands run
* return code for each command
* whether any PlatformIO package download occurred
* whether fresh worktree verification passed
* whether `platformio.ini` was modified and why
* whether any golden vectors changed and how they were handled
* suggested commit message

# Quality Constraints

* Do not add or broaden `skip` or `xfail`.
* Do not delete tests.
* Do not weaken assertions.
* Do not modify show orchestration behavior.
* Do not modify acceptance behavior.
* Do not modify firmware runtime behavior.
* Do not modify protocol encoders.
* Do not modify generated golden vectors.
* If the requested fix cannot be completed within the allowed files, report `BLOCKER` and explain the exact reason.

# Suggested Commit Message

Fix PlatformIO worktree firmware builds
