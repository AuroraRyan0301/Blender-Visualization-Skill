"""Unified render pipeline. GPU-only Cycles.

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
    --mp4 --fps   (for rgb output)

Outputs route through a multilayer EXR + post-decoder, unless the only output
is 'rgb' in which case Blender writes the PNG directly via the Standard view
transform.
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse_blender_argv, resolve_obj_path
from lib import (cli, material_registry, materials, passes, render_setup,
                  scene as scene_mod, scene_assembly, world)
from lib.render_pipeline import render_frames


def add_args(ap):
    # Scene assembly
    s = ap.add_argument_group('scene')
    s.add_argument('--scene', required=True,
                    choices=['mesh', 'parts', 'urdf'])
    s.add_argument('--mesh', help='path to mesh file (mesh/parts modes), or '
                                    'KaiNinja obj-id')
    s.add_argument('--face_ids', help='[parts] face_ids.npy; auto-resolved '
                                        'for KaiNinja obj-id')
    s.add_argument('--urdf', help='[urdf] URDF file')
    s.add_argument('--mesh_root', help='[urdf] base dir for package:// resolution')
    s.add_argument('--select_parts', default='all',
                    help='[parts/urdf] comma-separated part ids or "all"')
    s.add_argument('--normalize', choices=['whole', 'selected', 'none'],
                    default='whole')
    s.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')

    # Material
    m = ap.add_argument_group('material')
    m.add_argument('--material', choices=material_registry.NAMES,
                    default=None,
                    help='default: diffuse for mesh, tab20 for parts, embedded for urdf')
    m.add_argument('--color', type=float, nargs=3, default=[0.8, 0.8, 0.8])
    m.add_argument('--roughness', type=float, default=0.5)
    m.add_argument('--metallic', type=float, default=0.0)
    m.add_argument('--pbr_dir', help='[pbr] folder with PBR maps')
    m.add_argument('--uv_scale', type=float, nargs=2, default=[1.0, 1.0])
    m.add_argument('--normal_strength', type=float, default=1.0)
    m.add_argument('--displacement_scale', type=float, default=0.0)
    m.add_argument('--checker_scale', type=float, default=10.0)
    m.add_argument('--auto_unwrap', action='store_true')

    # World
    cli.add_world_args(ap)

    # Camera
    cli.add_camera_args(ap)

    # Output
    o = ap.add_argument_group('output')
    o.add_argument('--out_dir', required=True)
    o.add_argument('--outputs', default='rgb',
                    help='comma-separated subset of {rgb,depth,normal,mask}')
    o.add_argument('--samples', type=int, default=64)
    o.add_argument('--res', type=int, default=1024)
    cli.add_video_args(ap)


def _resolve_scene(args):
    """Build the Scene from --scene + the relevant inputs."""
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
            sel = [int(x) for x in args.select_parts.split(',') if x.strip() != '']
        return scene_assembly.Scene.from_parts(
            path, fids, normalize=args.normalize,
            source_frame=args.source_frame, select_parts=sel)
    if args.scene == 'urdf':
        if not args.urdf:
            raise SystemExit('--scene urdf requires --urdf')
        return scene_assembly.Scene.from_urdf(
            args.urdf, mesh_root=args.mesh_root, normalize=args.normalize)
    raise SystemExit(f'unknown scene: {args.scene}')


def _default_material(scene_kind: str) -> str:
    return {'mesh': 'diffuse', 'parts': 'tab20', 'urdf': 'embedded'}[scene_kind]


def main():
    ap = argparse.ArgumentParser()
    add_args(ap)
    args = ap.parse_args(parse_blender_argv())
    if args.material is None:
        args.material = _default_material(args.scene)

    import bpy
    scene_obj = _resolve_scene(args)
    print(f'[scene] {scene_obj.source}: {len(scene_obj.objects)} object(s), '
          f'diag={scene_obj.diag:.3f}, has_parts={scene_obj.has_parts}')

    material_fn = material_registry.make_factory(args)
    pass_list = passes.parse(args.outputs)
    use_multilayer = (pass_list != ['rgb'])
    is_mask = passes.is_mask_render(pass_list)

    hdri = args.hdri if os.path.isabs(args.hdri) \
        else os.path.join(world.ENVMAP_DIR, args.hdri)

    def build_scene(fi):
        if is_mask:
            world.set_world_black()
            render_setup.setup_cycles(samples=args.samples, resolution=args.res,
                                        denoise=False)
            bpy.context.scene.cycles.pixel_filter_type = 'BOX'
            bpy.context.scene.cycles.filter_width = 0.01
            bpy.context.scene.render.film_transparent = True
        else:
            world.set_world_hdri(hdri, strength=args.hdri_strength)
            render_setup.setup_cycles(samples=args.samples, resolution=args.res)
        vl = bpy.context.scene.view_layers[0]
        passes.enable_on_view_layer(vl, pass_list)
        if not use_multilayer:
            bpy.context.scene.use_nodes = False
        bpy.context.scene.view_settings.view_transform = \
            'Raw' if use_multilayer else 'Standard'
        objs = scene_obj.instantiate_into_blender(material_fn)
        if args.material in ('uv_color', 'uv_checker') and args.auto_unwrap:
            from lib import uv as uv_mod
            for o in objs:
                if not uv_mod.has_uvs(o):
                    uv_mod.smart_unwrap(o)

    def configure_output(path):
        if use_multilayer:
            passes.setup_compositor_multilayer(path, pass_list)
        else:
            cli.configure_output_format(bpy.context.scene, 'png')

    mp4_out = (os.path.join(args.out_dir, 'video.mp4')
                if (args.mp4 and not use_multilayer) else None)

    render_frames(cli.build_trajectory(args),
                   scene_obj.center, scene_obj.diag,
                   out_dir=args.out_dir,
                   build_scene=build_scene,
                   configure_output=configure_output,
                   extension='png',
                   use_multilayer_dirs=use_multilayer,
                   mp4_out=mp4_out, fps=args.fps)

    if use_multilayer:
        # OpenEXR isn't in Blender's bundled python; decode under a system
        # python that has `pip install OpenEXR matplotlib`.
        print('[decode] EXR -> per-pass PNGs:')
        print(f'  python scripts/exr_to_png.py --dir {args.out_dir}')
        if is_mask and passes.has_visual(pass_list):
            print('[warn] mask mode forces BOX filter + film_transparent, '
                  'so the rgb pass will look aliased. Render rgb and mask '
                  'separately if you need both at full quality.')


if __name__ == '__main__':
    main()
