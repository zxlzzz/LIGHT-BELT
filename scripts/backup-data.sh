#!/usr/bin/env bash
set -euo pipefail
REPO="/home/topeet/LIGHT-BELT"
SRC="$REPO/data"
DEST="/home/topeet/lb-data-backups"
KEEP=14
[ -d "$SRC" ] || { echo "[backup-data] 源目录不存在: $SRC"; exit 0; }
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARBALL="$DEST/data-$STAMP.tar.gz"
tar -czf "$TARBALL" -C "$REPO" data 2>/dev/null
ls -1t "$DEST"/data-*.tar.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
echo "[backup-data] 已备份 -> $TARBALL ($(du -h "$TARBALL" | cut -f1))，保留最近 $KEEP 份"