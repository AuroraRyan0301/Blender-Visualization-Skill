"""EXR -> PNG conversion + colorbars / legends.

Linear → sRGB transfer follows the IEC 61966-2-1 piecewise curve (the standard
Blender uses internally for its Standard view transform). EXR pixels are in
scene-linear space; multiply by exposure if needed, then apply this curve.

Background detection:
  depth   pixel > 1e8         -> background
  normal  ||N|| < 1e-3         -> background
"""
import os
import numpy as np


def srgb_to_linear(img: np.ndarray) -> np.ndarray:
    """sRGB-encoded (0..1) -> scene-linear (0..1+). Vectorized."""
    limit = 0.04045
    return np.where(img > limit,
                     ((img + 0.055) / 1.055) ** 2.4,
                     img / 12.92)


def linear_to_srgb(img: np.ndarray) -> np.ndarray:
    """Scene-linear -> sRGB-encoded (0..1). Clamp tonemapper above 1.

    Caller should apply exposure before this (multiply linear by 2**EV).
    """
    limit = 0.0031308
    out = np.where(img > limit,
                    1.055 * np.power(np.clip(img, 0, None), 1 / 2.4) - 0.055,
                    12.92 * img)
    out = np.clip(out, 0.0, 1.0)
    return out


def aces_tone_map(img: np.ndarray) -> np.ndarray:
    """ACES filmic — kept for callers that explicitly want filmic look.

    NOT the default. Plain linear_to_srgb is the policy default per the
    blender_kit conventions.
    """
    A, B, C, D, E = 2.51, 0.03, 2.43, 0.59, 0.14
    rgb = img[..., :3].copy()
    rgb = rgb ** 0.6
    rgb = (rgb * (A * rgb + B)) / (rgb * (C * rgb + D) + E)
    rgb = np.clip(rgb, 0.0, 1.0)
    out = img.copy()
    out[..., :3] = rgb
    return out


def exr_rgb_to_png(rgb: np.ndarray, out_path: str, exposure: float = 0.0,
                   tonemap: str = 'srgb') -> None:
    """Save (H,W,3|4) scene-linear RGB(A) EXR data to a PNG.

    tonemap: 'srgb' (default, the kit policy) or 'aces' (filmic).
    """
    import matplotlib.pyplot as plt
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    img = rgb.astype(np.float32).copy()
    if exposure != 0.0:
        img[..., :3] = img[..., :3] * (2.0 ** exposure)
    if tonemap == 'srgb':
        img[..., :3] = linear_to_srgb(img[..., :3])
    elif tonemap == 'aces':
        img = aces_tone_map(img)
    else:
        raise ValueError(f'unknown tonemap: {tonemap}')
    plt.imsave(out_path, np.clip(img, 0, 1))


def depth_to_png(depth: np.ndarray, out_path: str, cmap: str = 'viridis_r',
                 vmin: float = None, vmax: float = None,
                 colorbar: bool = True, unit: str = 'm') -> None:
    """Render a depth map with a real colorbar.

    Background pixels (Cycles writes ~1e10 for empty space) are masked white.
    """
    import matplotlib.pyplot as plt
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    valid = depth < 1e8
    if vmin is None:
        vmin = float(depth[valid].min()) if valid.any() else 0.0
    if vmax is None:
        vmax = float(depth[valid].max()) if valid.any() else 1.0
    d = np.where(valid, depth, np.nan)
    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    im = ax.imshow(d, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.axis('off')
    if colorbar:
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label(f'depth ({unit})')
    fig.savefig(out_path, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)


def normal_to_png(normal: np.ndarray, out_path: str, legend: bool = True) -> None:
    """Save normal map as (N+1)/2 RGB and overlay a unit-sphere legend.

    Pixels with ||N|| < 1e-3 are treated as background and rendered white.
    """
    import matplotlib.pyplot as plt
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    nrm = np.linalg.norm(normal, axis=-1, keepdims=True)
    bg = nrm[..., 0] < 1e-3
    n = np.where(nrm > 0, normal / np.clip(nrm, 1e-6, None), 0.0)
    img = np.clip((n + 1.0) / 2.0, 0, 1)
    img[bg] = 1.0

    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    ax.imshow(img)
    ax.axis('off')
    if legend:
        _overlay_sphere_legend(fig, ax)
    fig.savefig(out_path, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)


def _overlay_sphere_legend(fig, ax):
    """Inset axis showing the unit sphere under (N+1)/2 encoding."""
    H, W = 80, 80
    yy, xx = np.mgrid[-1:1:H * 1j, -1:1:W * 1j]
    r2 = xx * xx + yy * yy
    z = np.where(r2 <= 1.0, np.sqrt(np.clip(1 - r2, 0, 1)), np.nan)
    n = np.stack([xx, yy, z], axis=-1)
    img = (n + 1.0) / 2.0
    img[~np.isfinite(img)] = 1.0
    img = np.clip(img, 0, 1)
    iax = fig.add_axes([0.78, 0.08, 0.18, 0.18])
    iax.imshow(img)
    iax.set_xticks([]); iax.set_yticks([])
    iax.set_title('N', fontsize=8)


def make_grid(images, out_path: str, ncols: int = None, titles=None,
              figsize_per: float = 4.0):
    """Stack images into a grid PNG. images is a list of (H,W,3|4) arrays."""
    import matplotlib.pyplot as plt
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    n = len(images)
    if ncols is None:
        ncols = int(np.ceil(np.sqrt(n)))
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(figsize_per * ncols, figsize_per * nrows))
    axes = np.array(axes).reshape(-1)
    for i, ax in enumerate(axes):
        if i < n:
            ax.imshow(np.clip(images[i], 0, 1))
            if titles is not None and i < len(titles):
                ax.set_title(titles[i], fontsize=10)
        ax.axis('off')
    fig.savefig(out_path, bbox_inches='tight', pad_inches=0.1, dpi=150)
    plt.close(fig)


def linear_to_srgb_torch(img):
    """Torch version of linear_to_srgb. Lazy-import torch to keep numpy paths fast."""
    import torch
    limit = 0.0031308
    out = torch.where(img > limit,
                       1.055 * img.clamp(min=0).pow(1 / 2.4) - 0.055,
                       12.92 * img)
    out = out.clamp(0.0, 1.0)
    return out
