"""Convert between mesh formats with correct axis handling.

Per-format native frame:
  obj, glb, gltf, fbx -> Y-up
  ply, stl, off       -> Z-up (no spec; this is the kit default)

Override with --source_frame / --target_frame if you know the source violates
its format's convention.

Usage:
  blender -b --python convert_mesh.py -- --in input.obj --out output.glb
"""
import os
import sys
import argparse

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)

sys.path.insert(0, THIS_DIR)
from _common import parse_blender_argv  # noqa: E402
from lib import mesh_io  # noqa: E402


def main():
    argv = parse_blender_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', dest='outp', required=True)
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')
    ap.add_argument('--target_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto')
    args = ap.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.outp)) or '.', exist_ok=True)
    mesh_io.convert(args.inp, args.outp,
                     source_frame=args.source_frame,
                     target_frame=args.target_frame)
    print(f'[convert] {args.inp} -> {args.outp}')


if __name__ == '__main__':
    main()
