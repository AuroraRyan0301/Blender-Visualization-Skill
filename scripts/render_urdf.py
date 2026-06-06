"""Render a URDF robot at rest pose. GPU-only.

URDF (Universal Robot Description Format) is the ROS / robotics standard.
This script loads the kinematic tree, places every link's visual mesh at its
world transform (joints at zero), and renders frames along the chosen camera
trajectory. URDF-specified <material><color> values are honored.

Mesh files referenced from URDFs are assumed to be in their link's local
Z-up frame, so OBJ files are NOT rotated to Blender's Z-up (URDF already
defines them in the right frame).

Usage:
  blender -b --python render_urdf.py -- \
        --urdf robot.urdf --out_dir out --trajectory circle --frames 60 --mp4
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv
from lib import cli, render_setup, scene, urdf, world
from lib.render_pipeline import render_frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--urdf', required=True)
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--mesh_root',
                    help='base dir for package:// path resolution '
                         '(defaults to dir of the URDF file)')
    cli.add_render_args(ap)
    cli.add_world_args(ap)
    cli.add_camera_args(ap)
    cli.add_video_args(ap)
    args = ap.parse_args(parse_blender_argv())

    import bpy
    # Probe import once to compute scene bbox.
    scene.clear_scene()
    objs = urdf.load_into_blender(args.urdf, mesh_root=args.mesh_root)
    if not objs:
        sys.exit('[render_urdf] URDF produced no visual geometry')
    center, diag = scene.world_aabb(objs)
    print(f'[render_urdf] loaded {len(objs)} visual meshes, '
          f'diag={diag:.3f}m center={tuple(round(c,3) for c in center)}')

    hdri = args.hdri if os.path.isabs(args.hdri) \
        else os.path.join(world.ENVMAP_DIR, args.hdri)

    def build_scene(fi):
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        bpy.context.scene.use_nodes = False
        urdf.load_into_blender(args.urdf, mesh_root=args.mesh_root)

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
