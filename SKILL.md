---
name: blender_kit
description: >-
  Reusable Blender 4.2 Cycles rendering kit. GPU-only (CPU rendering is
  forbidden, Workbench is forbidden). Multi-format mesh IO (obj/ply/glb/gltf/
  stl/fbx) with correct per-format axis handling. Three render entry points:
  realistic diffuse under HDRI, tab20 per-part coloring, and depth+normal
  geometry passes via OPEN_EXR_MULTILAYER. PNG output uses sRGB encoding;
  EXR output is scene-linear, decoded downstream via linear_to_srgb.
---

# blender_kit

Offline Blender rendering as a skill. Always invoke a script in this kit
instead of writing ad-hoc render code.

## Hard policies

- **GPU only.** `setup_cycles` raises `NoGPUError` if no CUDA/OPTIX device is
  visible. ssh into a GPU node (node_q / node_h / node_f) before invoking.
- **Cycles only.** Workbench is forbidden for production output.
- **sRGB color transfer.** PNGs encode via `linear_to_srgb` (Blender's
  Standard view transform). EXRs are scene-linear; decode with
  `scripts/exr_to_png.py` which applies `linear_to_srgb`.
- **No emission shaders for visualization.** Use two-sided diffuse for
  uncertain face winding. Closed cavities can legitimately render RGB=0
  under env-only lighting — that's physically correct, not a bug.

## Layout

```
blender_kit/
├── SKILL.md
├── envmaps/                        # HDRI symlinks
├── lib/
│   ├── coord.py                    # OBJ Y-up <-> Blender Z-up
│   ├── mesh_io.py                  # multi-format load/save/convert
│   ├── normalize.py                # unit-cube / unit-sphere + diag/center
│   ├── normals.py                  # fix_normals / split_doubles / offset
│   ├── materials.py                # diffuse_realistic / two_sided / tab20
│   ├── camera.py                   # add_orbit_camera / add_look_at_camera
│   ├── world.py                    # set_world_hdri / set_world_black
│   ├── render_setup.py             # setup_cycles (GPU-only) / enable_aux_passes
│   ├── compositor.py               # setup_multilayer_exr / setup_png_output
│   ├── scene.py                    # clear_scene / add_mesh_from_arrays
│   ├── exr_reader.py               # read_multilayer (needs OpenEXR pkg)
│   └── postproc.py                 # linear_to_srgb / depth colorbar / normal legend
├── scripts/
│   ├── render_diffuse.py           # realistic Cycles render (--keep_materials for OBJ+MTL/GLB)
│   ├── render_parts.py             # tab20 per-part diffuse render per view
│   ├── render_pbr.py               # PBR texture pack (Poly Haven / ambientCG)
│   ├── render_uv.py                # UV-as-color + checker + 2D layout
│   ├── render_depth_normal.py      # geometry passes -> multilayer EXR
│   ├── convert_mesh.py             # format-to-format conversion
│   ├── exr_to_png.py               # EXR -> PNG via linear_to_srgb
│   └── fetch_polyhaven_pbr.sh      # one-shot CC0 PBR pack fetcher
└── examples/
    └── smoke.sh
```

## Mesh formats and coord axes

Each format's native frame is handled automatically. Override only if a
particular file violates its format's convention.

| ext | native frame | who applies the swap |
|-----|--------------|----------------------|
| .obj | Y-up (Wavefront) | manual parser in `mesh_io.load_obj` + `coord.obj_to_blender_pts` |
| .glb / .gltf | Y-up (glTF 2.0) | Blender's gltf importer (built-in) |
| .fbx | Y-up | Blender's fbx importer |
| .ply | Z-up (kit convention) | Blender importer; we rotate if `--source_frame y_up` |
| .stl | Z-up (kit convention) | Blender importer; we rotate if `--source_frame y_up` |
| .off | Z-up | manual loader (no bpy operator) |

Override per script with `--source_frame {auto, y_up, z_up}`.

## Install

```bash
git clone https://github.com/AuroraRyan0301/Blender-Visualization-Skill.git
cd Blender-Visualization-Skill
bash install.sh                # downloads Blender 4.2 LTS Linux x64 into ./blender/
export BLENDER="$PWD/blender/blender"
pip install OpenEXR matplotlib numpy   # for scripts/exr_to_png.py
```

A 2k `studio.exr` HDRI from Poly Haven ships in `envmaps/` and is the default
`--hdri`. Drop other `*.exr` files into `envmaps/` and reference them by
filename.

## Invocation

```bash
$BLENDER -b --python scripts/render_diffuse.py -- --obj <id-or-path> --out_dir <dir>
```

`scripts/exr_to_png.py` and `scripts/convert_mesh.py` need either Blender (for
convert_mesh) or pact env's python (for exr_to_png; needs `OpenEXR`).

```bash
PYBIN=/gs/fs/tga-koike-shanda4/yurh/miniconda3/envs/pact/bin/python
$PYBIN scripts/exr_to_png.py --exr_dir <out_dir>          # multilayer mode
$PYBIN scripts/exr_to_png.py --exr_file foo.exr           # single linear EXR -> foo.png
```

`--obj` accepts:
- a KaiNinja v2 obj-id (resolves to `/gs/bs/tga-koike-shanda/yurh/KaiNinja_v2/preprocess/<id>/`),
- or an absolute mesh path of any supported format.

## Scripts

### render_diffuse.py

```
--obj           required, KaiNinja obj-id or path to obj/ply/glb/gltf/stl/fbx
--out_dir       required
--views         default 4
--samples       default 64; 128-256 for hero renders
--res           default 1024
--hdri          envmaps/ filename or absolute path (default studio.exr)
--hdri_strength default 1.0
--distance      camera distance × scene diag (default 2.5)
--elevation     deg above horizon (default 25.0)
--color         RGB linear, default 0.8 0.8 0.8
--roughness     Principled BSDF, default 0.5
--metallic      Principled BSDF, default 0.0
--two_sided     swap Principled for two-sided diffuse
--keep_materials preserve materials embedded in the file (OBJ+MTL, GLB, FBX).
                 Disables --color/--roughness/--metallic/--two_sided
--output_format png|exr (default png)
--source_frame  auto|y_up|z_up (default auto)
--normalize     none|unit_cube|unit_sphere (default none)
```

### render_parts.py

```
--obj, --out_dir              required
--face_ids                     face_ids.npy; auto-resolved for KaiNinja obj-id
--views, --samples, --res,
--hdri, --hdri_strength,
--distance, --elevation        same as render_diffuse
--output_format png|exr        default png
--source_frame                 default auto
```

### render_pbr.py

Reads a folder of texture maps (Poly Haven / ambientCG naming) and builds a
Principled BSDF with each slot wired up.

```
--obj, --out_dir, --pbr_dir   required
--uv_scale U V                default 1.0 1.0
--normal_strength             default 1.0
--displacement_scale          default 0 (bump-only); >0 enables displacement
--auto_unwrap                 smart-project if mesh has no UVs
--views/--samples/--res/--hdri/--hdri_strength/--distance/--elevation
                              same as render_diffuse
--output_format png|exr       default png
--source_frame                default auto
```

Quick fetch a CC0 pack:
```bash
bash scripts/fetch_polyhaven_pbr.sh <slug> <dest_dir> [1k|2k|4k]
```

### render_uv.py

Three artifacts per view + one global 2D layout:

```
v{vi}_uvcolor.png    UV emission painted onto the surface (R=U, G=V)
v{vi}_checker.png    procedural checker via UV mapping (stretch viz)
uv_layout.png        2D UV islands from matplotlib
```

```
--obj, --out_dir              required
--views, --samples, --res     defaults 4, 32, 1024
--hdri, --hdri_strength       lights the checker pass
--distance, --elevation       orbit cam
--checker_scale               default 10.0
--auto_unwrap                 smart-project if no UV layer
--source_frame                default auto
```

### render_depth_normal.py

Writes `<out_dir>/v{vi}/0001.exr` per view (multilayer, slots = `rgb`,
`depth`, `normal`).

```
--obj, --out_dir, --views, --samples, --res, --distance, --elevation
--hdri, --hdri_strength        HDRI lights the RGB pass; depth/normal unaffected
--source_frame                 default auto
```

Decode with `exr_to_png.py --exr_dir <out_dir>`.

### convert_mesh.py

```
blender -b --python scripts/convert_mesh.py -- \
        --in input.obj --out output.glb \
        [--source_frame auto|y_up|z_up] [--target_frame auto|y_up|z_up]
```

### exr_to_png.py

```
--exr_dir <dir>     multilayer mode (depth+normal pipeline output)
--exr_file <path>   single linear EXR -> linear_to_srgb -> PNG next to it
--exposure <EV>     stops applied before sRGB encode (default 0)
```

## Output format details

- **png:** scene's view_transform = `Standard`, 8-bit RGBA. Blender applies
  linear→sRGB internally. Open directly in any viewer.
- **exr:** scene's view_transform = `Raw`, 32-bit RGB single-layer EXR. No
  tone mapping. Decode via `exr_to_png.py --exr_file` to get a sRGB PNG.

The multilayer EXR (depth+normal pipeline) is always view_transform=`Raw` so
geometry passes stay in their canonical numeric ranges.

## Conventions reference (sample code)

`postproc.linear_to_srgb` matches what Blender's Standard view transform does:

```python
def linear_to_srgb(img):
    limit = 0.0031308
    out = np.where(img > limit,
                    1.055 * np.power(np.clip(img, 0, None), 1/2.4) - 0.055,
                    12.92 * img)
    return np.clip(out, 0.0, 1.0)
```

A torch version is in `postproc.linear_to_srgb_torch`.

## Quick smoke test

```bash
cd /gs/fs/tga-koike-shanda4/yurh/blender_kit
bash examples/smoke.sh
```

Renders one KaiNinja obj through all three pipelines into `/tmp/blender_kit_smoke/`.

## Adding new HDRIs

Drop any `*.exr` into `envmaps/` (or symlink). `lib.world.list_envmaps()`
discovers them at runtime.

## Adding new entry points

Scripts live in `scripts/`, follow the pattern in `render_diffuse.py`:

```python
import os, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path, configure_output_format
from lib import ...

argv = parse_blender_argv()  # strips everything before '--' in sys.argv
```

Reusable helpers belong in `lib/`, not in the script. Keep entry points thin.
