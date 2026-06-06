#!/bin/bash
# One-obj smoke test through all three render pipelines.
# Renders to /tmp/blender_kit_smoke/.
set -e

BLENDER=/gs/fs/tga-koike-shanda4/yurh/blender-4.2.18-linux-x64/blender
KIT=/gs/fs/tga-koike-shanda4/yurh/blender_kit
OBJ_ID=${1:-0001870f6136d8e4e4097157b9461289}
OUT=${2:-/tmp/blender_kit_smoke}

mkdir -p "$OUT"
echo "[smoke] obj_id=$OBJ_ID  out=$OUT"

echo "[1/3] render_diffuse"
$BLENDER -b --python $KIT/scripts/render_diffuse.py -- \
    --obj $OBJ_ID --out_dir $OUT/diffuse --views 2 --samples 32 --res 512 \
    >$OUT/diffuse.log 2>&1

echo "[2/3] render_parts"
$BLENDER -b --python $KIT/scripts/render_parts.py -- \
    --obj $OBJ_ID --out_dir $OUT/parts --views 2 --samples 32 --res 512 \
    >$OUT/parts.log 2>&1

echo "[3/3] render_depth_normal"
$BLENDER -b --python $KIT/scripts/render_depth_normal.py -- \
    --obj $OBJ_ID --out_dir $OUT/dn --views 2 --samples 16 --res 512 \
    >$OUT/dn.log 2>&1

echo "[exr->png]"
python $KIT/scripts/exr_to_png.py --exr_dir $OUT/dn

echo "[done] artifacts:"
ls -la $OUT/diffuse/*.png $OUT/parts/*.png $OUT/dn/v*/rgb.png 2>/dev/null
echo "$OUT/dn/grid.png"
