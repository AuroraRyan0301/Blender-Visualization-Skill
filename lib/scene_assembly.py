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
    source_path: Optional[str] = None        # for file_embedded re-import
    normalize_transform: Optional[object] = None  # 4x4 mathutils Matrix or None

    @classmethod
    def from_mesh(cls, path: str, *, normalize: str = 'whole',
                   source_frame: str = 'auto') -> 'Scene':
        V, F = mesh_io.load_mesh_arrays(path, source_frame=source_frame)
        objs = [SceneObject(name=os.path.basename(path), V=V, F=F, part_id=0)]
        s = cls._finalize(objs, normalize, has_parts=False, source='mesh')
        s.source_path = path
        return s

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
    def from_voxels(cls, npz_path: str, *,
                    coords_key: str = 'coords',
                    part_id_key: Optional[str] = 'part_id',
                    dv_key: Optional[str] = 'dual_vertices',
                    grid_resolution: int = 512,
                    voxel_size: float = 0.003,
                    max_voxels: Optional[int] = None,
                    normalize: str = 'whole',
                    select_parts: Optional[Iterable[int]] = None) -> 'Scene':
        """Voxel point cloud rendered as N small cubes.

        Each voxel = one unit cube of `voxel_size` edge length. Positions are
        (coords + optional dual_vertices) / grid_resolution - 0.5, mapping a
        grid_resolution³ voxel grid to [-0.5, 0.5]³.

        One SceneObject per part_id so tab20 colors apply per part.
        """
        from . import primitives
        d = np.load(npz_path)
        coords = d[coords_key].astype(np.float32)
        if dv_key and dv_key in d.files:
            coords = coords + d[dv_key].astype(np.float32)
        pos = coords / float(grid_resolution) - 0.5
        if part_id_key and part_id_key in d.files:
            pids = d[part_id_key].astype(np.int32)
        else:
            pids = np.zeros(len(pos), dtype=np.int32)
        if max_voxels is not None and len(pos) > max_voxels:
            idx = np.random.default_rng(0).choice(len(pos), max_voxels,
                                                    replace=False)
            pos, pids = pos[idx], pids[idx]
        all_pids = sorted(int(p) for p in np.unique(pids) if int(p) >= 0)
        if select_parts is not None and select_parts != 'all':
            sel = set(int(x) for x in select_parts)
            keep = [p for p in all_pids if p in sel]
        else:
            keep = all_pids
        objs = []
        for pid in keep:
            mask = pids == pid
            V, F = primitives.cubes_at(pos[mask], voxel_size)
            if V.shape[0] == 0:
                continue
            objs.append(SceneObject(name=f'vox_p{pid}', V=V, F=F, part_id=pid))
        return cls._finalize(objs, normalize, has_parts=len(keep) > 1,
                              source='voxels')

    @classmethod
    def from_arrows(cls, npz_path: str, *,
                    positions_key: str = 'positions',
                    directions_key: str = 'directions',
                    part_id_key: Optional[str] = 'part_id',
                    lengths_key: Optional[str] = None,
                    max_arrows: int = 300,
                    shaft_radius: float = 0.005,
                    head_radius: float = 0.012,
                    head_fraction: float = 0.3,
                    arrow_sides: int = 6,
                    normalize: str = 'none',
                    select_parts: Optional[Iterable[int]] = None) -> 'Scene':
        """Arrows = cylinder shaft + cone head, one per (position, direction).

        normalize='none' is the sensible default because arrows are usually
        overlaid on something else and you want their world coords to match.
        """
        from . import primitives
        d = np.load(npz_path)
        pos = d[positions_key].astype(np.float32)
        dirs = d[directions_key].astype(np.float32)
        norms = np.linalg.norm(dirs, axis=1)
        if lengths_key and lengths_key in d.files:
            L = d[lengths_key].astype(np.float32)
        else:
            L = norms
        pids = d[part_id_key].astype(np.int32) if (part_id_key and part_id_key in d.files) \
            else np.zeros(len(pos), dtype=np.int32)
        if len(pos) > max_arrows:
            idx = np.linspace(0, len(pos) - 1, max_arrows).astype(np.int64)
            pos, dirs, L, pids = pos[idx], dirs[idx], L[idx], pids[idx]
        all_pids = sorted(int(p) for p in np.unique(pids) if int(p) >= 0)
        if select_parts is not None and select_parts != 'all':
            sel = set(int(x) for x in select_parts)
            keep = [p for p in all_pids if p in sel]
        else:
            keep = all_pids
        objs = []
        for pid in keep:
            mask = pids == pid
            V, F = primitives.arrows(
                pos[mask], dirs[mask], L[mask],
                shaft_radius=shaft_radius, head_radius=head_radius,
                head_fraction=head_fraction, sides=arrow_sides)
            if V.shape[0] == 0:
                continue
            objs.append(SceneObject(name=f'arr_p{pid}', V=V, F=F, part_id=pid))
        return cls._finalize(objs, normalize, has_parts=len(keep) > 1,
                              source='arrows')

    @classmethod
    def from_attraction(cls, npz_path: str, *,
                         coords_key: str = 'coords',
                         dv_key: Optional[str] = 'dual_vertices',
                         attraction_key: str = 'attraction',
                         part_id_key: Optional[str] = 'part_id',
                         grid_resolution: int = 512,
                         attr_slot: int = 0,
                         max_arrows: int = 300,
                         arrow_scale: float = 0.05,
                         normalize: str = 'whole',
                         select_parts: Optional[Iterable[int]] = None) -> 'Scene':
        """KaiNinja attraction field as arrows.

        The attraction array is (N, 9): 3 attraction targets per voxel × 3
        coords each. attr_slot picks which of the 3 to draw (0, 1, or 2).
        attr_slot=-1 means draw all 3 (3× more arrows).

        Positions: (coords + dv) / grid_resolution - 0.5.
        Direction: attraction[:, 3*slot : 3*slot+3] interpreted as a TARGET
                   relative to the voxel position; the arrow points from the
                   voxel toward the target. Length = arrow_scale * ||target||.
        """
        from . import primitives
        d = np.load(npz_path)
        coords = d[coords_key].astype(np.float32)
        if dv_key and dv_key in d.files:
            coords = coords + d[dv_key].astype(np.float32)
        pos = coords / float(grid_resolution) - 0.5
        attr = d[attraction_key].astype(np.float32)
        if attr.shape[1] != 9:
            raise ValueError(f'expected attraction (N,9), got {attr.shape}')
        pids = d[part_id_key].astype(np.int32) if (part_id_key and part_id_key in d.files) \
            else np.zeros(len(pos), dtype=np.int32)

        if attr_slot == -1:
            slots = (0, 1, 2)
        else:
            slots = (attr_slot,)
        positions_all, dirs_all, pids_all = [], [], []
        for s in slots:
            v = attr[:, 3 * s:3 * s + 3]
            positions_all.append(pos)
            dirs_all.append(v)
            pids_all.append(pids)
        pos_cat = np.concatenate(positions_all, axis=0)
        dir_cat = np.concatenate(dirs_all, axis=0)
        pid_cat = np.concatenate(pids_all, axis=0)
        L = np.linalg.norm(dir_cat, axis=1) * arrow_scale

        if len(pos_cat) > max_arrows:
            idx = np.linspace(0, len(pos_cat) - 1, max_arrows).astype(np.int64)
            pos_cat, dir_cat, L, pid_cat = pos_cat[idx], dir_cat[idx], L[idx], pid_cat[idx]
        all_pids = sorted(int(p) for p in np.unique(pid_cat) if int(p) >= 0)
        if select_parts is not None and select_parts != 'all':
            sel = set(int(x) for x in select_parts)
            keep = [p for p in all_pids if p in sel]
        else:
            keep = all_pids
        objs = []
        for pid in keep:
            mask = pid_cat == pid
            V, F = primitives.arrows(pos_cat[mask], dir_cat[mask], L[mask])
            if V.shape[0] == 0:
                continue
            objs.append(SceneObject(name=f'attr_p{pid}', V=V, F=F, part_id=pid))
        return cls._finalize(objs, normalize, has_parts=len(keep) > 1,
                              source='attraction')

    @classmethod
    def from_bboxes(cls, npz_path: str, *,
                     mins_key: str = 'mins',
                     maxs_key: str = 'maxs',
                     part_ids_key: Optional[str] = 'part_ids_unique',
                     normalize: str = 'whole') -> 'Scene':
        """Per-part axis-aligned bounding boxes as solid cuboids."""
        from . import primitives
        d = np.load(npz_path)
        if 'part_bboxes' in d.files:
            # KaiNinja convention: part_bboxes (P, 6) = [xmin,ymin,zmin,xmax,ymax,zmax]
            bb = d['part_bboxes'].astype(np.float32)
            mins, maxs = bb[:, :3], bb[:, 3:]
        else:
            mins = d[mins_key].astype(np.float32)
            maxs = d[maxs_key].astype(np.float32)
        if part_ids_key and part_ids_key in d.files:
            pids = d[part_ids_key].astype(np.int32)
        else:
            pids = np.arange(len(mins), dtype=np.int32)
        objs = []
        for i, pid in enumerate(pids):
            V, F = primitives.bboxes(mins[i:i + 1], maxs[i:i + 1])
            if V.shape[0] == 0:
                continue
            objs.append(SceneObject(name=f'bbox_p{pid}', V=V, F=F,
                                      part_id=int(pid)))
        return cls._finalize(objs, normalize, has_parts=len(objs) > 1,
                              source='bboxes')

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
        normalize_T = None
        if normalize in ('whole', 'selected'):
            mn = V_for_bbox.min(0); mx = V_for_bbox.max(0)
            center = (mn + mx) / 2.0
            scale = float((mx - mn).max())
            scale = scale if scale > 0 else 1.0
            from mathutils import Matrix, Vector
            T_neg = Matrix.Translation(Vector((-float(center[0]),
                                                  -float(center[1]),
                                                  -float(center[2]))))
            S = Matrix.Scale(1.0 / scale, 4)
            normalize_T = S @ T_neg
            for o in objs:
                if o.world_matrix is not None:
                    o.world_matrix = normalize_T @ o.world_matrix
                else:
                    o.V = ((o.V - center) / scale).astype(np.float32)
            new_center = (0.0, 0.0, 0.0)
            new_diag = float(np.linalg.norm(((mx - mn) / scale)))
        else:
            new_center = tuple(((V_for_bbox.min(0) + V_for_bbox.max(0)) / 2).tolist())
            new_diag = float(np.linalg.norm(V_for_bbox.max(0) - V_for_bbox.min(0)))
        return cls(objects=objs, center=new_center, diag=new_diag,
                    has_parts=has_parts, source=source,
                    normalize_transform=normalize_T)

    def instantiate_with_file_materials(self):
        """Import via bpy importer (keeping OBJ+MTL / GLB / FBX materials).

        Only valid when constructed from from_mesh (source_path set). Applies
        the same normalization as `instantiate_into_blender` would have, but
        via matrix_world so the importer's materials survive.
        """
        if self.source_path is None:
            raise RuntimeError(
                'instantiate_with_file_materials only valid for from_mesh()')
        from . import scene as scene_mod
        objs = scene_mod.import_with_materials(self.source_path)
        if self.normalize_transform is not None:
            for o in objs:
                o.matrix_world = self.normalize_transform @ o.matrix_world
        return objs

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
