"""URDF parser + Blender loader.

Supports the rest-pose visual geometry only:
  <link><visual><geometry>{<mesh filename="..." scale="..."/>, <box/>, <cylinder/>, <sphere/>}
  <link><visual><origin xyz="..." rpy="..."/>
  <link><visual><material><color rgba="..."/>
  <joint><parent/><child/><origin xyz rpy/>

Mesh filename resolution:
  package://pkg/path   -> mesh_root / path  (pkg segment stripped)
  file:///abs/path     -> /abs/path
  /abs/path            -> /abs/path
  rel/path             -> urdf_dir / rel/path

URDF / ROS convention is Z-up + X-forward (REP-103), same as Blender. Mesh
files referenced by a URDF are treated as already-in-link-frame, so OBJ
files do NOT get the usual Y-up rotation. Pass --source_frame y_up on the
command line if a specific URDF violates this.
"""
import os
import xml.etree.ElementTree as ET


def _parse_origin(elem):
    xyz = (0.0, 0.0, 0.0)
    rpy = (0.0, 0.0, 0.0)
    if elem is None:
        return xyz, rpy
    if 'xyz' in elem.attrib:
        xyz = tuple(float(x) for x in elem.attrib['xyz'].split())
    if 'rpy' in elem.attrib:
        rpy = tuple(float(x) for x in elem.attrib['rpy'].split())
    return xyz, rpy


def parse_urdf(path: str) -> dict:
    """Return {root, links: {name: {visuals: [...]}}, joints: [...], urdf_dir}."""
    tree = ET.parse(path)
    root_xml = tree.getroot()
    links = {}
    for link in root_xml.findall('link'):
        name = link.get('name')
        visuals = []
        for vis in link.findall('visual'):
            geom = vis.find('geometry')
            shape = _parse_shape(geom)
            mat = vis.find('material')
            color = None
            if mat is not None:
                c = mat.find('color')
                if c is not None and 'rgba' in c.attrib:
                    color = tuple(float(x) for x in c.attrib['rgba'].split())
            visuals.append({'origin': _parse_origin(vis.find('origin')),
                             'shape': shape, 'color': color})
        links[name] = {'name': name, 'visuals': visuals}
    joints = []
    children = set()
    for j in root_xml.findall('joint'):
        parent = j.find('parent')
        child = j.find('child')
        if parent is None or child is None:
            continue
        joints.append({
            'name': j.get('name'),
            'parent': parent.get('link'),
            'child': child.get('link'),
            'type': j.get('type', 'fixed'),
            'origin': _parse_origin(j.find('origin')),
        })
        children.add(child.get('link'))
    root_link = next((n for n in links if n not in children), None)
    return {'root': root_link, 'links': links, 'joints': joints,
            'urdf_dir': os.path.dirname(os.path.abspath(path))}


def _parse_shape(geom_elem):
    if geom_elem is None:
        return None
    m = geom_elem.find('mesh')
    if m is not None:
        scale = tuple(float(x) for x in m.get('scale', '1 1 1').split())
        return ('mesh', m.get('filename'), scale)
    b = geom_elem.find('box')
    if b is not None:
        return ('box', tuple(float(x) for x in b.get('size', '1 1 1').split()))
    c = geom_elem.find('cylinder')
    if c is not None:
        return ('cylinder', float(c.get('radius', '0.5')),
                 float(c.get('length', '1.0')))
    s = geom_elem.find('sphere')
    if s is not None:
        return ('sphere', float(s.get('radius', '0.5')))
    return None


def resolve_mesh_filename(filename: str, urdf_dir: str,
                            mesh_root: str = None) -> str:
    if filename.startswith('package://'):
        path = filename[len('package://'):]
        if '/' in path:
            _, rel = path.split('/', 1)
        else:
            rel = path
        base = mesh_root if (mesh_root and os.path.isabs(mesh_root)) else urdf_dir
        return os.path.join(base, rel)
    if filename.startswith('file://'):
        return filename[len('file://'):]
    if os.path.isabs(filename):
        return filename
    return os.path.join(urdf_dir, filename)


def compute_link_transforms(robot: dict) -> dict:
    """BFS from root, return {link_name: world Matrix4}. Rest pose only."""
    from mathutils import Matrix, Euler, Vector
    out = {robot['root']: Matrix.Identity(4)}
    by_parent = {}
    for j in robot['joints']:
        by_parent.setdefault(j['parent'], []).append(j)
    queue = [robot['root']]
    while queue:
        parent = queue.pop(0)
        for j in by_parent.get(parent, []):
            xyz, rpy = j['origin']
            T = Matrix.Translation(Vector(xyz)) @ \
                Euler(rpy, 'XYZ').to_matrix().to_4x4()
            out[j['child']] = out[parent] @ T
            queue.append(j['child'])
    return out


def load_into_blender(urdf_path: str, mesh_root: str = None,
                       default_color=(0.7, 0.7, 0.7, 1.0)) -> list:
    """Parse URDF and add all visual geometry into the current scene.

    Returns the list of created bpy mesh objects in world frame, with
    URDF-specified colors / default Principled BSDF.
    """
    import bpy
    from mathutils import Matrix, Euler, Vector
    from . import materials

    robot = parse_urdf(urdf_path)
    link_T = compute_link_transforms(robot)
    new_objs = []
    for link_name, link in robot['links'].items():
        if link_name not in link_T:
            continue  # disconnected island
        for vi, visual in enumerate(link['visuals']):
            shape = visual['shape']
            if shape is None:
                continue
            xyz, rpy = visual['origin']
            local_T = Matrix.Translation(Vector(xyz)) @ \
                       Euler(rpy, 'XYZ').to_matrix().to_4x4()
            world_T = link_T[link_name] @ local_T

            objs = _spawn(shape, robot['urdf_dir'], mesh_root)
            for o in objs:
                if shape[0] == 'mesh':
                    sx, sy, sz = shape[2]
                    o.matrix_world = world_T @ Matrix.Diagonal((sx, sy, sz, 1.0))
                else:
                    o.matrix_world = world_T
                o.name = f'{link_name}_v{vi}'
                rgba = visual['color'] or default_color
                mat = materials.diffuse_realistic(f'mat_{o.name}', tuple(rgba),
                                                   roughness=0.6)
                o.data.materials.clear()
                o.data.materials.append(mat)
                new_objs.append(o)
    return new_objs


def _spawn(shape, urdf_dir, mesh_root):
    """Spawn primitive geometry as Blender objects. Returns list of objects."""
    import bpy
    kind = shape[0]
    if kind == 'mesh':
        from . import mesh_io
        path = resolve_mesh_filename(shape[1], urdf_dir, mesh_root)
        # URDF stores meshes already in link frame (Z-up). Don't apply Y-up swap.
        # For OBJ specifically, raw-parse + add directly to avoid auto rotation.
        ext = os.path.splitext(path)[1].lower()
        if ext == '.obj':
            import numpy as np
            from . import scene as scene_mod
            V, F = mesh_io.load_obj(path)
            obj = scene_mod.add_mesh_from_arrays(os.path.basename(path), V, F)
            return [obj]
        return mesh_io.load_mesh_blender(path, source_frame='z_up')
    if kind == 'box':
        sx, sy, sz = shape[1]
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        o = bpy.context.active_object
        o.scale = (sx / 2, sy / 2, sz / 2)
        bpy.ops.object.transform_apply(scale=True)
        return [o]
    if kind == 'cylinder':
        r, length = shape[1], shape[2]
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=length)
        return [bpy.context.active_object]
    if kind == 'sphere':
        r = shape[1]
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r)
        return [bpy.context.active_object]
    return []
