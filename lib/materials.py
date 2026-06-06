"""Material builders.

Three flavors:
  - diffuse_realistic:  Principled BSDF, roughness 0.5, faint specular. Used
    for dataset-style renders against an HDRI.
  - two_sided_diffuse:  Backfacing → flipped-normal Diffuse mix. Use for thin
    shells or meshes whose facet winding isn't trustable. NOTE: closed cavities
    will still come out RGB=0 — that's physically correct, not a bug.
  - tab20:              matplotlib tab20 categorical palette, flat Diffuse.
    For per-part part-id visualization.
"""

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
