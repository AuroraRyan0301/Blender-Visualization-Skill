"""Binary masks: silhouette + per-part. GPU-only.

Writes <out_dir>/f{NNNN}/0001.exr per frame (OPEN_EXR_MULTILAYER):
  alpha:    silhouette (float 0..1)
  indexob:  per-part Object Index (float ≈ part_id + 1; 0 = background)

Decode via `python exr_to_png.py --mask_dir <out_dir>`.
"""
import os
import sys
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import (cli, compositor, materials, mesh_io, normalize, render_setup,
                  scene, world)
from lib.render_pipeline import render_frames


def main():
    ap = argparse.ArgumentParser()
    cli.add_io_args(ap)
    ap.add_argument('--samples', type=int, default=1,
                    help='pixel-perfect masks: default 1 with BOX filter')
    ap.add_argument('--res', type=int, default=1024)
    cli.add_camera_args(ap)
    ap.add_argument('--face_ids',
                    help='face_ids.npy; auto-resolved for KaiNinja obj-id')
    args = ap.parse_args(parse_blender_argv())

    mesh_path, fids_default = resolve_obj_path(args.obj)
    fids_path = args.face_ids or fids_default
    fids = None
    if fids_path and os.path.isfile(fids_path):
        fids = np.load(fids_path).astype(np.int64)

    V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=args.source_frame)
    if fids is not None and fids.shape[0] != F.shape[0]:
        raise AssertionError(f'face_ids {fids.shape[0]} != F {F.shape[0]}')
    import bpy
    scene.clear_scene()
    center = normalize.scene_center(V)
    diag = normalize.scene_diag(V)

    def build_scene(fi):
        world.set_world_black()
        render_setup.setup_cycles(samples=args.samples, resolution=args.res,
                                    denoise=False)
        render_setup.enable_aux_passes(z=False, normal=False, indexob=True)
        bpy.context.scene.cycles.pixel_filter_type = 'BOX'
        bpy.context.scene.cycles.filter_width = 0.01
        bpy.context.scene.render.film_transparent = True
        mat = materials.diffuse_realistic('mat', (0.8, 0.8, 0.8, 1.0))
        if fids is None:
            obj = scene.add_mesh_from_arrays('obj', V, F, mat=mat, smooth=False)
            obj.pass_index = 1
        else:
            for pid, Vp, Fp in scene.split_by_part_id(V, F, fids):
                obj = scene.add_mesh_from_arrays(f'p{pid}', Vp, Fp, mat=mat,
                                                  smooth=False)
                obj.pass_index = pid + 1

    def configure_output(frame_dir):
        compositor.setup_mask_multilayer(frame_dir, with_indexob=True)
        bpy.context.scene.view_settings.view_transform = 'Raw'

    render_frames(cli.build_trajectory(args), center, diag,
                   out_dir=args.out_dir, build_scene=build_scene,
                   configure_output=configure_output,
                   use_multilayer_dirs=True)


if __name__ == '__main__':
    main()
