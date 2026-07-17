# Documentation Index

This index is the entry point for repository documentation. A document's
directory defines its lifecycle; filenames alone do not determine authority.

## Authority

1. `CLAUDE.md` contains permanent project facts and architecture invariants.
2. `docs/CLOSED_LOOP_SPEC.md` defines target behavior and protocol contracts.
3. `docs/IMPLEMENTATION_PLAN.md` records the currently approved work only.
4. Current source and tests provide evidence of implemented behavior.

## Current instructions

- [Cabin Lighting V3 operator guide](current/cabin-lighting-v3-operator-guide.md)
- [ESP32 Windows commissioning](current/esp32-windows-commissioning.md)
- [Show v2 authoring](current/show-v2-authoring.md)
- [WS2811 show stability investigation](current/ws2811-show-stability-investigation.md)

## Reference

- [Effect reference](reference/effect-reference.md)
- [Host API v1](reference/host-api-v1.md)
- [Host API v1 changelog](reference/host-api-v1-changelog.md)
- `reference/host-api-v1.openapi.yaml`

## Acceptance

- [Cabin Lighting V3 Phase 31 software acceptance](acceptance/cabin-lighting-v3-phase31-software-acceptance.md)
- [Authoring modulation v1 software acceptance](acceptance/authoring-modulation-v1-software-acceptance.md)
- [Show orchestration v1 software acceptance](acceptance/show-orchestration-v1-software-acceptance.md)
- [Hardware acceptance checklist](acceptance/hardware-acceptance-checklist.md)
- [Repository governance closeout](acceptance/repository-governance-closeout.md)

Software acceptance is not hardware acceptance. All physical installation and
timing claims remain **NOT HARDWARE VERIFIED** until the hardware checklist is
completed with real evidence.

## History

`history/` preserves superseded plans, old prototype descriptions, and
completed campaign instructions. Historical files may intentionally contain
old paths, RGBW terminology, deprecated commands, or measurements captured at
the time. They are evidence, not current instructions.

The superseded five-controller Phase 29 report is retained at
`history/acceptance/cabin-lighting-v3-phase29-software-acceptance.md`; it does
not describe the Phase 31 production topology.

See [Repository Governance](repository-governance.md) for lifecycle and cleanup
rules.
