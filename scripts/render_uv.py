"""UV visualization: UV-as-color emission + UV checker + 2D layout PNG."""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import (cli, materials, mesh_io, normalize, render_setup,
                  scene, world, uv as uv_mod)
from lib.render_pipeline import render_frames


def main():
    ap = argparse.ArgumentParser()
    cli.add_io_args(ap)
    cli.add_render_args(ap)
    cli.add_world_args(ap)
    cli.add_camera_args(ap)
    cli.add_video_args(ap)
    ap.add_argument('--checker_scale', type=float, default=10.0)
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

    def configure_output(frame_path):
        cli.configure_output_format(bpy.context.scene, 'png')

    def make_build(mode):
        def build(fi):
            render_setup.setup_cycles(samples=args.samples, resolution=args.res)
            bpy.context.scene.use_nodes = False
            if mode == 'uvcolor':
                world.set_world_black()
                mat = materials.uv_color_emission('mat_uv')
            else:  # 'checker'
                world.set_world_hdri(hdri, strength=args.hdri_strength)
                mat = materials.uv_checker('mat_chk', scale=args.checker_scale)
            obj = scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=False)
            if not uv_mod.has_uvs(obj) and args.auto_unwrap:
                uv_mod.smart_unwrap(obj)
        return build

    traj = cli.build_trajectory(args)

    uvcolor_dir = os.path.join(args.out_dir, 'uvcolor')
    checker_dir = os.path.join(args.out_dir, 'checker')

    render_frames(traj, center, diag, out_dir=uvcolor_dir,
                   build_scene=make_build('uvcolor'),
                   configure_output=configure_output,
                   extension='png',
                   mp4_out=(os.path.join(uvcolor_dir, 'video.mp4') if args.mp4 else None),
                   fps=args.fps)
    render_frames(traj, center, diag, out_dir=checker_dir,
                   build_scene=make_build('checker'),
                   configure_output=configure_output,
                   extension='png',
                   mp4_out=(os.path.join(checker_dir, 'video.mp4') if args.mp4 else None),
                   fps=args.fps)

    # 2D UV layout (one PNG, mesh-pose-independent)
    scene.clear_scene()
    obj = scene.add_mesh_from_arrays('layout', V, F)
    if not uv_mod.has_uvs(obj) and args.auto_unwrap:
        uv_mod.smart_unwrap(obj)
    written = uv_mod.export_uv_layout_png(
        obj, os.path.join(args.out_dir, 'uv_layout.png'), size=1024)
    if written:
        print(f'[uv] -> {written}')


if __name__ == '__main__':
    main()
