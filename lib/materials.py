"""Material builders.

Flavors:
  - diffuse_realistic / two_sided_diffuse / tab20_flat (simple shaders)
  - principled_textured: Principled BSDF + per-slot image textures
  - load_pbr_pack: auto-detect Poly Haven / ambientCG style folders
  - uv_color_emission / uv_checker: UV visualization shaders

PBR map conventions recognized by load_pbr_pack:
  base_color   *diff* / *color* / *basecolor* / *albedo*   sRGB
  roughness    *rough* / *roughness*                       Non-Color
  normal       *nor_gl* / *normal_gl* / *normal*           Non-Color (OpenGL)
  metallic     *metal* / *metalness*                       Non-Color
  ao           *ao* / *ambientocclusion*                   Non-Color
  displacement *disp* / *displacement* / *height*          Non-Color

Free CC0 packs: https://polyhaven.com/textures , https://ambientcg.com/
"""
import os

# matplotlib tab20 (20 distinct categorical colors), linear RGB.
TAB20 = [
    (0.121569, 0.466667, 0.705882),
    (0.682353, 0.780392, 0.909804),
    (1.000000, 0.498039, 0.054902),
    (1.000000, 0.733333, 0.470588),
    (0.172549, 0.627451, 0.172549),
    (0.596078, 0.874510, 0.541176),
    (0.839216, 0.152941, 0.156863),
    (1.000000, 0.596078, 0.588235),
    (0.580392, 0.403922, 0.741176),
    (0.772549, 0.690196, 0.835294),
    (0.549020, 0.337255, 0.294118),
    (0.768627, 0.611765, 0.580392),
    (0.890196, 0.466667, 0.760784),
    (0.968627, 0.713725, 0.823529),
    (0.498039, 0.498039, 0.498039),
    (0.780392, 0.780392, 0.780392),
    (0.737255, 0.741176, 0.133333),
    (0.858824, 0.858824, 0.552941),
    (0.090196, 0.745098, 0.811765),
    (0.619608, 0.854902, 0.898039),
]


def tab20_color(idx: int):
    """RGBA tuple at index idx (mod 20). Linear-RGB space."""
    r, g, b = TAB20[idx % len(TAB20)]
    return (r, g, b, 1.0)


def diffuse_realistic(name: str, color=(0.8, 0.8, 0.8, 1.0),
                       roughness: float = 0.5, metallic: float = 0.0):
    """Principled BSDF — pleasant default for dataset renders."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def two_sided_diffuse(name: str, color=(0.8, 0.8, 0.8, 1.0)):
    """Diffuse that responds correctly to light from either face side.

    Backfacing -> swap to a Diffuse shader with reversed Normal. Outer surfaces
    of an opaque mesh render correctly under env-only lighting; closed
    cavities still come out black because light can't reach them.
    """
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    front = nt.nodes.new('ShaderNodeBsdfDiffuse')
    front.inputs['Color'].default_value = color
    back = nt.nodes.new('ShaderNodeBsdfDiffuse')
    back.inputs['Color'].default_value = color
    geom = nt.nodes.new('ShaderNodeNewGeometry')
    inv = nt.nodes.new('ShaderNodeVectorMath')
    inv.operation = 'SCALE'
    inv.inputs[3].default_value = -1.0
    nt.links.new(geom.outputs['Normal'], inv.inputs[0])
    nt.links.new(inv.outputs['Vector'], back.inputs['Normal'])
    bf = nt.nodes.new('ShaderNodeNewGeometry')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(bf.outputs['Backfacing'], mix.inputs['Fac'])
    nt.links.new(front.outputs['BSDF'], mix.inputs[1])
    nt.links.new(back.outputs['BSDF'], mix.inputs[2])
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    return mat


def tab20_flat(name: str, idx: int, two_sided: bool = True):
    """Flat tab20 diffuse for part visualization."""
    if two_sided:
        return two_sided_diffuse(name, tab20_color(idx))
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    diff = nt.nodes.new('ShaderNodeBsdfDiffuse')
    diff.inputs['Color'].default_value = tab20_color(idx)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(diff.outputs['BSDF'], out.inputs['Surface'])
    return mat


def assign_material(obj, mat):
    """Replace all materials on obj with mat."""
    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ---------------------------------------------------------------------------
# Textured Principled BSDF
# ---------------------------------------------------------------------------

_PBR_KEYS = {
    'base_color':   ('diff', 'color', 'basecolor', 'albedo'),
    'roughness':    ('rough', 'roughness'),
    'normal':       ('nor_gl', 'normal_gl', 'normalgl', 'nor_dx', 'normal',
                      'norm'),
    'metallic':     ('metal', 'metalness'),
    'ao':           ('ao', 'ambientocclusion', 'ambient_occlusion'),
    'displacement': ('disp', 'displacement', 'height'),
}

_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff', '.tga', '.bmp')


def _detect_pbr_maps(folder: str) -> dict:
    """Return {slot: absolute_path} for files matching the PBR conventions.

    Substring matched case-insensitively against the basename. First hit wins
    in the key-tuple order, so prefer specific patterns (`nor_gl` before
    `normal`).
    """
    if not os.path.isdir(folder):
        raise NotADirectoryError(folder)
    files = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
             if f.lower().endswith(_IMAGE_EXTS)]
    found = {}
    for slot, patterns in _PBR_KEYS.items():
        for pat in patterns:
            for f in files:
                base = os.path.basename(f).lower()
                if pat in base:
                    found[slot] = f
                    break
            if slot in found:
                break
    return found


def principled_textured(name: str, *,
                          base_color=(0.8, 0.8, 0.8, 1.0),
                          base_color_map: str = None,
                          roughness: float = 0.5,
                          roughness_map: str = None,
                          normal_map: str = None,
                          normal_strength: float = 1.0,
                          metallic: float = 0.0,
                          metallic_map: str = None,
                          ao_map: str = None,
                          displacement_map: str = None,
                          displacement_scale: float = 0.05,
                          uv_scale=(1.0, 1.0)):
    """Principled BSDF with optional image textures wired into each slot.

    Color spaces are set automatically: base_color/ao -> sRGB, everything else
    -> Non-Color. AO is multiplied into the base color (or used standalone if
    no base_color_map is provided).

    Displacement uses Cycles bump-only displacement by default; for true
    geometry displacement, enable adaptive subdivision on the object and set
    mat.cycles.displacement_method = 'BOTH'.
    """
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    out = nt.nodes.new('ShaderNodeOutputMaterial')

    tc = nt.nodes.new('ShaderNodeTexCoord')
    mapping = nt.nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (uv_scale[0], uv_scale[1], 1.0)
    nt.links.new(tc.outputs['UV'], mapping.inputs['Vector'])

    def _img_node(path: str, colorspace: str = 'Non-Color'):
        node = nt.nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(path, check_existing=True)
        try:
            node.image.colorspace_settings.name = colorspace
        except Exception:
            pass
        nt.links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    base_color_socket = None
    if base_color_map:
        n = _img_node(base_color_map, 'sRGB')
        base_color_socket = n.outputs['Color']
    if ao_map:
        n_ao = _img_node(ao_map, 'Non-Color')
        if base_color_socket is not None:
            mix = nt.nodes.new('ShaderNodeMixRGB')
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Fac'].default_value = 1.0
            nt.links.new(base_color_socket, mix.inputs['Color1'])
            nt.links.new(n_ao.outputs['Color'], mix.inputs['Color2'])
            base_color_socket = mix.outputs['Color']
        else:
            base_color_socket = n_ao.outputs['Color']
    if base_color_socket is not None:
        nt.links.new(base_color_socket, bsdf.inputs['Base Color'])
    else:
        bsdf.inputs['Base Color'].default_value = base_color

    if roughness_map:
        n = _img_node(roughness_map, 'Non-Color')
        nt.links.new(n.outputs['Color'], bsdf.inputs['Roughness'])
    else:
        bsdf.inputs['Roughness'].default_value = roughness

    if metallic_map:
        n = _img_node(metallic_map, 'Non-Color')
        nt.links.new(n.outputs['Color'], bsdf.inputs['Metallic'])
    else:
        bsdf.inputs['Metallic'].default_value = metallic

    if normal_map:
        n = _img_node(normal_map, 'Non-Color')
        nrm = nt.nodes.new('ShaderNodeNormalMap')
        nrm.inputs['Strength'].default_value = normal_strength
        nt.links.new(n.outputs['Color'], nrm.inputs['Color'])
        nt.links.new(nrm.outputs['Normal'], bsdf.inputs['Normal'])

    if displacement_map:
        n = _img_node(displacement_map, 'Non-Color')
        disp = nt.nodes.new('ShaderNodeDisplacement')
        disp.inputs['Scale'].default_value = displacement_scale
        nt.links.new(n.outputs['Color'], disp.inputs['Height'])
        nt.links.new(disp.outputs['Displacement'], out.inputs['Displacement'])

    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def load_pbr_pack(name: str, folder: str, uv_scale=(1.0, 1.0),
                   normal_strength: float = 1.0,
                   displacement_scale: float = 0.05):
    """Auto-detect a Poly Haven / ambientCG style folder and build a Principled BSDF.

    Returns (material, detected_map_dict). Empty dict on no matches.
    """
    maps = _detect_pbr_maps(folder)
    if not maps:
        print(f'[blender_kit] no PBR maps detected in {folder}')
    return principled_textured(
        name,
        base_color_map=maps.get('base_color'),
        roughness_map=maps.get('roughness'),
        normal_map=maps.get('normal'),
        metallic_map=maps.get('metallic'),
        ao_map=maps.get('ao'),
        displacement_map=maps.get('displacement'),
        uv_scale=uv_scale,
        normal_strength=normal_strength,
        displacement_scale=displacement_scale,
    ), maps


# ---------------------------------------------------------------------------
# UV visualization shaders
# ---------------------------------------------------------------------------

def uv_color_emission(name: str):
    """Emission shader: outputs (U, V, 0) so UV values bake into image color.

    Visualizes per-fragment UVs directly on the mesh surface. Faces that share
    UV coordinates render the same color; large gradient discontinuities show
    UV seams.
    """
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    com = nt.nodes.new('ShaderNodeCombineRGB')
    em = nt.nodes.new('ShaderNodeEmission')
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em.inputs['Strength'].default_value = 1.0
    nt.links.new(tc.outputs['UV'], sep.inputs['Vector'])
    nt.links.new(sep.outputs['X'], com.inputs['R'])
    nt.links.new(sep.outputs['Y'], com.inputs['G'])
    nt.links.new(com.outputs['Image'], em.inputs['Color'])
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return mat


def uv_checker(name: str, scale: float = 10.0, roughness: float = 0.6):
    """Principled BSDF with a procedural checker, UV-mapped.

    Cheap stretching/distortion visualizer — the checker squares look square
    where UVs are well-parametrized and skewed/stretched otherwise.
    """
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mapping = nt.nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (scale, scale, scale)
    checker = nt.nodes.new('ShaderNodeTexChecker')
    checker.inputs['Color1'].default_value = (0.95, 0.95, 0.95, 1.0)
    checker.inputs['Color2'].default_value = (0.10, 0.10, 0.10, 1.0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = roughness
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(tc.outputs['UV'], mapping.inputs['Vector'])
    nt.links.new(mapping.outputs['Vector'], checker.inputs['Vector'])
    nt.links.new(checker.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat
