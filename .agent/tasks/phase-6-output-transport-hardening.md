# Phase 6 鈥?Output Transport Hardening and v1 Removal

## Phase ID

phase-6-output-transport-hardening

## Goal

Complete Phase 6 from `docs/IMPLEMENTATION_PLAN.md`: production/memory/fake modes, latest-frame queues, strict failure semantics, direct PhysicalFrame output, and deletion of transitional v1/RoutedFrame code.

## Allowed Files

- light_engine/outputs/**
- light_engine/engine/__init__.py
- light_engine/models.py
- light_engine/cli/__init__.py
- config/outputs.yaml
- tests/test_output_safety.py
- tests/test_output_health.py
- tests/test_engine.py
- tests/test_serial.py
- tests/test_udp.py
- tests/test_pipeline.py
- tests/test_legacy_compat.py
- tests/test_phased_output_matrix.py
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md

## Forbidden Files

- firmware/**
- light_engine/analysis/**
- light_engine/media/**
- light_engine/effects/**
- config/layout.yaml
- .agent/**
- AGENTS.md
- CLAUDE.md

## Acceptance Criteria

- Add explicit PRODUCTION, MEMORY, and FAKE modes.
- PRODUCTION never silently falls back to memory.
- Latest-frame queue capacity is one with overwrite semantics.
- RS-485 packets for one logical frame remain contiguous.
- One complete digital-node frame is one UDP datagram.
- `send_all()` consumes PhysicalFrame directly.
- Remove legacy v1 output classes, compatibility adapter, and RoutedFrame.
- Safe-state shutdown remains all black with SAFE_STATE flag.
- Output failure isolation and health counters remain correct.
- Existing non-v1 behavior remains passing.
- No hardware-verification claim is made.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_output_safety.py tests/test_output_health.py tests/test_engine.py tests/test_serial.py tests/test_udp.py -q
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
```

## Commit Message

Phase 6: Harden output transport, delete v1 outputs and RoutedFrame

