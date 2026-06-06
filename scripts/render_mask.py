"""Render binary masks: whole-object silhouette + per-part masks. GPU-only.

Writes <out_dir>/v{vi}/0001.exr per view (OPEN_EXR_MULTILAYER):
  layer 'alpha'    silhouette (float 0..1) — set with film_transparent.
  layer 'indexob'  per-part Object Index (float ~= part_id + 1; 0 = background).

Decode to PNGs with `python scripts/exr_to_png.py --mask_dir <out_dir>`.

If --face_ids is not provided (or no KaiNinja face_ids resolved), only the
whole-object alpha is meaningful — indexob will be 1 everywhere on the mesh.

Usage:
  blender -b --python render_mask.py -- --obj <id-or-path> --out_dir <dir> \
          [--face_ids ...] [--views 4] [--samples 8] [--res 1024]
"""
import os
import sys
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import normalize as norm_mod, materials, camera, world
from lib import render_setup, scene, compositor, mesh_io


def main():
    argv = parse_blender_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--face_ids',
                    help='face_ids.npy; auto-resolved for KaiNinja obj-id')
    ap.add_argument('--views', type=int, default=4)
    ap.add_argument('--samples', type=int, default=1,
                    help='pixel-perfect masks: default 1 with BOX filter')
    ap.add_argument('--res', type=int, default=1024)
    ap.add_argument('--distance', type=float, default=2.5)
    ap.add_argument('--elevation', type=float, default=25.0)
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')
    args = ap.parse_args(argv)

    mesh_path, fids_default = resolve_obj_path(args.obj)
    fids_path = args.face_ids or fids_default
    fids = None
    if fids_path and os.path.isfile(fids_path):
        fids = np.load(fids_path).astype(np.int64)

    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    if fids is not None and fids.shape[0] != F.shape[0]:
        raise AssertionError(
            f'face_ids length {fids.shape[0]} != face count {F.shape[0]}')
    import bpy
    scene.clear_scene()
    center = norm_mod.scene_center(V)
    diag = norm_mod.scene_diag(V)

    os.makedirs(args.out_dir, exist_ok=True)
    for vi in range(args.views):
        scene.clear_scene()
        world.set_world_black()
        render_setup.setup_cycles(samples=args.samples, resolution=args.res,
                                    denoise=False)
        render_setup.enable_aux_passes(z=False, normal=False, indexob=True)
        # Pixel-perfect masks: BOX filter width 0 -> no subpixel mixing of
        # indexob between adjacent parts. samples can stay at 1 for crisp
        # binary edges; bump higher only if silhouette anti-aliasing matters.
        bpy.context.scene.cycles.pixel_filter_type = 'BOX'
        bpy.context.scene.cycles.filter_width = 0.01
        bpy.context.scene.render.film_transparent = True
        camera.add_orbit_camera(vi, args.views, center, diag,
                                 distance_factor=args.distance,
                                 elevation_deg=args.elevation)
        mat = materials.diffuse_realistic('mat', (0.8, 0.8, 0.8, 1.0))

        if fids is None:
            obj = scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=False)
            obj.pass_index = 1
        else:
            for pid, Vp, Fp in scene.split_by_part_id(V, F, fids):
                # pass_index 0 is reserved for background, so shift by +1
                obj = scene.add_mesh_from_arrays(f'p{pid}', Vp, Fp, mat=mat,
                                                  smooth=False)
                obj.pass_index = pid + 1

        view_dir = os.path.join(args.out_dir, f'v{vi:02d}')
        compositor.setup_mask_multilayer(view_dir, with_indexob=True)
        bpy.context.scene.view_settings.view_transform = 'Raw'
        bpy.context.scene.render.filepath = os.path.join(args.out_dir,
                                                          f'_dummy_v{vi:02d}.png')
        bpy.ops.render.render(write_still=True)
        print(f'[mask] wrote {view_dir}/0001.exr')


if __name__ == '__main__':
    main()
