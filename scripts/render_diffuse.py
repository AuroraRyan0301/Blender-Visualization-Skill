"""Realistic Cycles render under HDRI lighting. GPU-only.

Reads any supported mesh format (obj/ply/glb/gltf/stl/fbx). PNG (sRGB) or
scene-linear EXR. Optional --keep_materials to honor OBJ+MTL / GLB embedded
textures / FBX. Optional --mp4 to stitch frames.

Usage:
  blender -b --python render_diffuse.py -- \
        --obj input.glb --out_dir out --trajectory circle --frames 60 --mp4
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import cli, materials, mesh_io, normalize, render_setup, scene, world
from lib.render_pipeline import render_frames


def main():
    ap = argparse.ArgumentParser()
    cli.add_io_args(ap)
    cli.add_render_args(ap)
    cli.add_world_args(ap)
    cli.add_camera_args(ap)
    cli.add_video_args(ap)
    ap.add_argument('--color', type=float, nargs=3, default=[0.8, 0.8, 0.8])
    ap.add_argument('--roughness', type=float, default=0.5)
    ap.add_argument('--metallic', type=float, default=0.0)
    ap.add_argument('--two_sided', action='store_true')
    ap.add_argument('--keep_materials', action='store_true',
                    help='preserve file-embedded materials (OBJ+MTL, GLB, FBX)')
    ap.add_argument('--normalize', choices=['none', 'unit_cube', 'unit_sphere'],
                    default='none')
    args = ap.parse_args(parse_blender_argv())

    mesh_path, _ = resolve_obj_path(args.obj)
    import bpy

    if args.keep_materials:
        # Camera bbox is computed inside the loop after each re-import.
        center, diag = None, None
    else:
        V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
        scene.clear_scene()
        if args.normalize != 'none':
            V, _ = normalize.normalize_verts(V, mode=args.normalize)
        center = normalize.scene_center(V)
        diag = normalize.scene_diag(V)

    hdri = args.hdri if os.path.isabs(args.hdri) \
        else os.path.join(world.ENVMAP_DIR, args.hdri)

    nonlocal_state = {'center': center, 'diag': diag}

    def build_scene(fi):
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        render_setup.enable_aux_passes(z=False, normal=False)
        bpy.context.scene.use_nodes = False
        if args.keep_materials:
            objs = scene.import_with_materials(mesh_path)
            nonlocal_state['center'], nonlocal_state['diag'] = scene.world_aabb(objs)
        else:
            if args.two_sided:
                mat = materials.two_sided_diffuse('mat', (*args.color, 1.0))
            else:
                mat = materials.diffuse_realistic(
                    'mat', (*args.color, 1.0),
                    roughness=args.roughness, metallic=args.metallic)
            scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=True)

    def configure_output(frame_path):
        cli.configure_output_format(bpy.context.scene, args.output_format)

    trajectory = cli.build_trajectory(args)

    if args.keep_materials:
        # Need scene center/diag from a probe import before driving the loop.
        scene.clear_scene()
        objs = scene.import_with_materials(mesh_path)
        nonlocal_state['center'], nonlocal_state['diag'] = scene.world_aabb(objs)

    ext = 'png' if args.output_format == 'png' else 'exr'
    mp4_out = os.path.join(args.out_dir, 'video.mp4') if args.mp4 else None
    render_frames(trajectory,
                   nonlocal_state['center'], nonlocal_state['diag'],
                   out_dir=args.out_dir,
                   build_scene=build_scene,
                   configure_output=configure_output,
                   extension=ext,
                   mp4_out=mp4_out, fps=args.fps)


if __name__ == '__main__':
    main()
