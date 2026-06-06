"""Bulk geometry builders for non-mesh scene sources.

All builders return (V, F) numpy arrays in Blender Z-up frame. They batch
many primitives into one mesh — N voxel cubes become one (8N, 12N) mesh, N
arrows become one (5N, 6N) mesh. Use one Scene per part_id so tab20 coloring
still works at the part level.

Pure numpy. No bpy dependency — safe to import outside Blender for testing.
"""
import numpy as np


# ---------------------------------------------------------------------------
# Voxel cubes

_CUBE_VERTS = np.array([
    [-1, -1, -1], [+1, -1, -1], [+1, +1, -1], [-1, +1, -1],
    [-1, -1, +1], [+1, -1, +1], [+1, +1, +1], [-1, +1, +1],
], dtype=np.float32) * 0.5  # unit cube ±0.5

_CUBE_TRIS = np.array([
    [0, 2, 1], [0, 3, 2],   # -Z
    [4, 5, 6], [4, 6, 7],   # +Z
    [0, 1, 5], [0, 5, 4],   # -Y
    [2, 3, 7], [2, 7, 6],   # +Y
    [1, 2, 6], [1, 6, 5],   # +X
    [0, 4, 7], [0, 7, 3],   # -X
], dtype=np.int64)


def cubes_at(centers: np.ndarray, size: float):
    """Pack N unit cubes (one per center) into a single mesh.

    centers: (N, 3) world-space cube centers
    size: edge length (scalar) — same for every cube
    Returns: V (8N, 3) float32, F (12N, 3) int64
    """
    n = centers.shape[0]
    if n == 0:
        return (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64))
    V = (centers[:, None, :] + _CUBE_VERTS[None, :, :] * size).reshape(-1, 3)
    base = (np.arange(n) * 8)[:, None, None]
    F = (_CUBE_TRIS[None, :, :] + base).reshape(-1, 3)
    return V.astype(np.float32), F.astype(np.int64)


# ---------------------------------------------------------------------------
# Arrows (shaft cylinder + cone head)

def _orthonormal_basis(z: np.ndarray):
    """For each unit z (N, 3), return (x, y) such that (x, y, z) is orthonormal.

    Picks a stable helper vector to avoid degeneracy near the +Z axis.
    """
    helper = np.tile(np.array([0, 0, 1], dtype=np.float32), (z.shape[0], 1))
    near_z = np.abs(z[:, 2]) > 0.95
    helper[near_z] = np.array([1, 0, 0], dtype=np.float32)
    x = np.cross(helper, z)
    x = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)
    y = np.cross(z, x)
    return x.astype(np.float32), y.astype(np.float32)


def arrows(positions: np.ndarray, directions: np.ndarray,
           lengths: np.ndarray = None, *,
           shaft_radius: float = 0.005,
           head_radius: float = 0.012,
           head_fraction: float = 0.3,
           sides: int = 6):
    """Build N arrows: each = open cylinder (shaft) + cone (head).

    positions: (N, 3) tail position of each arrow
    directions: (N, 3) direction vector (will be normalized)
    lengths: (N,) total length of arrow (shaft + head). If None, uses ||directions||.
    sides: polygon resolution around the shaft/cone axis.

    Per arrow: 2*sides (shaft ring verts) + 1 (shaft top center) + sides (cone base)
        + 1 (cone tip) = 3*sides + 2 vertices.
    Per arrow: 2*sides (shaft side tris, no caps) + sides (cone side tris) = 3*sides tris.
    """
    n = positions.shape[0]
    if n == 0:
        return (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64))
    pos = positions.astype(np.float32)
    raw_d = directions.astype(np.float32)
    norms = np.linalg.norm(raw_d, axis=1)
    if lengths is None:
        L = norms.copy()
    else:
        L = lengths.astype(np.float32)
    z = raw_d / np.maximum(norms[:, None], 1e-9)
    x, y = _orthonormal_basis(z)

    head_L = (L * head_fraction)[:, None]
    shaft_L = (L * (1.0 - head_fraction))[:, None]
    shaft_top = pos + z * shaft_L                    # (N, 3)
    arrow_tip = pos + z * (shaft_L + head_L)         # (N, 3)

    theta = np.linspace(0, 2 * np.pi, sides, endpoint=False, dtype=np.float32)
    ring_x = np.cos(theta)  # (sides,)
    ring_y = np.sin(theta)

    # Shaft bottom + top rings (each sides verts), per arrow
    shaft_bot = (pos[:, None, :]
                 + x[:, None, :] * (ring_x[None, :, None] * shaft_radius)
                 + y[:, None, :] * (ring_y[None, :, None] * shaft_radius))   # (N, sides, 3)
    shaft_top_ring = shaft_bot + z[:, None, :] * shaft_L[:, None, :]          # (N, sides, 3)
    cone_base = (shaft_top[:, None, :]
                 + x[:, None, :] * (ring_x[None, :, None] * head_radius)
                 + y[:, None, :] * (ring_y[None, :, None] * head_radius))     # (N, sides, 3)
    tip = arrow_tip[:, None, :]                                               # (N, 1, 3)

    # Pack into per-arrow vertex order: [shaft_bot, shaft_top_ring, cone_base, tip]
    V_per = np.concatenate([shaft_bot, shaft_top_ring, cone_base, tip], axis=1)  # (N, 3*sides+1, 3)
    V = V_per.reshape(-1, 3)
    verts_per_arrow = 3 * sides + 1
    base = (np.arange(n) * verts_per_arrow)[:, None, None]

    # Shaft side quads -> 2 tris each (sides quads). Indices into shaft_bot [0..sides) + shaft_top_ring [sides..2sides)
    shaft_tris = []
    for i in range(sides):
        i2 = (i + 1) % sides
        b0, b1 = i, i2
        t0, t1 = sides + i, sides + i2
        shaft_tris.append([b0, t0, t1])
        shaft_tris.append([b0, t1, b1])
    # Cone side tris (sides triangles): tip (idx 3*sides) + cone_base[i] + cone_base[i+1]
    cone_tris = []
    tip_idx = 3 * sides
    for i in range(sides):
        i2 = (i + 1) % sides
        cone_tris.append([2 * sides + i, tip_idx, 2 * sides + i2])
    F_per = np.array(shaft_tris + cone_tris, dtype=np.int64)  # (3*sides, 3)
    F = (F_per[None, :, :] + base).reshape(-1, 3)
    return V.astype(np.float32), F.astype(np.int64)


# ---------------------------------------------------------------------------
# Bounding boxes (solid cuboids; flag for wireframe = todo)

def bboxes(mins: np.ndarray, maxs: np.ndarray):
    """N axis-aligned cuboids from (mins, maxs) each (N, 3)."""
    centers = (mins + maxs) / 2.0
    sizes = (maxs - mins)
    n = centers.shape[0]
    if n == 0:
        return (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64))
    # Build per-cube with per-axis size — can't reuse cubes_at directly.
    V = np.empty((n, 8, 3), np.float32)
    for axis in range(3):
        V[:, :, axis] = centers[:, axis:axis + 1] + _CUBE_VERTS[None, :, axis] * sizes[:, axis:axis + 1]
    base = (np.arange(n) * 8)[:, None, None]
    F = (_CUBE_TRIS[None, :, :] + base).reshape(-1, 3)
    return V.reshape(-1, 3).astype(np.float32), F.astype(np.int64)
