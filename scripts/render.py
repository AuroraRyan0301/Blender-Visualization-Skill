"""Unified render pipeline. GPU-only Cycles + GPU denoiser.

Four-stage composition:

  Scene      what to render
    --scene {mesh,parts,urdf}
      mesh:  --mesh PATH
      parts: --mesh PATH --face_ids PATH  [--select_parts all|i,j,...]
      urdf:  --urdf PATH [--mesh_root PATH]
    --normalize {whole,selected,none}
    --source_frame {auto,y_up,z_up}

  Material   how the surface looks
    --material {diffuse,two_sided,tab20,pbr,uv_color,uv_checker,embedded,mask}
    (mode-specific: --color, --roughness, --pbr_dir, --checker_scale, ...)

  Camera     where to look from
    --trajectory {static,circle,half_circle,hemisphere_jitter}
    --frames N + per-trajectory params

  Outputs    which passes get written
    --outputs <comma-list of rgb|depth|normal|mask>
    --out_dir DIR --res N --samples N
    --mp4 --fps   (rgb-only path)

Render strategy:
  outputs == {rgb}           Blender writes PNG directly (Standard transform).
  outputs ⊆ visual or mask   single Cycles render -> multilayer EXR per frame.
  visual + mask both         two Cycles renders per frame; visual.exr + mask.exr
                              live side by side. Mask uses BOX filter + samples=1
                              + film_transparent for crisp masks; visual uses the
                              full --samples for clean rgb.
"""
import copy
import json
import os
import shutil
import sys
import argparse
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import (cli, material_registry, materials, passes, render_setup,
                  scene as scene_mod, scene_assembly, world)
from lib.render_pipeline import render_frames


# ---------------------------------------------------------------------------
# CLI

def add_args(ap):
    s = ap.add_argument_group('scene')
    s.add_argument('--scene', choices=['mesh', 'parts', 'urdf',
                                          'voxels', 'arrows', 'attraction',
                                          'bboxes'],
                    help='required unless using --manifest')
    s.add_argument('--mesh', help='mesh path or KaiNinja obj-id (mesh/parts)')
    s.add_argument('--face_ids', help='[parts] face_ids.npy')
    s.add_argument('--urdf', help='[urdf] URDF file')
    s.add_argument('--mesh_root', help='[urdf] base for package:// resolution')
    s.add_argument('--npz', help='[voxels/arrows/attraction/bboxes] npz file')
    s.add_argument('--voxel_size', type=float, default=0.003,
                    help='[voxels] cube edge length in normalized units')
    s.add_argument('--grid_resolution', type=int, default=512,
                    help='[voxels/attraction] coord grid resolution')
    s.add_argument('--max_voxels', type=int, default=None,
                    help='[voxels] random subsample cap')
    s.add_argument('--max_arrows', type=int, default=300,
                    help='[arrows/attraction] arrow count cap')
    s.add_argument('--shaft_radius', type=float, default=0.005)
    s.add_argument('--head_radius', type=float, default=0.012)
    s.add_argument('--head_fraction', type=float, default=0.3)
    s.add_argument('--attr_slot', type=int, default=0,
                    help='[attraction] which of 3 slots (0/1/2), -1 = all 3')
    s.add_argument('--arrow_scale', type=float, default=0.05,
                    help='[attraction] multiplies |attr| -> arrow length')
    s.add_argument('--select_parts', default='all',
                    help='"all" or comma-separated part ids')
    s.add_argument('--normalize', choices=['whole', 'selected', 'none'],
                    default='whole')
    s.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')

    m = ap.add_argument_group('material')
    m.add_argument('--material', choices=material_registry.NAMES, default=None,
                    help='default: diffuse(mesh), tab20(parts), embedded(urdf). '
                         'file_embedded keeps OBJ+MTL / GLB textures / FBX '
                         'materials.')
    m.add_argument('--color', type=float, nargs=3, default=[0.8, 0.8, 0.8])
    m.add_argument('--roughness', type=float, default=0.5)
    m.add_argument('--metallic', type=float, default=0.0)
    m.add_argument('--pbr_dir', help='[pbr] folder with PBR maps')
    m.add_argument('--uv_scale', type=float, nargs=2, default=[1.0, 1.0])
    m.add_argument('--normal_strength', type=float, default=1.0)
    m.add_argument('--displacement_scale', type=float, default=0.0)
    m.add_argument('--checker_scale', type=float, default=10.0)
    m.add_argument('--auto_unwrap', action='store_true')

    cli.add_world_args(ap)
    cli.add_camera_args(ap)

    o = ap.add_argument_group('output')
    o.add_argument('--out_dir', help='required unless using --manifest')
    o.add_argument('--outputs', default='rgb',
                    help='comma-separated subset of {rgb,depth,normal,mask}')
    o.add_argument('--samples', type=int, default=64)
    o.add_argument('--res', type=int, default=1024)
    cli.add_video_args(ap)

    b = ap.add_argument_group('batch / multi-node')
    b.add_argument('--manifest',
                    help='JSONL file: one JSON object per line. Each line\'s '
                         'keys override the corresponding --flag for that job. '
                         'CLI flags become defaults shared by all jobs. '
                         'Single Blender process amortizes startup across all '
                         'jobs assigned to this rank.')
    b.add_argument('--rank', type=int, default=0,
                    help='shard index for multi-node / multi-GPU split '
                         '(default 0)')
    b.add_argument('--world', type=int, default=1,
                    help='total shard count (default 1); jobs[rank::world] is '
                         'this rank\'s slice')
    b.add_argument('--continue_on_error', action='store_true', default=True,
                    help='[batch] log + skip failed jobs instead of aborting '
                         '(default True)')


# ---------------------------------------------------------------------------
# Scene + material resolution

def resolve_scene(args):
    if args.scene == 'mesh':
        if not args.mesh:
            raise SystemExit('--scene mesh requires --mesh')
        path, _ = resolve_obj_path(args.mesh)
        return scene_assembly.Scene.from_mesh(
            path, normalize=args.normalize, source_frame=args.source_frame)
    if args.scene == 'parts':
        if not args.mesh:
            raise SystemExit('--scene parts requires --mesh')
        path, fids_default = resolve_obj_path(args.mesh)
        fids = args.face_ids or fids_default
        if not fids or not os.path.isfile(fids):
            raise SystemExit(f'--face_ids not found: {fids}')
        sel = None
        if args.select_parts and args.select_parts != 'all':
            sel = [int(x) for x in args.select_parts.split(',') if x.strip()]
        return scene_assembly.Scene.from_parts(
            path, fids, normalize=args.normalize,
            source_frame=args.source_frame, select_parts=sel)
    if args.scene == 'urdf':
        if not args.urdf:
            raise SystemExit('--scene urdf requires --urdf')
        return scene_assembly.Scene.from_urdf(
            args.urdf, mesh_root=args.mesh_root, normalize=args.normalize)
    sel = None
    if args.select_parts and args.select_parts != 'all':
        sel = [int(x) for x in args.select_parts.split(',') if x.strip()]
    if args.scene == 'voxels':
        if not args.npz:
            raise SystemExit('--scene voxels requires --npz')
        return scene_assembly.Scene.from_voxels(
            args.npz, voxel_size=args.voxel_size,
            grid_resolution=args.grid_resolution, max_voxels=args.max_voxels,
            normalize=args.normalize, select_parts=sel)
    if args.scene == 'arrows':
        if not args.npz:
            raise SystemExit('--scene arrows requires --npz')
        return scene_assembly.Scene.from_arrows(
            args.npz, max_arrows=args.max_arrows,
            shaft_radius=args.shaft_radius, head_radius=args.head_radius,
            head_fraction=args.head_fraction,
            normalize=args.normalize, select_parts=sel)
    if args.scene == 'attraction':
        if not args.npz:
            raise SystemExit('--scene attraction requires --npz')
        return scene_assembly.Scene.from_attraction(
            args.npz, grid_resolution=args.grid_resolution,
            attr_slot=args.attr_slot, arrow_scale=args.arrow_scale,
            max_arrows=args.max_arrows,
            normalize=args.normalize, select_parts=sel)
    if args.scene == 'bboxes':
        if not args.npz:
            raise SystemExit('--scene bboxes requires --npz')
        return scene_assembly.Scene.from_bboxes(
            args.npz, normalize=args.normalize)
    raise SystemExit(f'unknown scene: {args.scene}')


def default_material(scene_kind):
    return {'mesh': 'diffuse', 'parts': 'tab20', 'urdf': 'embedded',
            'voxels': 'tab20', 'arrows': 'tab20',
            'attraction': 'tab20', 'bboxes': 'tab20'}[scene_kind]


# ---------------------------------------------------------------------------
# Single Cycles-render builders. Each returns a (build_scene, configure_output)
# pair used by render_pipeline.

def make_visual_step(args, scene_obj, material_fn, visual_passes, hdri):
    """One Cycles invocation that produces rgb/depth/normal passes under HDRI."""
    import bpy

    def build_scene(fi):
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        vl = bpy.context.scene.view_layers[0]
        passes.enable_on_view_layer(vl, visual_passes)
        # Visual pass uses Raw view transform because compositor writes EXR.
        bpy.context.scene.view_settings.view_transform = 'Raw'
        if args.material == 'file_embedded':
            # Use bpy importer; keep OBJ+MTL / GLB / FBX materials as-is.
            objs = scene_obj.instantiate_with_file_materials()
        else:
            objs = scene_obj.instantiate_into_blender(material_fn)
        if args.material in ('uv_color', 'uv_checker') and args.auto_unwrap:
            from lib import uv as uv_mod
            for o in objs:
                if not uv_mod.has_uvs(o):
                    uv_mod.smart_unwrap(o)

    def configure_output(path):
        passes.setup_compositor_multilayer(path, visual_passes)

    return build_scene, configure_output


def make_mask_step(args, scene_obj, mask_passes, hdri):
    """One Cycles invocation that produces alpha/indexob with crisp edges."""
    import bpy

    def build_scene(fi):
        # film_transparent gives us alpha regardless of world; keeping HDRI on
        # is harmless because we route the Alpha socket (not Image).
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=1, resolution=args.res, denoise=False)
        bpy.context.scene.cycles.pixel_filter_type = 'BOX'
        bpy.context.scene.cycles.filter_width = 0.01
        bpy.context.scene.render.film_transparent = True
        vl = bpy.context.scene.view_layers[0]
        passes.enable_on_view_layer(vl, mask_passes)
        bpy.context.scene.view_settings.view_transform = 'Raw'

        # Grey diffuse for the geometry; pass_index = part_id + 1
        grey = materials.diffuse_realistic('mat_mask', (0.8, 0.8, 0.8, 1.0))
        scene_obj.instantiate_into_blender(lambda o, i: grey)

    def configure_output(path):
        passes.setup_compositor_multilayer(path, mask_passes)

    return build_scene, configure_output


def make_rgb_only_step(args, scene_obj, material_fn, hdri):
    """The PNG fast path: no compositor, Blender writes the PNG directly."""
    import bpy

    def build_scene(fi):
        world.set_world_hdri(hdri, strength=args.hdri_strength)
        render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        bpy.context.scene.use_nodes = False
        if args.material == 'file_embedded':
            objs = scene_obj.instantiate_with_file_materials()
        else:
            objs = scene_obj.instantiate_into_blender(material_fn)
        if args.material in ('uv_color', 'uv_checker') and args.auto_unwrap:
            from lib import uv as uv_mod
            for o in objs:
                if not uv_mod.has_uvs(o):
                    uv_mod.smart_unwrap(o)

    def configure_output(path):
        cli.configure_output_format(bpy.context.scene, 'png')

    return build_scene, configure_output


# ---------------------------------------------------------------------------
# Single-job runner (called once in single-shot mode, once per job in batch)

def run_one_job(args):
    if not args.scene:
        raise SystemExit('--scene is required')
    if not args.out_dir:
        raise SystemExit('--out_dir is required')
    if args.material is None:
        args.material = default_material(args.scene)
    if args.material == 'file_embedded' and args.scene != 'mesh':
        raise SystemExit('--material file_embedded only works with --scene mesh')

    scene_obj = resolve_scene(args)
    print(f'[scene] {scene_obj.source}: {len(scene_obj.objects)} object(s), '
          f'diag={scene_obj.diag:.3f}, has_parts={scene_obj.has_parts}')

    material_fn = material_registry.make_factory(args)
    pass_list = passes.parse(args.outputs)
    visual_passes = [p for p in pass_list if p in ('rgb', 'depth', 'normal')]
    mask_passes = [p for p in pass_list if p in ('alpha', 'indexob')]
    rgb_only = pass_list == ['rgb']

    hdri = args.hdri if os.path.isabs(args.hdri) \
        else os.path.join(world.ENVMAP_DIR, args.hdri)

    traj = cli.build_trajectory(args)
    os.makedirs(args.out_dir, exist_ok=True)

    if rgb_only:
        build, cfg = make_rgb_only_step(args, scene_obj, material_fn, hdri)
        mp4_out = (os.path.join(args.out_dir, 'video.mp4')
                    if args.mp4 else None)
        render_frames(traj, scene_obj.center, scene_obj.diag,
                       out_dir=args.out_dir, build_scene=build,
                       configure_output=cfg, extension='png',
                       mp4_out=mp4_out, fps=args.fps)
        return

    # Multilayer path: 1 or 2 Cycles invocations per frame.
    needs_two = bool(visual_passes) and bool(mask_passes)

    if not needs_two:
        active_passes = visual_passes or mask_passes
        if mask_passes:
            build, cfg = make_mask_step(args, scene_obj, active_passes, hdri)
        else:
            build, cfg = make_visual_step(args, scene_obj, material_fn,
                                            active_passes, hdri)
        render_frames(traj, scene_obj.center, scene_obj.diag,
                       out_dir=args.out_dir, build_scene=build,
                       configure_output=cfg, use_multilayer_dirs=True)
    else:
        # Two-pass: visual then mask. Write to staging subdirs, then
        # consolidate so each frame dir holds visual.exr + mask.exr.
        visual_dir = os.path.join(args.out_dir, '_visual')
        mask_dir = os.path.join(args.out_dir, '_mask')

        vb, vc = make_visual_step(args, scene_obj, material_fn,
                                    visual_passes, hdri)
        render_frames(traj, scene_obj.center, scene_obj.diag,
                       out_dir=visual_dir, build_scene=vb, configure_output=vc,
                       use_multilayer_dirs=True)

        mb, mc = make_mask_step(args, scene_obj, mask_passes, hdri)
        render_frames(traj, scene_obj.center, scene_obj.diag,
                       out_dir=mask_dir, build_scene=mb, configure_output=mc,
                       use_multilayer_dirs=True)

        for fi in range(len(traj)):
            target = os.path.join(args.out_dir, f'f{fi:04d}')
            os.makedirs(target, exist_ok=True)
            for src_dir, dst_name in (
                    (visual_dir, 'visual.exr'),
                    (mask_dir, 'mask.exr')):
                src = os.path.join(src_dir, f'f{fi:04d}', '0001.exr')
                if os.path.isfile(src):
                    shutil.move(src, os.path.join(target, dst_name))
        shutil.rmtree(visual_dir, ignore_errors=True)
        shutil.rmtree(mask_dir, ignore_errors=True)

    print('[decode] EXR -> per-pass PNGs:')
    print(f'  python scripts/exr_to_png.py --dir {args.out_dir}')


# ---------------------------------------------------------------------------
# Batch / multi-node runner

def _read_manifest(path: str):
    """Return list of dicts, one per non-empty non-comment line."""
    jobs = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            try:
                jobs.append(json.loads(s))
            except json.JSONDecodeError as e:
                raise SystemExit(f'manifest line {i}: {e}')
    return jobs


def _merge(cli_args, overrides: dict):
    """CLI flags = defaults; per-job dict overrides win."""
    a = copy.copy(cli_args)
    for k, v in overrides.items():
        if not hasattr(a, k):
            print(f'  ! ignoring unknown manifest key: {k}')
            continue
        setattr(a, k, v)
    # Per-job material default depends on per-job scene
    if 'material' not in overrides and a.scene:
        a.material = None  # let run_one_job pick the scene-specific default
    return a


def run_batch(cli_args):
    all_jobs = _read_manifest(cli_args.manifest)
    sliced = all_jobs[cli_args.rank::cli_args.world] \
        if cli_args.world > 1 else all_jobs
    print(f'[batch] manifest={cli_args.manifest} '
          f'rank={cli_args.rank}/{cli_args.world} '
          f'-> {len(sliced)}/{len(all_jobs)} jobs')

    n_ok = n_fail = 0
    for i, overrides in enumerate(sliced):
        tag = (overrides.get('out_dir')
               or overrides.get('mesh')
               or overrides.get('urdf')
               or '?')
        print(f'[batch {i + 1}/{len(sliced)}] {tag}')
        try:
            run_one_job(_merge(cli_args, overrides))
            n_ok += 1
        except (SystemExit, Exception) as e:
            n_fail += 1
            print(f'  ! failed: {type(e).__name__}: {e}')
            if not cli_args.continue_on_error:
                raise
            traceback.print_exc(limit=2)
    print(f'[batch] rank {cli_args.rank}: '
          f'{n_ok} succeeded, {n_fail} failed (of {len(sliced)})')


def main():
    ap = argparse.ArgumentParser()
    add_args(ap)
    cli_args = ap.parse_args(parse_blender_argv())
    if cli_args.manifest:
        run_batch(cli_args)
    else:
        run_one_job(cli_args)


if __name__ == '__main__':
    main()
