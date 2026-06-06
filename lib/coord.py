"""OBJ (Y-up, -Z forward) <-> Blender (Z-up, -Y forward) coordinate transform.

bpy.ops.import_scene.obj bakes R_x(+90deg) into matrix_world, but when we build
meshes via mesh.from_pydata we receive raw OBJ-frame vertices. Use these
helpers to convert positions/directions before they touch any Blender API.
"""
import numpy as np


def obj_to_blender_pts(v: np.ndarray) -> np.ndarray:
    """(N,3) OBJ Y-up -> Blender Z-up. (x,y,z) -> (x,-z,y)."""
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=-1).astype(np.float32)


def obj_to_blender_dir(d: np.ndarray) -> np.ndarray:
    """Same as positions — pure rotation, no translation."""
    return obj_to_blender_pts(d)


def blender_to_obj_pts(v: np.ndarray) -> np.ndarray:
    """(N,3) Blender -> OBJ. Inverse of obj_to_blender_pts."""
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=-1).astype(np.float32)
