"""Render with a PBR texture pack folder (Poly Haven / ambientCG style).

Detects the standard PBR map naming convention:
  base_color   *diff*, *color*, *basecolor*, *albedo*       sRGB
  roughness    *rough*, *roughness*                          Non-Color
  normal       *nor_gl*, *normal_gl*, *normal*               Non-Color (GL)
  metallic     *metal*, *metalness*                          Non-Color
  ao           *ao*, *ambientocclusion*                      Non-Color
  displacement *disp*, *displacement*, *height*              Non-Color

Free CC0 packs: https://polyhaven.com/textures , https://ambientcg.com/

Usage:
  blender -b --python render_pbr.py -- --obj input.glb --pbr_dir wood_pack/ \
          --out_dir out [--uv_scale 1 1] [--normal_strength 1.0] \
          [--displacement_scale 0.05]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path, configure_output_format
from lib import normalize as norm_mod, materials, camera, world
from lib import render_setup, scene, mesh_io


def main():
    argv = parse_blender_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument('--obj', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--pbr_dir', required=True,
                    help='folder containing the PBR map files')
    ap.add_argument('--uv_scale', type=float, nargs=2, default=[1.0, 1.0])
    ap.add_argument('--normal_strength', type=float, default=1.0)
    ap.add_argument('--displacement_scale', type=float, default=0.0,
                    help='set >0 to wire the displacement map (bump-only by default)')
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
    ap.add_argument('--auto_unwrap', action='store_true',
                    help='smart-project unwrap if the mesh has no UVs')
    args = ap.parse_args(argv)

    mesh_path, _ = resolve_obj_path(args.obj)
    import bpy
    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
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
        mat, detected = materials.load_pbr_pack(
            'pbr', args.pbr_dir,
            uv_scale=tuple(args.uv_scale),
            normal_strength=args.normal_strength,
            displacement_scale=args.displacement_scale)
        if vi == 0:
            print(f'[render_pbr] detected maps: {list(detected.keys())}')
        obj = scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=True)
        if args.auto_unwrap:
            from lib import uv as uv_mod
            uv_mod.ensure_uvs(obj)
        camera.add_orbit_camera(vi, args.views, center, diag,
                                 distance_factor=args.distance,
                                 elevation_deg=args.elevation)
        out_path = os.path.join(args.out_dir, f'v{vi:02d}.{ext}')
        bpy.context.scene.use_nodes = False
        configure_output_format(bpy.context.scene, args.output_format)
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f'[render_pbr] wrote {out_path}')


if __name__ == '__main__':
    main()
