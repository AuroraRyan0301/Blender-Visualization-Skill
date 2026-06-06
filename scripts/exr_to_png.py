"""Multilayer EXR -> per-pass PNGs.

Two modes:
  --dir <out_dir>    walk out_dir/f*/0001.exr (or v*/0001.exr) and auto-detect
                     which passes each EXR contains (rgb/depth/normal/alpha/
                     indexob). For each frame, writes a PNG per pass into the
                     frame's subdir.
  --exr_file <path>  single scene-linear RGB EXR -> sRGB PNG next to it.

When indexob is present, mask.png + mask_pNNN.png are also written.
Run with system python (not Blender's). Requires `pip install OpenEXR matplotlib`.
"""
import os
import sys
import argparse
import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)

from lib import decode, postproc  # noqa: E402


def _process_single_rgb(exr_path: str, out_png: str, exposure: float):
    import OpenEXR
    import Imath
    f = OpenEXR.InputFile(exr_path)
    header = f.header()
    dw = header['dataWindow']
    h = dw.max.y - dw.min.y + 1
    w = dw.max.x - dw.min.x + 1
    pt = Imath.PixelType(Imath.PixelType.FLOAT)
    suffixes = ['R', 'G', 'B']
    if 'A' in header['channels']:
        suffixes.append('A')
    bufs = [np.frombuffer(f.channel(s, pt), dtype=np.float32).reshape(h, w, 1)
            for s in suffixes]
    img = np.dstack(bufs)
    postproc.exr_rgb_to_png(img, out_png, exposure=exposure, tonemap='srgb')


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--dir', dest='multilayer_dir',
                    help='out_dir containing f*/0001.exr (or v*/0001.exr)')
    g.add_argument('--exr_file', help='single linear EXR -> PNG next to it')
    ap.add_argument('--exposure', type=float, default=0.0,
                    help='EV stops applied before sRGB encoding')
    args = ap.parse_args()

    if args.exr_file:
        out_png = os.path.splitext(args.exr_file)[0] + '.png'
        _process_single_rgb(args.exr_file, out_png, args.exposure)
        print(f'[exr->png] {out_png}')
        return

    frame_dirs = sorted(d for d in os.listdir(args.multilayer_dir)
                        if (d.startswith('f') or d.startswith('v')) and
                        os.path.isfile(os.path.join(args.multilayer_dir, d,
                                                      '0001.exr')))
    if not frame_dirs:
        sys.exit(f'no f*/0001.exr (or v*/0001.exr) in {args.multilayer_dir}')
    for d in frame_dirs:
        sub = os.path.join(args.multilayer_dir, d)
        written = decode.decode_frame(os.path.join(sub, '0001.exr'), sub,
                                        passes=None, exposure=args.exposure)
        print(f'[exr->png] {d}: {list(written.keys())}')


if __name__ == '__main__':
    main()
