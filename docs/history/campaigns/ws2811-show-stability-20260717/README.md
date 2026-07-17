# WS2811 Show-Stability Freeze Record

This directory is the publish-safe record for the 2026-07-17 two-node asset
freeze. The corresponding local snapshot preserves the exact field binaries,
Host sources, firmware sources, profiles, Shows, tests, and investigation
documents.

## Why the binaries are not in Git

The onsite ESP32 application images embed the local Wi-Fi credential used at
build time. Publishing those bytes would disclose that credential. The exact
binaries therefore remain in the ignored local freeze and firmware baseline
directories. Git retains their acquisition record, byte lengths, SHA-256
identities, behavior, and restoration constraints without retaining the secret
bytes.

| Node | Application bytes | SHA-256 |
|---|---:|---|
| Node 2 / strip 41 | 727456 | `469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0` |
| Node 8 / strip 42 | 727952 | `C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B` |

Both were read from onsite flash offset `0x10000` with esptool 4.11.0 without
an erase or write operation, and both exactly matched their previously recorded
field identities.

## Published evidence

- `asset-manifest.md`: key profile, Show, test, document, and binary hashes.
- `field-readback.md`: ports, MACs, read lengths, and readback results.
- `iteration-history.md`: the technical path from the VCCB correction through
  content dedupe, inter-node offset, all-effects playback, and virtual paths.
- `test-purposes.md`: what each retained test and Show proves and does not prove.

The live evidence ledger remains
`docs/current/ws2811-show-stability-investigation.md`; the concise operational
handoff remains `docs/current/ws2811-emergency-handoff.md`.

## Frozen conclusion

The checkpoint produces useful and often excellent effects, including a
color-changing comet across one authored 30-group virtual path. Rare wrong-color
events remain possible, including strip-41 events when Node 2 is the only active
transmitter. This record is **NOT HARDWARE VERIFIED** for production and does
not establish arbitrary APP color control, 30 FPS, Scheduled playback, strict
synchronization, or long-duration stability.
