"""Render with a Poly Haven / ambientCG style PBR texture pack folder."""
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
    ap.add_argument('--pbr_dir', required=True)
    ap.add_argument('--uv_scale', type=float, nargs=2, default=[1.0, 1.0])
    ap.add_argument('--normal_strength', type=float, default=1.0)
    ap.add_argument('--displacement_scale', type=float, default=0.0)
    ap.add_argument('--auto_unwrap', action='store_true')
    args = ap.parse_args(parse_blender_argv())

    mesh_path, _ = resolve_obj_path(args.obj)
    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    import bpy
    scene.clear_scene()
    center = normalize.scene_center(V)
    diag = normalize.scene_diag(V)
    hdri = args.hdri if os.path.isabs(args.hdri) \
        else os.path.join(world.ENVMAP_DIR, args.hdri)

    def build_scene(fi):
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        bpy.context.scene.use_nodes = False
        mat, detected = materials.load_pbr_pack(
            'pbr', args.pbr_dir,
            uv_scale=tuple(args.uv_scale),
            normal_strength=args.normal_strength,
            displacement_scale=args.displacement_scale)
        if fi == 0:
            print(f'[render_pbr] detected: {list(detected)}')
        obj = scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=True)
        if args.auto_unwrap:
            from lib import uv as uv_mod
            uv_mod.ensure_uvs(obj)

    def configure_output(frame_path):
        cli.configure_output_format(bpy.context.scene, args.output_format)

    ext = 'png' if args.output_format == 'png' else 'exr'
    mp4_out = os.path.join(args.out_dir, 'video.mp4') if args.mp4 else None
    render_frames(cli.build_trajectory(args), center, diag,
                   out_dir=args.out_dir, build_scene=build_scene,
                   configure_output=configure_output,
                   extension=ext, mp4_out=mp4_out, fps=args.fps)


if __name__ == '__main__':
    main()
