"""Stage 1: scene assembly.

Build a Scene from one of three sources:
  Scene.from_mesh(path)             single mesh, no part labels
  Scene.from_parts(mesh, face_ids)  mesh + per-face part IDs
  Scene.from_urdf(urdf, mesh_root)  URDF kinematic tree at rest pose

A Scene knows its objects (numpy V/F + optional part_id + optional world_matrix
for URDF rest-pose placement). Normalization is applied at construction time:
  whole     bbox over ALL original geometry (selected or not) -> unit cube
  selected  bbox over SELECTED subset only -> unit cube (recenters subset)
  none      pass-through

Selection via select_parts filters down to a subset of part_ids (or 'all').

The Scene's `instantiate_into_blender(material_fn)` creates bpy objects in the
current scene, calling material_fn(obj, idx) per object for the material.
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Iterable, Callable
import numpy as np

from . import mesh_io, normalize as norm_mod


@dataclass
class SceneObject:
    name: str
    V: np.ndarray
    F: np.ndarray
    part_id: int = 0
    world_matrix: Optional[object] = None   # mathutils.Matrix for URDF, else None
    color: Optional[Tuple[float, float, float, float]] = None  # URDF <material>


@dataclass
class Scene:
    objects: List[SceneObject]
    center: Tuple[float, float, float]
    diag: float
    has_parts: bool
    source: str = 'mesh'

    @classmethod
    def from_mesh(cls, path: str, *, normalize: str = 'whole',
                   source_frame: str = 'auto') -> 'Scene':
        V, F = mesh_io.load_mesh_arrays(path, source_frame=source_frame)
        objs = [SceneObject(name=os.path.basename(path), V=V, F=F, part_id=0)]
        return cls._finalize(objs, normalize, has_parts=False, source='mesh')

    @classmethod
    def from_parts(cls, mesh_path: str, face_ids_path: str, *,
                    normalize: str = 'whole', source_frame: str = 'auto',
                    select_parts: Optional[Iterable[int]] = None) -> 'Scene':
        V, F = mesh_io.load_mesh_arrays(mesh_path, source_frame=source_frame)
        fids = np.load(face_ids_path).astype(np.int64)
        if fids.shape[0] != F.shape[0]:
            raise ValueError(
                f'face_ids {fids.shape[0]} != face count {F.shape[0]}')
        all_pids = [int(p) for p in np.unique(fids) if int(p) >= 0]
        if select_parts is None or select_parts == 'all':
            selected = set(all_pids)
        else:
            selected = set(int(p) for p in select_parts)
            unknown = selected - set(all_pids)
            if unknown:
                print(f'[scene] warning: select_parts {sorted(unknown)} not in mesh')
            selected &= set(all_pids)
        objs = []
        for pid in sorted(selected):
            mask = fids == pid
            sub_F = F[mask]
            if sub_F.shape[0] == 0:
                continue
            used = np.unique(sub_F.flatten())
            vmap = -np.ones(V.shape[0], dtype=np.int64)
            vmap[used] = np.arange(len(used))
            objs.append(SceneObject(name=f'p{pid}', V=V[used],
                                      F=vmap[sub_F], part_id=pid))
        return cls._finalize(objs, normalize, has_parts=True, source='parts',
                              all_V=V if normalize == 'whole' else None)

    @classmethod
    def from_urdf(cls, urdf_path: str, *, mesh_root: str = None,
                   normalize: str = 'whole') -> 'Scene':
        # Defer to lib.urdf to walk the tree; convert each visual to numpy V,F.
        from . import urdf as urdf_mod
        from mathutils import Matrix, Euler, Vector
        robot = urdf_mod.parse_urdf(urdf_path)
        link_T = urdf_mod.compute_link_transforms(robot)
        objs: List[SceneObject] = []
        pid = 0
        for link_name, link in robot['links'].items():
            if link_name not in link_T:
                continue
            for vi, vis in enumerate(link['visuals']):
                shape = vis['shape']
                if shape is None:
                    continue
                xyz, rpy = vis['origin']
                local_T = Matrix.Translation(Vector(xyz)) @ \
                           Euler(rpy, 'XYZ').to_matrix().to_4x4()
                world_T = link_T[link_name] @ local_T
                V, F = _shape_to_arrays(shape, robot['urdf_dir'], mesh_root)
                if V is None:
                    continue
                objs.append(SceneObject(
                    name=f'{link_name}_v{vi}', V=V, F=F, part_id=pid,
                    world_matrix=world_T, color=vis['color']))
                pid += 1
        return cls._finalize(objs, normalize, has_parts=True, source='urdf')

    @classmethod
    def _finalize(cls, objs, normalize, *, has_parts, source, all_V=None):
        if not objs:
            raise ValueError('scene contains no geometry')
        if normalize == 'whole' and all_V is not None:
            # parts case with select subset but normalize over full mesh
            V_for_bbox = all_V
        else:
            # union of selected objects' world-space verts
            if any(o.world_matrix is not None for o in objs):
                pts = []
                for o in objs:
                    if o.world_matrix is not None:
                        T = np.array(o.world_matrix)
                        V_h = np.concatenate(
                            [o.V, np.ones((o.V.shape[0], 1), np.float32)], axis=1)
                        pts.append((T @ V_h.T).T[:, :3])
                    else:
                        pts.append(o.V)
                V_for_bbox = np.concatenate(pts, axis=0)
            else:
                V_for_bbox = np.concatenate([o.V for o in objs], axis=0)
        if normalize in ('whole', 'selected'):
            mn = V_for_bbox.min(0); mx = V_for_bbox.max(0)
            center = (mn + mx) / 2.0
            scale = float((mx - mn).max())
            scale = scale if scale > 0 else 1.0
            for o in objs:
                if o.world_matrix is not None:
                    from mathutils import Matrix, Vector
                    # p' = (p - center) / scale  ==>  S(1/scale) @ T(-center) @ M
                    T_neg = Matrix.Translation(Vector((-float(center[0]),
                                                          -float(center[1]),
                                                          -float(center[2]))))
                    S = Matrix.Scale(1.0 / scale, 4)
                    o.world_matrix = S @ T_neg @ o.world_matrix
                else:
                    o.V = ((o.V - center) / scale).astype(np.float32)
            new_center = (0.0, 0.0, 0.0)
            new_diag = float(np.linalg.norm(((mx - mn) / scale)))
        else:
            new_center = tuple(((V_for_bbox.min(0) + V_for_bbox.max(0)) / 2).tolist())
            new_diag = float(np.linalg.norm(V_for_bbox.max(0) - V_for_bbox.min(0)))
        return cls(objects=objs, center=new_center, diag=new_diag,
                    has_parts=has_parts, source=source)

    def instantiate_into_blender(self, material_fn: Callable):
        """Add every object to the current Blender scene.

        material_fn(obj: SceneObject, idx: int) -> bpy.Material. Returns the
        list of created bpy mesh objects (parallel to self.objects).
        """
        from . import scene as scene_mod
        created = []
        for i, o in enumerate(self.objects):
            mat = material_fn(o, i)
            bo = scene_mod.add_mesh_from_arrays(o.name, o.V, o.F, mat=mat,
                                                  smooth=False)
            if o.world_matrix is not None:
                bo.matrix_world = o.world_matrix
            bo.pass_index = o.part_id + 1  # 0 reserved for background
            created.append(bo)
        return created


def _shape_to_arrays(shape, urdf_dir, mesh_root):
    """URDF visual primitive -> (V, F) numpy arrays in URDF link frame."""
    from . import urdf as urdf_mod
    kind = shape[0]
    if kind == 'mesh':
        path = urdf_mod.resolve_mesh_filename(shape[1], urdf_dir, mesh_root)
        # URDF treats mesh data as already in link frame: no Y-up swap for OBJ.
        ext = os.path.splitext(path)[1].lower()
        if ext == '.obj':
            V, F = mesh_io.load_obj(path)  # Y-up? as-stored, no rotation
        else:
            V, F = mesh_io.load_mesh_arrays(path, source_frame='z_up')
        # Apply per-mesh scale
        scale = shape[2] if len(shape) > 2 else (1.0, 1.0, 1.0)
        V = V * np.array(scale, dtype=np.float32)
        return V, F
    if kind == 'box':
        sx, sy, sz = shape[1]
        h = np.array([sx / 2, sy / 2, sz / 2], dtype=np.float32)
        V = np.array([
            [-h[0], -h[1], -h[2]], [+h[0], -h[1], -h[2]],
            [+h[0], +h[1], -h[2]], [-h[0], +h[1], -h[2]],
            [-h[0], -h[1], +h[2]], [+h[0], -h[1], +h[2]],
            [+h[0], +h[1], +h[2]], [-h[0], +h[1], +h[2]],
        ], dtype=np.float32)
        F = np.array([
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
            [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3],
        ], dtype=np.int64)
        return V, F
    if kind in ('cylinder', 'sphere'):
        # For primitives more complex than a box, defer to bpy's primitive_*_add
        # by spawning a temp object and reading its mesh. Done here to keep the
        # Scene pure-numpy.
        return _primitive_to_arrays(shape)
    return None, None


def _primitive_to_arrays(shape):
    """Spawn a Blender primitive, read its mesh into numpy, delete it."""
    import bpy
    before = set(bpy.data.objects)
    kind = shape[0]
    if kind == 'cylinder':
        bpy.ops.mesh.primitive_cylinder_add(radius=shape[1], depth=shape[2],
                                              vertices=32)
    elif kind == 'sphere':
        bpy.ops.mesh.primitive_uv_sphere_add(radius=shape[1], segments=24,
                                               ring_count=12)
    else:
        return None, None
    new = next(iter(set(bpy.data.objects) - before))
    me = new.data
    me.calc_loop_triangles()
    V = np.array([v.co for v in me.vertices], dtype=np.float32)
    F = np.array([[t.vertices[0], t.vertices[1], t.vertices[2]]
                   for t in me.loop_triangles], dtype=np.int64)
    bpy.data.objects.remove(new, do_unlink=True)
    bpy.data.meshes.remove(me, do_unlink=True)
    return V, F
