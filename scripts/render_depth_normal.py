"""Depth + normal pass render via OPEN_EXR_MULTILAYER. GPU-only.

Writes <out_dir>/f{NNNN}/0001.exr per frame. Decode via exr_to_png.py --exr_dir.
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import (cli, compositor, materials, mesh_io, normalize, render_setup,
                  scene, world)
from lib.render_pipeline import render_frames


def main():
    ap = argparse.ArgumentParser()
    cli.add_io_args(ap)
    ap.add_argument('--samples', type=int, default=32)
    ap.add_argument('--res', type=int, default=1024)
    cli.add_world_args(ap)
    cli.add_camera_args(ap)
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
        render_setup.enable_aux_passes(z=True, normal=True)
        mat = materials.diffuse_realistic('mat', (0.8, 0.8, 0.8, 1.0))
        scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=False)

    def configure_output(frame_dir):
        compositor.setup_multilayer_exr(frame_dir,
                                          slots=('rgb', 'depth', 'normal'))
        bpy.context.scene.view_settings.view_transform = 'Raw'

    render_frames(cli.build_trajectory(args), center, diag,
                   out_dir=args.out_dir, build_scene=build_scene,
                   configure_output=configure_output,
                   use_multilayer_dirs=True)


if __name__ == '__main__':
    main()
