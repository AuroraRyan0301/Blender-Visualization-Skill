# Blender-Visualization-Skill

Offline Blender 4.2 Cycles rendering kit, packaged as a "skill" with one
unified entry point and a four-stage composable pipeline.

```bash
$BLENDER -b --python scripts/render.py -- \
    --scene mesh --mesh input.glb \
    --material diffuse \
    --trajectory circle --frames 60 \
    --outputs rgb,depth,normal --mp4
```

## Install

```bash
git clone https://github.com/AuroraRyan0301/Blender-Visualization-Skill.git
cd Blender-Visualization-Skill
bash install.sh                          # downloads Blender 4.2 LTS into ./blender/
export BLENDER="$PWD/blender/blender"
pip install OpenEXR matplotlib numpy     # for scripts/exr_to_png.py
```

A 2k studio HDRI (`envmaps/studio.exr`, Poly Haven brown_photostudio_06, CC0)
ships as the default `--hdri`.

## Hard policies

- **GPU only.** No GPU → `NoGPUError`. CPU rendering is forbidden.
- **Cycles only.** Workbench is forbidden.
- **sRGB color transfer.** PNG = Blender Standard view transform; EXR = Raw
  scene-linear, decoded downstream via `linear_to_srgb`.
- **No emission shaders for visualization.** Closed-cavity facets under
  env-only lighting legitimately render RGB=0; use `--material two_sided` for
  unreliable face winding.

## Pipeline (four stages, every render goes through these)

```
   1. Scene assembly      2. Material         3. Camera             4. Outputs
   ----------------       ---------------     ------------------    ----------------
   --scene mesh           --material          --trajectory          --outputs
   --scene parts            diffuse             static                rgb
   --scene urdf             two_sided           circle                depth
                            tab20               half_circle           normal
   --normalize              pbr                 hemisphere_jitter     mask
     whole / selected /     uv_color                                  (any subset,
     none                   uv_checker          --frames N            comma list)
                            embedded            --start_az
   --select_parts                               --elevation
     all | 0,2,5                                --distance
                                                ...                   --mp4 (rgb only)
```

### 1. Scene assembly

Three sources of geometry; all return a `Scene` with `objects`, `center`,
`diag`, optional `part_id` and `world_matrix` per object.

```
--scene mesh        --mesh PATH                        single mesh, no parts
--scene parts       --mesh PATH --face_ids PATH        mesh + per-face part IDs
--scene urdf        --urdf PATH [--mesh_root PATH]     URDF tree at rest pose
--scene voxels      --npz PATH                         voxel cubes per part
--scene arrows      --npz PATH                         arrow primitives
--scene attraction  --npz PATH                         KaiNinja attraction field
--scene bboxes      --npz PATH                         per-part bounding boxes
--scene ovoxel      --npz PATH [--src_axis y_up|z_up]  decoded dual-contour mesh
```

Selection + normalization:

```
--select_parts {all | i,j,k}     filter parts (only for parts/urdf scenes)
--normalize whole                bbox over ALL geometry  -> unit cube
--normalize selected             bbox over SELECTED subset -> unit cube (recenters)
--normalize none                 pass-through, no transform
```

Mesh format axis handling: OBJ / GLB / GLTF / FBX = Y-up, PLY / STL / OFF =
Z-up. Auto-converted to Blender Z-up. Override per file with `--source_frame`.
For URDF, referenced meshes are treated as already in link frame (Z-up, no
swap).

### 2. Material

```
--material diffuse        Principled BSDF + --color, --roughness, --metallic
--material two_sided      Backface-flipped diffuse (opaque)
--material tab20          Categorical per-part (uses object index)
--material pbr            Poly Haven / ambientCG folder via --pbr_dir
--material uv_color       Emission (R=U, G=V) — surface-painted UV viz
--material uv_checker     Procedural checker on UV — stretch viz (--checker_scale)
--material embedded       For URDF: use URDF-declared <material><color>
--material mask           Grey diffuse (passes carry the mask data)
--material file_embedded  Use OBJ+MTL / GLB / FBX file-embedded materials
                          (mesh scene only)
```

Defaults: `mesh→diffuse`, `parts→tab20`, `urdf→embedded`.
`uv_color` / `uv_checker` honor `--auto_unwrap` to smart-project if no UV layer.

### 3. Camera trajectory

| name | shape | args |
|---|---|---|
| `static` (default) | N views evenly around a circle at `--elevation` | `--start_az`, `--elevation`, `--distance` |
| `circle` | full 360° orbit | same |
| `half_circle` | partial sweep of `--sweep` degrees | `--start_az`, `--sweep`, `--elevation`, `--distance` |
| `hemisphere_jitter` | random samples on a hemisphere patch | `--center_az`, `--center_el`, `--az_range`, `--el_range`, `--distance`, `--distance_jitter`, `--seed` |

### 4. Outputs

```
--outputs rgb                       (default) — Blender writes PNG directly
--outputs rgb,depth,normal          rgb + geometry passes -> multilayer EXR
--outputs mask                      silhouette + per-part masks (BOX filter, samples=1)
--outputs rgb,depth,normal,mask     everything in one shot (rgb degraded by mask mode)
```

`mask` is an alias for `alpha,indexob`. Multilayer EXR output goes to
`out_dir/f{NNNN}/0001.exr`. Decode to per-pass PNGs:

```bash
python scripts/exr_to_png.py --dir out_dir
```

Auto-detects which passes the EXRs contain (rgb, depth, normal, alpha,
indexob) and emits PNGs accordingly (`mask.png` + per-part `mask_pNNN.png`
when indexob is present).

For PNG-only outputs, `--mp4 --fps N` stitches into `out_dir/video.mp4` via
ffmpeg.

## Quick recipes

```bash
# 60-frame realistic turntable mp4
$BLENDER -b --python scripts/render.py -- \
    --scene mesh --mesh input.glb \
    --trajectory circle --frames 60 --mp4 --fps 30

# Half-orbit per-part tab20 video
$BLENDER -b --python scripts/render.py -- \
    --scene parts --mesh <id> \
    --material tab20 --trajectory half_circle --frames 30 --sweep 180 --mp4

# Single part recentered (selected normalize) + PBR wood
bash scripts/fetch_polyhaven_pbr.sh wood_floor /tmp/wood 1k
$BLENDER -b --python scripts/render.py -- \
    --scene parts --mesh <id> --select_parts 0 --normalize selected \
    --material pbr --pbr_dir /tmp/wood --auto_unwrap \
    --trajectory circle --frames 24 --mp4

# All-passes EXR + decode
$BLENDER -b --python scripts/render.py -- \
    --scene parts --mesh <id> \
    --outputs rgb,depth,normal,mask --trajectory static --frames 4
python scripts/exr_to_png.py --dir out_dir

# URDF robot at rest, full orbit
$BLENDER -b --python scripts/render.py -- \
    --scene urdf --urdf robot.urdf \
    --trajectory circle --frames 60 --mp4
```

## Batch + multi-node

`--manifest jobs.jsonl` runs many jobs in one Blender process. Saves the
5–10s Cycles/OPTIX startup per job. Per-job error isolation.

`jobs.jsonl` — one JSON object per line; keys match CLI flag names:

```jsonl
{"scene": "mesh", "mesh": "a.glb", "out_dir": "out/a"}
{"scene": "parts", "mesh": "b", "out_dir": "out/b", "select_parts": "0,3"}
```

```bash
$BLENDER -b --python scripts/render.py -- \
        --manifest jobs.jsonl --trajectory circle --frames 60
```

**Multi-node** — `--rank R --world W` runs only `jobs[R::W]` slice. Pin GPU
via `CUDA_VISIBLE_DEVICES` set by the launcher (must be before Blender starts).

```bash
# Node N of 10, GPU G of 4:
for GPU in 0 1 2 3; do
    CUDA_VISIBLE_DEVICES=$GPU \
    $BLENDER -b --python scripts/render.py -- \
        --manifest big.jsonl --rank $((N * 4 + GPU)) --world 40 &
done; wait
```

## Repo layout

```
.
├── SKILL.md                  # full API reference
├── README.md                 # this file
├── install.sh                # downloads Blender 4.2 LTS
├── envmaps/studio.exr        # default HDRI (Poly Haven, CC0)
├── lib/                      # all the building blocks
│   ├── scene_assembly.py     # Scene + from_mesh/from_parts/from_urdf
│   ├── material_registry.py  # --material -> factory(obj, idx) -> Material
│   ├── trajectory.py         # static / circle / half_circle / hemisphere_jitter
│   ├── passes.py             # rgb/depth/normal/mask -> compositor wiring
│   ├── decode.py             # multilayer EXR -> per-pass PNGs
│   ├── render_pipeline.py    # the one frame loop
│   ├── urdf.py               # URDF parser + Blender loader
│   ├── cli.py                # shared argparse helpers
│   ├── video.py              # ffmpeg frames -> mp4
│   ├── materials.py          # shader builders
│   ├── camera.py             # place_camera / orbit / look_at
│   ├── world.py              # set_world_hdri / set_world_black
│   ├── render_setup.py       # setup_cycles (GPU-only)
│   ├── compositor.py         # multilayer/mask EXR wiring
│   ├── scene.py              # add_mesh_from_arrays / clear / world_aabb
│   ├── exr_reader.py         # read_multilayer
│   ├── postproc.py           # linear_to_srgb / colorbars / sphere legend
│   ├── uv.py                 # smart_unwrap / 2D layout PNG
│   ├── mesh_io.py            # multi-format load/save/convert
│   ├── normalize.py          # standalone normalize helpers
│   ├── normals.py            # fix_normals / split_doubles / offset
│   └── coord.py              # OBJ Y-up <-> Blender Z-up
├── scripts/
│   ├── render.py             # THE entry point
│   ├── exr_to_png.py         # post-decode multilayer EXR -> PNGs
│   ├── frames_to_mp4.py      # PNG sequence -> mp4 (ffmpeg)
│   ├── convert_mesh.py       # format-to-format conversion
│   └── fetch_polyhaven_pbr.sh # CC0 PBR pack fetcher
└── examples/smoke.sh
```

## License

MIT.
