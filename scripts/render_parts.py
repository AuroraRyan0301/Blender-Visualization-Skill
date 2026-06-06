"""Part-coloring render — tab20 per part_id, two-sided diffuse. GPU-only."""
import os
import sys
import argparse
import numpy as np

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
    ap.add_argument('--face_ids',
                    help='face_ids.npy; auto-resolved for KaiNinja obj-id')
    args = ap.parse_args(parse_blender_argv())

    mesh_path, fids_default = resolve_obj_path(args.obj)
    fids_path = args.face_ids or fids_default
    if fids_path is None or not os.path.isfile(fids_path):
        raise FileNotFoundError(f'face_ids.npy required: {fids_path}')
    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    fids = np.load(fids_path).astype(np.int64)
    assert fids.shape[0] == F.shape[0], \
        f'face_ids {fids.shape[0]} != F {F.shape[0]}'
    import bpy
    scene.clear_scene()
    center = normalize.scene_center(V)
    diag = normalize.scene_diag(V)

    hdri = args.hdri if os.path.isabs(args.hdri) \
        else os.path.join(world.ENVMAP_DIR, args.hdri)

    def build_scene(fi):
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        render_setup.enable_aux_passes(z=False, normal=False)
        bpy.context.scene.use_nodes = False
        for ki, (pid, Vp, Fp) in enumerate(scene.split_by_part_id(V, F, fids)):
            mat = materials.tab20_flat(f'mat_p{pid}', ki, two_sided=True)
            scene.add_mesh_from_arrays(f'p{pid}', Vp, Fp, mat=mat, smooth=False)

    def configure_output(frame_path):
        cli.configure_output_format(bpy.context.scene, args.output_format)

    ext = 'png' if args.output_format == 'png' else 'exr'
    mp4_out = os.path.join(args.out_dir, 'video.mp4') if args.mp4 else None
    render_frames(cli.build_trajectory(args), center, diag,
                   out_dir=args.out_dir,
                   build_scene=build_scene,
                   configure_output=configure_output,
                   extension=ext, mp4_out=mp4_out, fps=args.fps)


if __name__ == '__main__':
    main()
