"""UV helpers: ensure-UV / auto-unwrap / 2D layout export.

Blender's `bpy.ops.uv.export_layout` needs an Image Editor context which isn't
available in headless mode. We extract UVs from mesh data and draw the islands
with matplotlib instead — produces the same overview without GUI dependencies.
"""
import os


def has_uvs(obj) -> bool:
    return bool(obj.data.uv_layers)


def smart_unwrap(obj, angle_limit: float = 66.0,
                  island_margin: float = 0.02):
    """Smart-project unwrap. Adds a UV layer if missing."""
    import bpy
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name='UVMap')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=angle_limit,
                              island_margin=island_margin)
    bpy.ops.object.mode_set(mode='OBJECT')


def ensure_uvs(obj, auto_unwrap_if_missing: bool = True):
    """If the mesh has no UV layer, run smart_unwrap. Otherwise no-op."""
    if has_uvs(obj):
        return
    if auto_unwrap_if_missing:
        smart_unwrap(obj)


def extract_uv_polys(obj):
    """Return [[(u,v), ...], ...] — one list per polygon, in mesh-face order.

    Empty list if the object has no UV layer.
    """
    me = obj.data
    if not me.uv_layers:
        return []
    uv_data = me.uv_layers.active.data
    polys = []
    for poly in me.polygons:
        verts = [(uv_data[li].uv[0], uv_data[li].uv[1])
                 for li in poly.loop_indices]
        polys.append(verts)
    return polys


def export_uv_layout_png(obj, out_path: str, size: int = 1024,
                          line_width: float = 0.4,
                          show_unit_square: bool = True) -> str:
    """Render the 2D UV layout as a PNG via matplotlib.

    Uses mesh data directly — works in headless Blender. Returns the written
    path, or None if the object has no UV layer.
    """
    polys = extract_uv_polys(obj)
    if not polys:
        return None
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fig, ax = plt.subplots(figsize=(size / 100, size / 100), dpi=100)
    pc = PolyCollection(polys, facecolors='none', edgecolors='black',
                         linewidths=line_width)
    ax.add_collection(pc)
    if show_unit_square:
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False, edgecolor='red',
                                    linewidth=1.0))
    pad = 0.05
    ax.set_xlim(-pad, 1 + pad)
    # Flip Y so the result matches Blender's UV editor (origin at top-left
    # when imagining the 0..1 unit tile as a texture).
    ax.set_ylim(1 + pad, -pad)
    ax.set_aspect('equal')
    ax.set_title(f'UV layout ({len(polys)} faces)', fontsize=10)
    ax.set_xlabel('U'); ax.set_ylabel('V')
    fig.savefig(out_path, dpi=100, bbox_inches='tight')
    plt.close(fig)
    return out_path
