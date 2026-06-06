"""High-level scene-building helpers — sit between lib/ primitives and scripts/.

add_mesh_from_arrays:  one numpy mesh -> Blender mesh object with material.
clear_scene:           wipe all data-blocks (use between views in a multi-view
                       render so RAM doesn't blow up after 8+ renders).
"""
import numpy as np


def clear_scene():
    """Delete everything — objects and orphan datablocks."""
    import bpy
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for c in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
              bpy.data.cameras, bpy.data.images):
        for it in list(c):
            try:
                c.remove(it)
            except RuntimeError:
                pass


def add_mesh_from_arrays(name: str, V: np.ndarray, F: np.ndarray, mat=None,
                          smooth: bool = False):
    """Build a Blender mesh from (Nv,3) verts + (Nf,3) tri faces.

    V should already be in Blender Z-up frame. Call coord.obj_to_blender_pts
    on raw OBJ data before passing here.
    """
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(V.tolist(), [], F.tolist())
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    mesh.validate(verbose=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    return obj


def import_with_materials(path: str):
    """Import obj/glb/gltf/fbx via bpy and KEEP whatever materials the importer
    creates (OBJ+MTL textures, GLB embedded textures, FBX materials).

    Returns the list of imported mesh objects. Use this instead of
    add_mesh_from_arrays when you want the file's own materials applied.
    """
    from . import mesh_io
    return mesh_io.load_mesh_blender(path)


def world_aabb(objs):
    """(center, diag) over world-space bbox of every vertex in every obj."""
    import bpy
    from mathutils import Vector
    mn = Vector((float('inf'),) * 3)
    mx = Vector((float('-inf'),) * 3)
    for obj in objs:
        mw = obj.matrix_world
        for v in obj.data.vertices:
            p = mw @ v.co
            for i in range(3):
                if p[i] < mn[i]:
                    mn[i] = p[i]
                if p[i] > mx[i]:
                    mx[i] = p[i]
    center = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2)
    diag = float(((mx[0] - mn[0]) ** 2 + (mx[1] - mn[1]) ** 2 +
                  (mx[2] - mn[2]) ** 2) ** 0.5)
    return center, diag


def split_by_part_id(V: np.ndarray, F: np.ndarray, face_ids: np.ndarray):
    """Yield (part_id, V_sub, F_sub_local) for each unique part_id >= 0.

    V_sub / F_sub_local are dense and locally indexed — feed directly to
    add_mesh_from_arrays per part.
    """
    parts = sorted(int(x) for x in np.unique(face_ids) if int(x) >= 0)
    for k in parts:
        mask = face_ids == k
        sub_f = F[mask]
        if sub_f.shape[0] == 0:
            continue
        used = np.unique(sub_f.flatten())
        vmap = -np.ones(V.shape[0], dtype=np.int64)
        vmap[used] = np.arange(len(used))
        yield k, V[used], vmap[sub_f]
