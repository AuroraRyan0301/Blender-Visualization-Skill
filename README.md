# Blender-Visualization-Skill

Offline Blender 4.2 Cycles rendering kit, packaged as a "skill" with stable
entry points. Stop writing one-off render scripts — invoke this kit instead.

```bash
bash install.sh                            # one-shot: downloads Blender 4.2 LTS
export BLENDER="$PWD/blender/blender"
$BLENDER -b --python scripts/render_diffuse.py -- --obj input.glb --out_dir out/
```

Three render entry points, one EXR decoder, one mesh-format converter. Each
runs in Blender's bundled Python; the EXR decoder runs in your system Python
(needs `pip install OpenEXR matplotlib numpy`).

## Capabilities

| Script | What it produces |
|---|---|
| `scripts/render_diffuse.py` | Realistic Cycles render under HDRI lighting. Principled BSDF or two-sided diffuse. PNG (sRGB) or EXR (scene-linear). |
| `scripts/render_parts.py` | Per-part `tab20` color render. Reads `face_ids.npy` aligned to the mesh's face order. |
| `scripts/render_depth_normal.py` | RGB + depth + normal via OPEN_EXR_MULTILAYER. Decoded to PNGs with a proper depth colorbar (meters) and a unit-sphere normal legend. |
| `scripts/convert_mesh.py` | Convert between `.obj` / `.ply` / `.glb` / `.gltf` / `.stl` / `.fbx` with correct per-format axis handling. |
| `scripts/exr_to_png.py` | EXR → PNG via `linear_to_srgb`. Single-file or multilayer mode. |

## Hard policies

- **GPU only.** `setup_cycles` raises `NoGPUError` if no CUDA/OPTIX device is
  visible. CPU rendering is forbidden by design.
- **Cycles only.** Workbench is forbidden — production output must be ray-traced.
- **sRGB color transfer.** PNG output uses Blender's `Standard` view transform
  (linear → sRGB). EXR output is `Raw` (no transform), decoded downstream via
  `linear_to_srgb` (the IEC 61966-2-1 piecewise curve).
- **No emission shaders.** Closed cavities can legitimately render RGB=0 under
  env-only lighting — that's physically correct, not a bug. Use `--two_sided`
  diffuse for uncertain face winding.

## Mesh format axis handling

Each format's native frame is converted to Blender Z-up automatically:

| ext           | native frame   |
|---------------|----------------|
| `.obj`        | Y-up (Wavefront) |
| `.glb` `.gltf`| Y-up (glTF 2.0)  |
| `.fbx`        | Y-up           |
| `.ply` `.stl` `.off` | Z-up (kit convention; override per file with `--source_frame y_up` if needed) |

## Repo layout

```
.
├── SKILL.md                  # operational doc (this kit's API)
├── README.md                 # this file (public-facing overview)
├── install.sh                # downloads Blender 4.2 LTS into ./blender/
├── envmaps/
│   ├── studio.exr            # default HDRI: Poly Haven brown_photostudio_06 (CC0)
│   └── README.md             # drop additional HDRIs here
├── lib/                      # building blocks
│   ├── coord.py              # OBJ Y-up <-> Blender Z-up
│   ├── mesh_io.py            # multi-format load/save/convert
│   ├── normalize.py          # unit-cube/unit-sphere + diag/center
│   ├── normals.py            # fix_normals / split_doubles / offset
│   ├── materials.py          # diffuse_realistic / two_sided / tab20
│   ├── camera.py             # add_orbit_camera / add_look_at_camera
│   ├── world.py              # set_world_hdri / set_world_black
│   ├── render_setup.py       # setup_cycles (GPU-only) / enable_aux_passes
│   ├── compositor.py         # setup_multilayer_exr / setup_png_output
│   ├── scene.py              # clear_scene / add_mesh_from_arrays
│   ├── exr_reader.py         # read_multilayer (needs OpenEXR pkg)
│   └── postproc.py           # linear_to_srgb / depth colorbar / normal legend
├── scripts/                  # entry points
│   ├── render_diffuse.py
│   ├── render_parts.py
│   ├── render_depth_normal.py
│   ├── convert_mesh.py
│   └── exr_to_png.py
└── examples/
    └── smoke.sh
```

## Install

```bash
git clone https://github.com/AuroraRyan0301/Blender-Visualization-Skill.git
cd Blender-Visualization-Skill
bash install.sh                 # downloads Blender 4.2 LTS into ./blender/
export BLENDER="$PWD/blender/blender"

# OpenEXR decoder (system python)
pip install OpenEXR matplotlib numpy
```

`install.sh` is idempotent; safe to re-run. macOS/Windows users should install
Blender 4.2 manually from https://www.blender.org/download/ and point
`$BLENDER` at the binary.

A 2k studio HDRI (`envmaps/studio.exr`, from [Poly Haven](https://polyhaven.com/a/brown_photostudio_06), CC0) ships
with the repo as the default `--hdri`. Drop other `*.exr` files into
`envmaps/` to use them by filename.

## Quick start

```bash
# 1. realistic render, 4 views
$BLENDER -b --python scripts/render_diffuse.py -- \
    --obj input.glb --out_dir out/diffuse --views 4 --samples 64 \
    --hdri studio.exr

# 2. per-part tab20 render (needs face_ids.npy aligned to mesh face order)
$BLENDER -b --python scripts/render_parts.py -- \
    --obj input.obj --face_ids face_ids.npy --out_dir out/parts --views 4

# 3. depth+normal pass via multilayer EXR
$BLENDER -b --python scripts/render_depth_normal.py -- \
    --obj input.obj --out_dir out/dn --views 4
python scripts/exr_to_png.py --exr_dir out/dn   # -> rgb.png, depth.png, normal.png, grid.png

# 4. convert mesh formats with correct axis handling
$BLENDER -b --python scripts/convert_mesh.py -- --in mesh.obj --out mesh.glb
```

## Output format

- `--output_format png` (default): 8-bit sRGB PNG. Blender applies the
  Standard view transform. Open directly in any viewer.
- `--output_format exr`: 32-bit scene-linear single-layer EXR. Decode via
  `scripts/exr_to_png.py --exr_file <path>` to apply `linear_to_srgb` and get
  a PNG.

The depth+normal pipeline always writes multilayer EXR (`rgb`, `depth`,
`normal` slots) since geometry passes need to stay in linear / canonical units.

## Why this exists

We kept rewriting Blender boilerplate every time we needed a render. This kit
captures it once — Cycles config, GPU enforcement, multi-format coord
conversion, multilayer EXR, depth colorbar in meters, normal sphere legend —
so callers only state intent (which mesh, which views, which envmap).

See `SKILL.md` for the full operational reference.

## License

MIT.
