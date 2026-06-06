"""Face normal repair + facet-intersection robustness.

recalc_face_normals walks connected components and orients each consistently
outward-pointing (or inward — bmesh picks the larger-volume side). Combined
with mesh.validate(verify=False, clean_customdata=True) this handles most
malformed inputs.
"""


def fix_normals(obj):
    """Recalculate consistent face normals on a mesh object.

    Safe to call on any bpy mesh object. Operates via bmesh on the active mesh.
    """
    import bpy
    import bmesh
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()


def split_doubles(obj, threshold: float = 1e-6):
    """Merge duplicate verts, then split sharp edges. Helps coincident facets.

    Use on raw imports where parts overlap exactly (z-fighting).
    """
    import bmesh
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=threshold)
    bm.to_mesh(me)
    bm.free()
    me.update()


def offset_along_normals(obj, eps: float = 1e-4):
    """Push every vertex along its smoothed normal by `eps`.

    Cheap fix for facets exactly coincident with another part — shrinks/grows
    the shell by a fraction of a percent so the raytracer can disambiguate.
    """
    import bmesh
    import numpy as np
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.co = v.co + v.normal * eps
    bm.to_mesh(me)
    bm.free()
    me.update()
