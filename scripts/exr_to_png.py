"""Decode rendered EXR -> PNG via linear_to_srgb.

Two input modes:
  --exr_dir <dir>  : multilayer EXR per view (depth+normal pipeline). Walks
                     v*/0001.exr and writes rgb.png/depth.png/normal.png +
                     a combined grid.png.
  --exr_file <path>: single scene-linear EXR (RGB) -> linear_to_srgb -> PNG
                     at <path>.png.

Run with system python (not Blender's). Requires `pip install OpenEXR`.
"""
import os
import sys
import argparse
import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)

from lib import exr_reader, postproc  # noqa: E402


def process_multilayer_view(exr_path: str, out_view_dir: str, exposure: float):
    layers = exr_reader.read_multilayer(exr_path,
                                         layers=('rgb', 'depth', 'normal'))
    rgb_png = os.path.join(out_view_dir, 'rgb.png')
    depth_png = os.path.join(out_view_dir, 'depth.png')
    normal_png = os.path.join(out_view_dir, 'normal.png')
    postproc.exr_rgb_to_png(layers['rgb'], rgb_png,
                             exposure=exposure, tonemap='srgb')
    postproc.depth_to_png(layers['depth'], depth_png)
    postproc.normal_to_png(layers['normal'], normal_png)
    return rgb_png, depth_png, normal_png


def process_single_rgb_exr(exr_path: str, out_png: str, exposure: float):
    """Single-layer scene-linear EXR (Blender's OPEN_EXR output) -> PNG."""
    import OpenEXR
    import Imath
    f = OpenEXR.InputFile(exr_path)
    header = f.header()
    dw = header['dataWindow']
    h = dw.max.y - dw.min.y + 1
    w = dw.max.x - dw.min.x + 1
    pt = Imath.PixelType(Imath.PixelType.FLOAT)
    channels = header['channels']
    suffixes = ['R', 'G', 'B']
    if 'A' in channels:
        suffixes.append('A')
    bufs = [np.frombuffer(f.channel(s, pt), dtype=np.float32).reshape(h, w, 1)
            for s in suffixes]
    img = np.dstack(bufs)
    postproc.exr_rgb_to_png(img, out_png, exposure=exposure, tonemap='srgb')
    return out_png


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--exr_dir',
                    help='multilayer EXR root (contains v*/0001.exr ...)')
    g.add_argument('--exr_file', help='single linear EXR file -> PNG next to it')
    ap.add_argument('--exposure', type=float, default=0.0,
                    help='EV stops applied before sRGB encoding (0 = no change)')
    ap.add_argument('--grid', action='store_true', default=True)
    args = ap.parse_args()

    if args.exr_file:
        out_png = os.path.splitext(args.exr_file)[0] + '.png'
        process_single_rgb_exr(args.exr_file, out_png, args.exposure)
        print(f'[exr->png] {out_png}')
        return

    import matplotlib.pyplot as plt
    view_dirs = sorted(d for d in os.listdir(args.exr_dir)
                       if d.startswith('v') and
                       os.path.isfile(os.path.join(args.exr_dir, d, '0001.exr')))
    if not view_dirs:
        sys.exit(f'no v*/0001.exr in {args.exr_dir}')

    rows = []
    for v in view_dirs:
        vdir = os.path.join(args.exr_dir, v)
        exr = os.path.join(vdir, '0001.exr')
        rgb_png, depth_png, normal_png = process_multilayer_view(exr, vdir,
                                                                   args.exposure)
        rows.append((rgb_png, depth_png, normal_png))
        print(f'[exr->png] {v}: rgb/depth/normal in {vdir}')

    if args.grid:
        n_views = len(rows)
        fig, axes = plt.subplots(n_views, 3, figsize=(12, 4 * n_views))
        if n_views == 1:
            axes = axes.reshape(1, -1)
        for i, (r, d, n) in enumerate(rows):
            for j, p in enumerate((r, d, n)):
                axes[i, j].imshow(plt.imread(p))
                axes[i, j].axis('off')
                if i == 0:
                    axes[i, j].set_title(['rgb', 'depth', 'normal'][j])
        grid_path = os.path.join(args.exr_dir, 'grid.png')
        fig.savefig(grid_path, bbox_inches='tight', dpi=120)
        plt.close(fig)
        print(f'[grid] {grid_path}')


if __name__ == '__main__':
    main()
