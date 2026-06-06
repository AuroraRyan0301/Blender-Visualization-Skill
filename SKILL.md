---
name: blender_kit
description: >-
  Unified Blender 4.2 Cycles rendering pipeline. GPU-only. Single entry
  scripts/render.py composes a four-stage pipeline: scene assembly
  (mesh / parts / URDF) → material → camera trajectory → output passes
  (rgb / depth / normal / mask). Trajectories include static views, full
  orbit, half orbit, and hemisphere-jitter for novel-view sampling.
---

# blender_kit

Single entry point. Four-stage composable pipeline.

```bash
$BLENDER -b --python scripts/render.py -- \
    --scene <mesh|parts|urdf>     # WHAT to render
    --material <...>              # HOW the surface looks
    --trajectory <...> --frames N # WHERE the camera goes
    --outputs <...>               # WHICH passes get written
    --out_dir DIR --res N --samples N
```

## Hard policies

- **GPU only.** `setup_cycles` raises `NoGPUError` without a CUDA/OPTIX device.
- **Cycles only.** Workbench is forbidden for production output.
- **sRGB color transfer.** PNG uses Standard view transform; EXR is Raw and
  decoded downstream via `linear_to_srgb` (IEC 61966-2-1).
- **No emission for visualization.** Closed cavities under env-only legitimately
  render RGB=0. Use `two_sided` for unreliable winding.

## Stage 1 — Scene

```
--scene mesh   --mesh PATH                       single mesh, no parts
--scene parts  --mesh PATH --face_ids PATH       per-face part IDs
--scene urdf   --urdf PATH [--mesh_root PATH]    URDF tree at rest pose
```

`--mesh` accepts a path to obj/ply/glb/gltf/stl/fbx or a KaiNinja obj-id
(resolves to `/gs/bs/tga-koike-shanda/yurh/KaiNinja_v2/preprocess/<id>/`).

```
--select_parts {all | i,j,k}     filter parts (parts/urdf)
--normalize whole                bbox over all original geometry -> unit cube
--normalize selected             bbox over selected subset -> unit cube
--normalize none                 no transform
--source_frame {auto, y_up, z_up}  override per-format default
```

Per-format axis defaults: OBJ / GLB / GLTF / FBX = Y-up, PLY / STL / OFF =
Z-up. URDF-referenced meshes are treated as already in link frame
(no swap), per REP-103.

## Stage 2 — Material

```
--material diffuse        Principled BSDF (--color RGB --roughness --metallic)
--material two_sided      Backface-flipped diffuse
--material tab20          Categorical per-object color (tab20)
--material pbr            PBR pack via --pbr_dir + --uv_scale --normal_strength
                          --displacement_scale
--material uv_color       Emission (U, V, 0) — UV painted onto surface
--material uv_checker     Procedural checker on UV (--checker_scale)
--material embedded       URDF: use URDF-declared <material><color rgba/>
--material mask           Flat grey (passes carry the mask info)
--material file_embedded  Use OBJ+MTL / GLB / FBX file-embedded materials
                          (mesh scene only — imports via bpy, keeps textures)
```

Defaults: `mesh→diffuse`, `parts→tab20`, `urdf→embedded`.
`--auto_unwrap` runs `bpy.ops.uv.smart_project` if the mesh has no UV layer.

CC0 PBR sources:
- Poly Haven: https://polyhaven.com/textures
- ambientCG: https://ambientcg.com/

Recognized basename substrings (case-insensitive):

| slot | substrings | colorspace |
|---|---|---|
| base_color | `diff` `color` `basecolor` `albedo` | sRGB |
| roughness | `rough` `roughness` | Non-Color |
| normal | `nor_gl` `normal_gl` `normal` | Non-Color |
| metallic | `metal` `metalness` | Non-Color |
| ao | `ao` `ambientocclusion` | Non-Color |
| displacement | `disp` `displacement` `height` | Non-Color |

## Stage 3 — Camera trajectory

| name | shape | args |
|---|---|---|
| `static` (default) | N views around a 360° ring | `--start_az` (default 35), `--elevation`, `--distance` |
| `circle` | full 360° turntable | `--start_az`, `--elevation`, `--distance` |
| `half_circle` | sweep of `--sweep` degrees | `--start_az`, `--sweep` (default 180), `--elevation`, `--distance` |
| `hemisphere_jitter` | random samples in (`±az_range`, `±el_range`, `±distance_jitter`) | `--center_az`, `--center_el`, `--az_range`, `--el_range`, `--distance`, `--distance_jitter`, `--seed` |

```
--frames N                       number of camera frames
--distance 2.5                   factor × scene_diag
```

## Batch + multi-node

`--manifest <jobs.jsonl>` runs many jobs in one Blender process — Cycles
startup, OPTIX kernel JIT, and library imports are amortized across the
batch. Per-job error isolation (a missing mesh doesn't kill the run).

`jobs.jsonl` — one JSON object per line, each its own job. Keys match the
single-shot CLI flags. CLI flags become defaults shared by all jobs.

```jsonl
{"scene": "mesh", "mesh": "abc.glb", "out_dir": "out/abc"}
{"scene": "parts", "mesh": "xyz", "out_dir": "out/xyz", "select_parts": "0,2"}
{"scene": "urdf", "urdf": "robot.urdf", "out_dir": "out/robot"}
```

```bash
$BLENDER -b --python scripts/render.py -- \
        --manifest jobs.jsonl \
        --trajectory circle --frames 60 --samples 64 --res 1024
```

**Multi-node sharding** — `--rank R --world W` takes only this rank's slice
of the manifest (`jobs[R::W]`). Each shard runs in its own Blender process,
typically pinned to one GPU.

Example: 10 nodes × 4 GPUs each = 40 workers, qsub-style:

```bash
# Per node:
for GPU in 0 1 2 3; do
    CUDA_VISIBLE_DEVICES=$GPU \
    $BLENDER -b --python scripts/render.py -- \
        --manifest big_jobs.jsonl \
        --rank $((NODE_IDX * 4 + GPU)) \
        --world 40 \
        --trajectory circle --frames 4 --samples 64 --res 512 \
        > log_node${NODE_IDX}_gpu${GPU}.txt 2>&1 &
done
wait
```

GPU pinning is via `CUDA_VISIBLE_DEVICES` set by the launcher — must come
BEFORE Blender starts (Cycles caches device enumeration on first init).

## Stage 4 — Outputs

```
--outputs rgb                    Blender writes PNG directly (Standard transform)
--outputs rgb,depth,normal       multilayer EXR + per-pass decode
--outputs mask                   alpha + indexob; BOX filter + samples=1 mode
--outputs rgb,depth,normal,mask  everything in one EXR (rgb degraded by mask mode)
```

`mask` expands to `alpha + indexob`. When mask is in outputs, the renderer
switches to mask mode (BOX filter, samples=1, `film_transparent=True`, black
world). If you want both clean rgb and clean masks, run two passes.

Multilayer EXR goes to `out_dir/f{NNNN}/0001.exr`. Decode under a system
python that has `pip install OpenEXR matplotlib`:

```bash
python scripts/exr_to_png.py --dir out_dir
```

Auto-detects which layers each EXR contains and emits `rgb.png`, `depth.png`
(viridis_r colorbar in meters), `normal.png` (sRGB + unit-sphere legend),
`mask.png` (silhouette), `mask_p{NNN}.png` (per part).

For PNG outputs, `--mp4 --fps N` stitches frames into `out_dir/video.mp4`
via ffmpeg.

## Repo layout

```
blender_kit/
├── SKILL.md
├── README.md
├── install.sh
├── envmaps/                       # studio.exr ships (Poly Haven, CC0)
├── lib/
│   ├── scene_assembly.py          # Scene + from_mesh / from_parts / from_urdf
│   ├── material_registry.py       # --material -> factory(obj, idx)
│   ├── trajectory.py              # camera trajectories
│   ├── passes.py                  # output passes -> compositor wiring
│   ├── decode.py                  # multilayer EXR -> per-pass PNGs
│   ├── render_pipeline.py         # render_frames(...) loop
│   ├── urdf.py                    # URDF parse + Blender load
│   ├── cli.py                     # shared argparse + post-processing
│   ├── video.py                   # ffmpeg PNG-sequence -> mp4
│   ├── materials.py               # shader builders
│   ├── camera.py / world.py / render_setup.py / compositor.py / scene.py
│   ├── exr_reader.py / postproc.py / uv.py
│   ├── mesh_io.py / normalize.py / normals.py / coord.py
├── scripts/
│   ├── render.py                  # THE entry point
│   ├── exr_to_png.py              # EXR -> PNGs (system python)
│   ├── frames_to_mp4.py           # PNG sequence -> mp4
│   ├── convert_mesh.py            # mesh format conversion
│   └── fetch_polyhaven_pbr.sh     # CC0 PBR pack fetcher
└── examples/smoke.sh
```

## Adding a new entry

`scripts/render.py` is the only entry. To add a new material or pass:

- New material → add a branch in `lib/material_registry.make_factory` +
  declare in `NAMES`.
- New pass → register the socket + view-layer flag in
  `lib/passes._PASSES`, optionally an alias in `ALIASES`, and a decode
  branch in `lib/decode.decode_frame`.
- New trajectory → add a function in `lib/trajectory.py` + register in
  `_REGISTRY`, and a help line in `lib/cli.add_camera_args`.

Per-stage parameters live in `lib/cli.add_*_args` so they're shared by
anything that wants the same args.
