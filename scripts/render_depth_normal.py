"""Depth + normal pass render via OPEN_EXR_MULTILAYER. GPU-only.

Writes <out_dir>/v{vi}/0001.exr per view (slots: rgb, depth, normal).
Decode with exr_to_png.py.

Usage:
  blender -b --python render_depth_normal.py -- --obj <id-or-path> \
          --out_dir <dir> [--views 4] [--samples 32] [--res 1024]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import normalize as norm_mod, materials, camera, world
from lib import render_setup, scene, compositor, mesh_io


def main():
    argv = parse_blender_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--views', type=int, default=4)
    ap.add_argument('--samples', type=int, default=32)
    ap.add_argument('--res', type=int, default=1024)
    ap.add_argument('--distance', type=float, default=2.5)
    ap.add_argument('--elevation', type=float, default=25.0)
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')
    ap.add_argument('--hdri', default='studio.exr',
                    help='HDRI for the RGB pass (depth/normal unaffected)')
    ap.add_argument('--hdri_strength', type=float, default=1.0)
    args = ap.parse_args(argv)

    mesh_path, _ = resolve_obj_path(args.obj)
    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    import bpy
    scene.clear_scene()
    center = norm_mod.scene_center(V)
    diag = norm_mod.scene_diag(V)

    hdri = args.hdri
    if not os.path.isabs(hdri):
        hdri = os.path.join(world.ENVMAP_DIR, hdri)

    os.makedirs(args.out_dir, exist_ok=True)
    for vi in range(args.views):
        scene.clear_scene()
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        render_setup.enable_aux_passes(z=True, normal=True)
        camera.add_orbit_camera(vi, args.views, center, diag,
                                 distance_factor=args.distance,
                                 elevation_deg=args.elevation)
        mat = materials.diffuse_realistic('mat', (0.8, 0.8, 0.8, 1.0))
        scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=False)

        view_dir = os.path.join(args.out_dir, f'v{vi:02d}')
        compositor.setup_multilayer_exr(view_dir,
                                         slots=('rgb', 'depth', 'normal'))
        bpy.context.scene.view_settings.view_transform = 'Raw'
        bpy.context.scene.render.filepath = os.path.join(args.out_dir,
                                                          f'_dummy_v{vi:02d}.png')
        bpy.ops.render.render(write_still=True)
        print(f'[depth_normal] wrote {view_dir}/0001.exr')


if __name__ == '__main__':
    main()
