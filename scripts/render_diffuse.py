"""Realistic Cycles render under HDRI lighting. GPU-only.

Reads any supported mesh format (obj/ply/glb/stl/fbx/off) with correct per-format
axis handling. Writes PNG (sRGB, Standard view transform) by default; pass
--output_format exr for scene-linear EXR and decode via exr_to_png.py.

Usage:
  blender -b --python render_diffuse.py -- --obj <id-or-path> --out_dir <dir> \
          [--views 4] [--samples 64] [--res 1024] [--hdri studio.exr] \
          [--distance 2.5] [--color 0.8 0.8 0.8] [--output_format png|exr]
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
    ap.add_argument('--views', type=int, default=4)
    ap.add_argument('--samples', type=int, default=64)
    ap.add_argument('--res', type=int, default=1024)
    ap.add_argument('--hdri', default='studio.exr',
                    help='filename in envmaps/ or absolute path')
    ap.add_argument('--hdri_strength', type=float, default=1.0)
    ap.add_argument('--distance', type=float, default=2.5)
    ap.add_argument('--elevation', type=float, default=25.0)
    ap.add_argument('--color', type=float, nargs=3, default=[0.8, 0.8, 0.8])
    ap.add_argument('--roughness', type=float, default=0.5)
    ap.add_argument('--metallic', type=float, default=0.0)
    ap.add_argument('--two_sided', action='store_true')
    ap.add_argument('--output_format', choices=['png', 'exr'], default='png')
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto',
                    help='override per-format default coord frame')
    ap.add_argument('--normalize', choices=['none', 'unit_cube', 'unit_sphere'],
                    default='none')
    args = ap.parse_args(argv)

    mesh_path, _ = resolve_obj_path(args.obj)
    import bpy
    # Use bpy importer for non-OBJ; manual parser for OBJ (preserves order)
    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    # Clean up anything bpy imported when loading non-OBJ
    scene.clear_scene()

    if args.normalize != 'none':
        V, _ = norm_mod.normalize_verts(V, mode=args.normalize)
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
        if args.two_sided:
            mat = materials.two_sided_diffuse('mat', (*args.color, 1.0))
        else:
            mat = materials.diffuse_realistic('mat', (*args.color, 1.0),
                                               roughness=args.roughness,
                                               metallic=args.metallic)
        scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=True)

        out_path = os.path.join(args.out_dir, f'v{vi:02d}.{ext}')
        bpy.context.scene.use_nodes = False
        configure_output_format(bpy.context.scene, args.output_format)
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f'[diffuse] wrote {out_path}')


if __name__ == '__main__':
    main()
