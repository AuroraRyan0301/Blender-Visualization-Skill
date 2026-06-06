"""Multi-format mesh IO: .obj / .ply / .glb / .gltf / .stl / .fbx / .off.

Two layers:

  load_mesh_blender(path, source_frame='auto')
      Import via bpy. Returns the imported bpy mesh object(s) — vertices stay
      in Blender Z-up frame because each importer handles its own axis swap.
      Use inside scripts that already have bpy available.

  load_mesh_arrays(path, source_frame='auto')
      Pure-numpy load. Returns (V, F) in Blender Z-up frame, regardless of
      the file's native frame. Uses the manual .obj parser for OBJ (preserves
      face order — important when face_ids.npy is index-aligned to the file).
      Other formats fall back to bpy (must run inside Blender).

Per-format native frame (what the file itself stores):
  obj   -> Y-up,  -Z forward      (Wavefront convention)
  gltf/glb -> Y-up, +Z forward    (glTF 2.0 spec)
  ply, stl, off -> no spec; usually Z-up
  fbx   -> Y-up                   (default; metadata can override)

We rotate Y-up -> Z-up by  (x, y, z) -> (x, -z, y).  Z-up sources pass through.
"""
import os
import numpy as np

from . import coord

_YUP_EXT = {'.obj', '.glb', '.gltf', '.fbx'}
_ZUP_EXT = {'.ply', '.stl', '.off'}


def _native_frame(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _YUP_EXT:
        return 'y_up'
    if ext in _ZUP_EXT:
        return 'z_up'
    raise ValueError(f'unknown mesh format: {ext}')


def _to_blender(V: np.ndarray, source_frame: str) -> np.ndarray:
    if source_frame == 'y_up':
        return coord.obj_to_blender_pts(V)
    if source_frame == 'z_up':
        return V.astype(np.float32)
    raise ValueError(f'unknown source_frame: {source_frame}')


def _from_blender(V: np.ndarray, target_frame: str) -> np.ndarray:
    if target_frame == 'y_up':
        return coord.blender_to_obj_pts(V)
    if target_frame == 'z_up':
        return V.astype(np.float32)
    raise ValueError(f'unknown target_frame: {target_frame}')


def load_obj(path: str):
    """Fast manual OBJ parser. Returns (V, F) in OBJ's native Y-up frame.

    Preserves vertex and face order — required when face_ids.npy is aligned
    to the file's face count. Triangulates polygon faces.
    """
    verts, faces = [], []
    with open(path) as fh:
        for ln in fh:
            if ln.startswith('v '):
                verts.append([float(x) for x in ln.split()[1:4]])
            elif ln.startswith('f '):
                idx = [int(t.split('/')[0]) - 1 for t in ln.split()[1:]]
                for i in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[i], idx[i + 1]])
    return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.int64)


def save_obj(path: str, V: np.ndarray, F: np.ndarray) -> None:
    """V should already be in Y-up frame. Caller responsible for the swap."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'w') as fh:
        for v in V:
            fh.write(f'v {v[0]} {v[1]} {v[2]}\n')
        for f in F:
            fh.write(f'f {f[0] + 1} {f[1] + 1} {f[2] + 1}\n')


def load_mesh_arrays(path: str, source_frame: str = 'auto'):
    """Return (V, F) in Blender Z-up frame.

    source_frame='auto' (default) uses the per-extension default. Override
    with 'y_up' / 'z_up' if a particular PLY/STL violates convention.
    """
    if source_frame == 'auto':
        source_frame = _native_frame(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == '.obj':
        V_native, F = load_obj(path)
        return _to_blender(V_native, source_frame), F
    return _load_via_bpy_arrays(path, source_frame)


def _load_via_bpy_arrays(path: str, source_frame: str):
    """Import non-OBJ via bpy, extract V,F from the merged result."""
    import bpy
    objs = load_mesh_blender(path, source_frame=source_frame)
    V_all, F_all, offset = [], [], 0
    for obj in objs:
        me = obj.data
        me.calc_loop_triangles()
        mw = obj.matrix_world
        V = np.array([mw @ v.co for v in me.vertices], dtype=np.float32)
        F = np.array([[t.vertices[0], t.vertices[1], t.vertices[2]]
                       for t in me.loop_triangles], dtype=np.int64) + offset
        V_all.append(V)
        F_all.append(F)
        offset += V.shape[0]
    if not V_all:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64)
    return np.concatenate(V_all, axis=0), np.concatenate(F_all, axis=0)


def load_mesh_blender(path: str, source_frame: str = 'auto'):
    """Import any supported format via bpy. Returns list of MESH objects.

    Importer is chosen by extension. Each importer is configured so the
    imported geometry ends up in Blender Z-up world frame (default for
    glb/obj/fbx; ply/stl get rotated manually if source_frame='y_up').
    """
    import bpy
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext == '.obj':
        if hasattr(bpy.ops.wm, 'obj_import'):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.ply':
        if hasattr(bpy.ops.wm, 'ply_import'):
            bpy.ops.wm.ply_import(filepath=path)
        else:
            bpy.ops.import_mesh.ply(filepath=path)
    elif ext == '.stl':
        if hasattr(bpy.ops.wm, 'stl_import'):
            bpy.ops.wm.stl_import(filepath=path)
        else:
            bpy.ops.import_mesh.stl(filepath=path)
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.off':
        raise NotImplementedError('OFF: load with load_mesh_arrays (manual)')
    else:
        raise ValueError(f'unsupported extension: {ext}')
    new_objs = [o for o in bpy.data.objects
                if o not in before and o.type == 'MESH']

    # For formats where the importer doesn't apply the axis swap, do it now.
    if source_frame == 'auto':
        source_frame = _native_frame(path)
    importer_handles_swap = ext in ('.obj', '.glb', '.gltf', '.fbx')
    if not importer_handles_swap and source_frame == 'y_up':
        import math
        from mathutils import Matrix
        R = Matrix.Rotation(math.radians(90.0), 4, 'X')
        for o in new_objs:
            o.matrix_world = R @ o.matrix_world
    return new_objs


def save_mesh_arrays(path: str, V: np.ndarray, F: np.ndarray,
                      target_frame: str = 'auto') -> None:
    """V is in Blender Z-up; converted to the file format's native frame.

    Implemented for OBJ via the manual writer. Other formats route through
    bpy (must run inside Blender) using a temporary mesh.
    """
    if target_frame == 'auto':
        target_frame = _native_frame(path)
    V_native = _from_blender(V, target_frame)
    ext = os.path.splitext(path)[1].lower()
    if ext == '.obj':
        save_obj(path, V_native, F)
        return
    _save_via_bpy(path, V, F)  # bpy exporter handles its own swap


def _save_via_bpy(path: str, V: np.ndarray, F: np.ndarray):
    import bpy
    ext = os.path.splitext(path)[1].lower()
    mesh = bpy.data.meshes.new('_export_tmp')
    mesh.from_pydata(V.tolist(), [], F.tolist())
    mesh.update()
    obj = bpy.data.objects.new('_export_tmp', mesh)
    bpy.context.collection.objects.link(obj)
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    if ext in ('.glb', '.gltf'):
        bpy.ops.export_scene.gltf(filepath=path, use_selection=True,
                                    export_format='GLB' if ext == '.glb' else 'GLTF_EMBEDDED')
    elif ext == '.ply':
        if hasattr(bpy.ops.wm, 'ply_export'):
            bpy.ops.wm.ply_export(filepath=path, export_selected_objects=True)
        else:
            bpy.ops.export_mesh.ply(filepath=path, use_selection=True)
    elif ext == '.stl':
        if hasattr(bpy.ops.wm, 'stl_export'):
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True)
        else:
            bpy.ops.export_mesh.stl(filepath=path, use_selection=True)
    elif ext == '.fbx':
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True)
    else:
        raise ValueError(f'unsupported export extension: {ext}')
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh, do_unlink=True)


def convert(in_path: str, out_path: str,
            source_frame: str = 'auto', target_frame: str = 'auto') -> None:
    """Format-to-format conversion with correct axis handling."""
    V, F = load_mesh_arrays(in_path, source_frame=source_frame)
    save_mesh_arrays(out_path, V, F, target_frame=target_frame)
