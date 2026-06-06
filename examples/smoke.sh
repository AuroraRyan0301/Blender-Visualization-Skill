#!/bin/bash
# One-obj smoke test through all three render pipelines.
#
# Usage:
#   bash examples/smoke.sh /path/to/mesh.obj [out_dir]
#   bash examples/smoke.sh <kainin-obj-id>   [out_dir]
#
# Requires:
#   $BLENDER points at a Blender 4.2 binary, or ./blender/blender exists
#   (e.g. after `bash install.sh`).
set -e

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Resolve Blender binary
if [[ -z "${BLENDER:-}" ]]; then
    if [[ -x "$KIT/blender/blender" ]]; then
        BLENDER="$KIT/blender/blender"
    elif command -v blender >/dev/null 2>&1; then
        BLENDER=$(command -v blender)
    else
        echo "[smoke] no Blender found. Run \`bash install.sh\` or set BLENDER=/path/to/blender"
        exit 1
    fi
fi

OBJ="${1:-}"
OUT="${2:-/tmp/blender_kit_smoke}"
if [[ -z "$OBJ" ]]; then
    echo "Usage: $0 <obj-id-or-path> [out_dir]"
    exit 1
fi

mkdir -p "$OUT"
echo "[smoke] blender=$BLENDER"
echo "[smoke] obj=$OBJ  out=$OUT"

echo "[1/3] render_diffuse"
"$BLENDER" -b --python "$KIT/scripts/render_diffuse.py" -- \
    --obj "$OBJ" --out_dir "$OUT/diffuse" --views 2 --samples 32 --res 512 \
    >"$OUT/diffuse.log" 2>&1
echo "      -> $OUT/diffuse/"

echo "[2/3] render_parts (skipped if no face_ids.npy)"
if "$BLENDER" -b --python "$KIT/scripts/render_parts.py" -- \
    --obj "$OBJ" --out_dir "$OUT/parts" --views 2 --samples 32 --res 512 \
    >"$OUT/parts.log" 2>&1; then
    echo "      -> $OUT/parts/"
else
    echo "      skipped: $OUT/parts.log"
fi

echo "[3/3] render_depth_normal"
"$BLENDER" -b --python "$KIT/scripts/render_depth_normal.py" -- \
    --obj "$OBJ" --out_dir "$OUT/dn" --views 2 --samples 16 --res 512 \
    >"$OUT/dn.log" 2>&1
echo "      -> $OUT/dn/v*/0001.exr"

echo "[exr->png] (needs OpenEXR pip pkg in PATH python)"
if python "$KIT/scripts/exr_to_png.py" --exr_dir "$OUT/dn" 2>>"$OUT/dn.log"; then
    echo "      -> $OUT/dn/grid.png"
else
    echo "      decode failed (likely missing OpenEXR). See $OUT/dn.log"
fi

echo "[done]"
