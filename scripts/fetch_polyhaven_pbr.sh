#!/usr/bin/env bash
# Fetch a Poly Haven PBR texture pack into a folder for render_pbr.py.
#
# Usage:
#   bash fetch_polyhaven_pbr.sh <slug> [<dest_dir>] [<resolution>]
# Example:
#   bash fetch_polyhaven_pbr.sh wood_floor /tmp/wood 1k
#
# Pack catalogue: https://polyhaven.com/textures (CC0).
set -e

SLUG="${1:-wood_floor}"
DEST="${2:-./$SLUG}"
RES="${3:-1k}"
BASE="https://dl.polyhaven.org/file/ph-assets/Textures/png/${RES}/${SLUG}"

mkdir -p "$DEST"
echo "[fetch] $SLUG @ $RES -> $DEST"
for K in diff rough nor_gl disp ao arm; do
    URL="${BASE}/${SLUG}_${K}_${RES}.png"
    if curl -fL --silent --output "$DEST/${SLUG}_${K}_${RES}.png" "$URL" 2>/dev/null; then
        echo "  ok ${K}"
    fi
done
echo "[fetch] done. point --pbr_dir at $DEST"
ls -la "$DEST"
