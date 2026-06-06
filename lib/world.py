"""World (background) setup.

Two modes:
  - hdri_env:  Environment Texture node fed from an HDR file. Realistic
    lighting, optional film_transparent so the HDRI doesn't appear in the
    rendered image background.
  - black:     Strength=0 background — for normal/depth aux passes where the
    background should not influence the geometry pass.
"""
import os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENVMAP_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'envmaps'))

DEFAULT_HDRI = os.path.join(ENVMAP_DIR, 'studio.exr')


def set_world_hdri(hdri_path: str = DEFAULT_HDRI, strength: float = 1.0,
                   transparent_bg: bool = True, rotation_deg: float = 0.0):
    """Replace world shader with Environment Texture -> Background.

    transparent_bg: if True (default), the HDRI lights the scene but does NOT
    appear in the rendered image background. Useful when compositing.
    """
    import bpy
    import math
    w = bpy.context.scene.world or bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    coord = nt.nodes.new('ShaderNodeTexCoord')
    mapping = nt.nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.radians(rotation_deg))
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    if not os.path.isfile(hdri_path):
        raise FileNotFoundError(f'HDRI not found: {hdri_path}')
    env.image = bpy.data.images.load(hdri_path, check_existing=True)
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    nt.links.new(mapping.outputs['Vector'], env.inputs['Vector'])
    nt.links.new(env.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    bpy.context.scene.render.film_transparent = transparent_bg


def set_world_black():
    """Strength=0 black background. Geometry passes only."""
    import bpy
    w = bpy.context.scene.world or bpy.data.worlds.new('w')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (0, 0, 0, 1)
    bg.inputs['Strength'].default_value = 0.0
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    bpy.context.scene.render.film_transparent = True


def list_envmaps():
    return sorted(f for f in os.listdir(ENVMAP_DIR) if f.endswith('.exr'))
