"""Shared argv / path / mesh-load helpers for the entry scripts.

Launched as `blender -b --python script.py -- <args>`, so strip everything
before '--' before argparsing.
"""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)


def parse_blender_argv():
    if '--' not in sys.argv:
        return []
    return sys.argv[sys.argv.index('--') + 1:]


_MESH_EXTS = ('.obj', '.glb', '.gltf', '.ply', '.stl', '.fbx', '.off')


def resolve_obj_path(obj_arg: str):
    """Map a bare KaiNinja obj-id OR an absolute mesh path -> (mesh_path, fids_path?).

    Returns face_ids path only when the arg is a KaiNinja obj-id.
    """
    if obj_arg.lower().endswith(_MESH_EXTS):
        return obj_arg, None
    base = f'/gs/bs/tga-koike-shanda/yurh/KaiNinja_v2/preprocess/{obj_arg}'
    return f'{base}/mesh_cleaned.obj', f'{base}/face_ids.npy'


def configure_output_format(scene, output_format: str):
    """Map our --output_format to Blender's image_settings.

    'png': sRGB-encoded 8-bit PNG (Blender applies the Standard view transform).
    'exr': scene-linear 32-bit RGB EXR (no view transform).
    """
    s = scene
    if output_format == 'png':
        s.render.image_settings.file_format = 'PNG'
        s.render.image_settings.color_mode = 'RGBA'
        s.render.image_settings.color_depth = '8'
        s.view_settings.view_transform = 'Standard'
    elif output_format == 'exr':
        s.render.image_settings.file_format = 'OPEN_EXR'
        s.render.image_settings.color_mode = 'RGB'
        s.render.image_settings.color_depth = '32'
        s.render.image_settings.exr_codec = 'ZIP'
        s.view_settings.view_transform = 'Raw'
    else:
        raise ValueError(f'output_format must be png|exr, got {output_format}')
