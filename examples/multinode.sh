#!/bin/bash
# Multi-GPU launcher template: 1 node with N GPUs, runs N ranks of a manifest.
#
# For multi-node, set NODE_IDX / NODE_TOTAL in your submit script and run
# this on every node — the global rank becomes NODE_IDX * NGPUS + local GPU.
set -e

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${BLENDER:=$KIT/blender/blender}"
: "${MANIFEST:?Set MANIFEST=/path/to/jobs.jsonl}"
: "${NODE_IDX:=0}"
: "${NODE_TOTAL:=1}"

NGPUS=$(nvidia-smi -L | wc -l)
WORLD=$((NODE_TOTAL * NGPUS))
echo "[multinode] node=$NODE_IDX/$NODE_TOTAL  gpus_per_node=$NGPUS  world=$WORLD"

for GPU in $(seq 0 $((NGPUS - 1))); do
    RANK=$((NODE_IDX * NGPUS + GPU))
    LOG="rank${RANK}.log"
    echo "  spawning rank $RANK on GPU $GPU -> $LOG"
    CUDA_VISIBLE_DEVICES=$GPU \
    "$BLENDER" -b --python "$KIT/scripts/render.py" -- \
        --manifest "$MANIFEST" --rank "$RANK" --world "$WORLD" \
        "$@" >"$LOG" 2>&1 &
done

wait
echo "[multinode] all ranks done on node $NODE_IDX"
