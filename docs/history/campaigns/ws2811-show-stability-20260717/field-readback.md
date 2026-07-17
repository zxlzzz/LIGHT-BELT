# Onsite Application Readback Record

Date: 2026-07-17

Both boards were placed in download mode and read with esptool 4.11.0. No
erase, write, or upload command was issued.

## Node 2

```text
Port: COM7
MAC: E0:72:A1:D3:30:3C
Command operation: read_flash
Offset: 0x10000
Length: 727456
SHA-256: 469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0
Recorded identity match: yes
```

## Node 8

```text
Port: COM13
MAC: 28:84:85:8A:36:B0
Command operation: read_flash
Offset: 0x10000
Length: 727952
SHA-256: C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B
Recorded identity match: yes
Existing retained file match: yes
```

Esptool hard-reset each board after its read. These hashes identify the exact
application bytes in the two onsite boards at freeze time. They do not by
themselves verify visual behavior, electrical timing, or production fitness.
