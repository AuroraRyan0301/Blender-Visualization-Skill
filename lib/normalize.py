"""Normalization: recenter + scale mesh into a canonical box.

Two modes:
  - unit_cube:   max axis fits in [-0.5, 0.5]
  - unit_sphere: max ||v|| = 1
"""
import numpy as np


def normalize_verts(V: np.ndarray, mode: str = 'unit_cube'):
    """Return (V_norm, (center, scale)) where V_norm = (V - center) / scale.

    Apply the same (center, scale) to all parts of a multi-part mesh to
    preserve relative positions.
    """
    V = V.astype(np.float32)
    mn, mx = V.min(0), V.max(0)
    center = (mn + mx) / 2.0
    if mode == 'unit_cube':
        scale = float((mx - mn).max())
    elif mode == 'unit_sphere':
        scale = float(np.linalg.norm(V - center, axis=-1).max() * 2)
    else:
        raise ValueError(f'unknown normalize mode: {mode}')
    if scale <= 0:
        scale = 1.0
    return (V - center) / scale, (center, scale)


def scene_diag(V: np.ndarray) -> float:
    """Diagonal of axis-aligned bounding box. Use to size camera distance."""
    return float(np.linalg.norm(V.max(0) - V.min(0)))


def scene_center(V: np.ndarray) -> np.ndarray:
    return ((V.min(0) + V.max(0)) / 2.0).astype(np.float32)
