"""Multilayer EXR -> per-pass PNGs.

Takes the multilayer EXR produced by passes.setup_compositor_multilayer and
emits one PNG per pass. 'mask' is the special-case alias for {alpha + indexob}
that produces mask.png (silhouette) + mask_pNNN.png per part.
"""
import os
import numpy as np

from . import exr_reader, postproc

_ALL_PASSES = ('rgb', 'depth', 'normal', 'alpha', 'indexob')


def list_layers(exr_path: str):
    """Set of layer names present in `exr_path` (chars before the channel dot)."""
    import OpenEXR
    f = OpenEXR.InputFile(exr_path)
    return set(c.split('.')[0] for c in f.header()['channels'].keys())


def decode_frame(exr_path: str, out_dir: str, passes=None,
                  exposure: float = 0.0, alpha_threshold: float = 0.5) -> dict:
    """Decode every requested pass into a PNG inside out_dir.

    Returns {pass_name: list of written paths}. 'mask' aggregates alpha +
    indexob into mask.png + mask_p{pid:03d}.png — only emitted when both layers
    were rendered.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = {}
    available = list_layers(exr_path)
    if passes is None:
        have = [p for p in _ALL_PASSES if p in available]
    else:
        have = [p for p in passes if p in available]
    if not have:
        return written
    layers = exr_reader.read_multilayer(exr_path, layers=tuple(have))

    if 'rgb' in have:
        path = os.path.join(out_dir, 'rgb.png')
        postproc.exr_rgb_to_png(layers['rgb'], path, exposure=exposure,
                                 tonemap='srgb')
        written['rgb'] = [path]
    if 'depth' in have:
        path = os.path.join(out_dir, 'depth.png')
        postproc.depth_to_png(layers['depth'], path)
        written['depth'] = [path]
    if 'normal' in have:
        path = os.path.join(out_dir, 'normal.png')
        postproc.normal_to_png(layers['normal'], path)
        written['normal'] = [path]

    if 'alpha' in have:
        import matplotlib.pyplot as plt
        alpha = layers['alpha']
        mask = (alpha > alpha_threshold).astype(np.uint8) * 255
        path = os.path.join(out_dir, 'mask.png')
        plt.imsave(path, mask, cmap='gray', vmin=0, vmax=255)
        written['mask'] = [path]
        if 'indexob' in have:
            idx_int = np.rint(layers['indexob']).astype(np.int64)
            for k in sorted(int(v) for v in np.unique(idx_int)):
                if k <= 0:
                    continue
                pmask = ((idx_int == k) & (alpha > alpha_threshold)).astype(np.uint8) * 255
                pid = k - 1
                pp = os.path.join(out_dir, f'mask_p{pid:03d}.png')
                plt.imsave(pp, pmask, cmap='gray', vmin=0, vmax=255)
                written['mask'].append(pp)
    return written


def decode_directory(root_dir: str, passes=None,
                      exposure: float = 0.0) -> list:
    """Walk root_dir/f*/ and decode every *.exr inside. Returns frame dirs.

    Supports single-EXR frames (0001.exr) and two-pass frames
    (visual.exr + mask.exr). PNGs land in the frame's own subdir.
    """
    frame_dirs = sorted(d for d in os.listdir(root_dir)
                        if (d.startswith('f') or d.startswith('v')) and
                        os.path.isdir(os.path.join(root_dir, d)))
    out = []
    for d in frame_dirs:
        sub = os.path.join(root_dir, d)
        exrs = sorted(f for f in os.listdir(sub) if f.endswith('.exr'))
        if not exrs:
            continue
        for exr in exrs:
            decode_frame(os.path.join(sub, exr), sub, passes,
                          exposure=exposure)
        out.append(sub)
    return out
