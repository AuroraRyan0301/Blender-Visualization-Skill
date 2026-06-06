"""UV visualization: surface coloring + 2D layout export.

Three artifacts per view:
  v{vi}_uvcolor.png   UV painted onto the mesh surface as emission (U,V,0)
  v{vi}_checker.png   procedural checker via UV mapping (stretch viz)

One global artifact:
  uv_layout.png       2D UV islands drawn via matplotlib

If the mesh has no UV layer and --auto_unwrap is set, smart-project is run.

Usage:
  blender -b --python render_uv.py -- --obj input.obj --out_dir out \
          [--views 4] [--samples 32] [--checker_scale 10] [--auto_unwrap]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path, configure_output_format
from lib import normalize as norm_mod, materials, camera, world
from lib import render_setup, scene, mesh_io, uv as uv_mod


def main():
    argv = parse_blender_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--views', type=int, default=4)
    ap.add_argument('--samples', type=int, default=32)
    ap.add_argument('--res', type=int, default=1024)
    ap.add_argument('--hdri', default='studio.exr')
    ap.add_argument('--hdri_strength', type=float, default=1.0)
    ap.add_argument('--distance', type=float, default=2.5)
    ap.add_argument('--elevation', type=float, default=25.0)
    ap.add_argument('--checker_scale', type=float, default=10.0)
    ap.add_argument('--auto_unwrap', action='store_true',
                    help='smart-project if the mesh has no UV layer')
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')
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

    # 1) UV-as-color emission render (env-independent — emission)
    for vi in range(args.views):
        scene.clear_scene()
        world.set_world_black()
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        camera.add_orbit_camera(vi, args.views, center, diag,
                                 distance_factor=args.distance,
                                 elevation_deg=args.elevation)
        mat = materials.uv_color_emission('mat_uv')
        obj = scene.add_mesh_from_arrays('uv_obj', V, F, mat=mat, smooth=False)
        if not uv_mod.has_uvs(obj):
            if args.auto_unwrap:
                uv_mod.smart_unwrap(obj)
            else:
                print('[render_uv] WARNING: mesh has no UV layer. '
                      'Pass --auto_unwrap to smart-project.')
        out_path = os.path.join(args.out_dir, f'v{vi:02d}_uvcolor.png')
        bpy.context.scene.use_nodes = False
        configure_output_format(bpy.context.scene, 'png')
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f'[render_uv] wrote {out_path}')

    # 2) Procedural checker (HDRI-lit, shows stretching)
    for vi in range(args.views):
        scene.clear_scene()
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        camera.add_orbit_camera(vi, args.views, center, diag,
                                 distance_factor=args.distance,
                                 elevation_deg=args.elevation)
        mat = materials.uv_checker('mat_checker', scale=args.checker_scale)
        obj = scene.add_mesh_from_arrays('chk_obj', V, F, mat=mat, smooth=False)
        if not uv_mod.has_uvs(obj):
            if args.auto_unwrap:
                uv_mod.smart_unwrap(obj)
        out_path = os.path.join(args.out_dir, f'v{vi:02d}_checker.png')
        bpy.context.scene.use_nodes = False
        configure_output_format(bpy.context.scene, 'png')
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f'[render_uv] wrote {out_path}')

    # 3) 2D UV layout (matplotlib, headless-safe)
    scene.clear_scene()
    obj = scene.add_mesh_from_arrays('layout', V, F)
    if not uv_mod.has_uvs(obj) and args.auto_unwrap:
        uv_mod.smart_unwrap(obj)
    layout_path = os.path.join(args.out_dir, 'uv_layout.png')
    written = uv_mod.export_uv_layout_png(obj, layout_path, size=1024)
    if written:
        print(f'[render_uv] wrote {written}')
    else:
        print('[render_uv] no UV layer -> skipped uv_layout.png')


if __name__ == '__main__':
    main()
