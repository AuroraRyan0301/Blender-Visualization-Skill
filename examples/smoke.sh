#!/bin/bash
# Quick end-to-end smoke test of the unified pipeline.
#
# Usage:
#   bash examples/smoke.sh <mesh-path-or-kainin-obj-id> [out_dir]
set -e

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${BLENDER:-}" ]]; then
    if [[ -x "$KIT/blender/blender" ]]; then
        BLENDER="$KIT/blender/blender"
    elif command -v blender >/dev/null 2>&1; then
        BLENDER=$(command -v blender)
    else
        echo "[smoke] no Blender. Run bash install.sh or set BLENDER=/path/to/blender"
        exit 1
    fi
fi

OBJ="${1:-}"
OUT="${2:-/tmp/blender_kit_smoke}"
if [[ -z "$OBJ" ]]; then
    echo "Usage: $0 <mesh-or-obj-id> [out_dir]"
    exit 1
fi

mkdir -p "$OUT"
echo "[smoke] blender=$BLENDER  obj=$OBJ  out=$OUT"

echo "[1] mesh + diffuse + rgb"
"$BLENDER" -b --python "$KIT/scripts/render.py" -- \
    --scene mesh --mesh "$OBJ" \
    --out_dir "$OUT/diffuse" --trajectory circle --frames 4 --samples 16 --res 256 \
    >"$OUT/diffuse.log" 2>&1
echo "    -> $OUT/diffuse/"

echo "[2] parts + tab20 + rgb+depth+normal+mask (multilayer EXR)"
"$BLENDER" -b --python "$KIT/scripts/render.py" -- \
    --scene parts --mesh "$OBJ" \
    --material tab20 --outputs rgb,depth,normal,mask \
    --out_dir "$OUT/parts" --trajectory static --frames 2 --samples 1 --res 256 \
    >"$OUT/parts.log" 2>&1 || echo "    (skipped — no face_ids)"

if [[ -d "$OUT/parts/f0000" ]]; then
    python "$KIT/scripts/exr_to_png.py" --dir "$OUT/parts" 2>>"$OUT/parts.log" \
        && echo "    -> $OUT/parts/f0000/{rgb,depth,normal,mask*}.png"
fi

echo "[done]"
