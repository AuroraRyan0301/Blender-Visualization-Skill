"""Part-coloring render — tab20 per part_id, two-sided diffuse. GPU-only.

face_ids.npy must be index-aligned to the OBJ file's face order. For non-OBJ
inputs, --face_ids must align to the triangulated face order returned by the
bpy importer.

Usage:
  blender -b --python render_parts.py -- --obj <id-or-path> --out_dir <dir> \
          [--face_ids path] [--views 4] [--samples 64] [--res 1024] \
          [--hdri studio.exr] [--output_format png|exr]
"""
import os
import sys
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path, configure_output_format
from lib import normalize as norm_mod, materials, camera, world
from lib import render_setup, scene, mesh_io


def main():
    argv = parse_blender_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--face_ids',
                    help='face_ids.npy path; auto-resolved for KaiNinja obj-id')
    ap.add_argument('--views', type=int, default=4)
    ap.add_argument('--samples', type=int, default=64)
    ap.add_argument('--res', type=int, default=1024)
    ap.add_argument('--hdri', default='studio.exr')
    ap.add_argument('--hdri_strength', type=float, default=1.0)
    ap.add_argument('--distance', type=float, default=2.5)
    ap.add_argument('--elevation', type=float, default=25.0)
    ap.add_argument('--output_format', choices=['png', 'exr'], default='png')
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')
    args = ap.parse_args(argv)

    mesh_path, fids_default = resolve_obj_path(args.obj)
    fids_path = args.face_ids or fids_default
    if fids_path is None or not os.path.isfile(fids_path):
        raise FileNotFoundError(
            f'face_ids.npy not found (pass --face_ids for bare paths): {fids_path}')
    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    fids = np.load(fids_path).astype(np.int64)
    assert fids.shape[0] == F.shape[0], \
        f'face_ids length {fids.shape[0]} != face count {F.shape[0]}'
    import bpy
    scene.clear_scene()

    center = norm_mod.scene_center(V)
    diag = norm_mod.scene_diag(V)

    hdri = args.hdri
    if not os.path.isabs(hdri):
        hdri = os.path.join(world.ENVMAP_DIR, hdri)

    os.makedirs(args.out_dir, exist_ok=True)
    ext = 'png' if args.output_format == 'png' else 'exr'
    for vi in range(args.views):
        scene.clear_scene()
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        render_setup.enable_aux_passes(z=False, normal=False)
        camera.add_orbit_camera(vi, args.views, center, diag,
                                 distance_factor=args.distance,
                                 elevation_deg=args.elevation)
        for ki, (pid, Vp, Fp) in enumerate(scene.split_by_part_id(V, F, fids)):
            mat = materials.tab20_flat(f'mat_p{pid}', ki, two_sided=True)
            scene.add_mesh_from_arrays(f'p{pid}', Vp, Fp, mat=mat, smooth=False)

        out_path = os.path.join(args.out_dir, f'v{vi:02d}.{ext}')
        bpy.context.scene.use_nodes = False
        configure_output_format(bpy.context.scene, args.output_format)
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f'[parts] wrote {out_path}')


if __name__ == '__main__':
    main()
