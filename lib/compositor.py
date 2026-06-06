"""Compositor: one OPEN_EXR_MULTILAYER per render with named layer_slots.

Pattern from AuroraRyan0301/blender_util:render_utils.py buildMainNodeTree —
write a single multilayer EXR per camera view with named slots {rgb, depth,
normal}, read downstream via OpenEXR python lib by layer name.

Why multilayer: keeps rgb + depth + normal aligned per-pixel in one file,
avoiding multiple-render-pass drift across runs.
"""
import os


def setup_multilayer_exr(out_dir: str, slots=('rgb', 'depth', 'normal')):
    """Configure Compositor to write <out_dir>/0001.exr per render.

    base_path needs a trailing slash so Blender treats it as a directory and
    concatenates frame numbers as filenames inside it. Without the slash,
    Blender concatenates 0001.exr directly onto the path.
    """
    import bpy
    os.makedirs(out_dir, exist_ok=True)
    bpy.context.scene.use_nodes = True
    nt = bpy.context.scene.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new('CompositorNodeRLayers')

    fout = nt.nodes.new('CompositorNodeOutputFile')
    fout.format.file_format = 'OPEN_EXR_MULTILAYER'
    fout.format.exr_codec = 'ZIP'
    fout.format.color_mode = 'RGB'
    fout.format.color_depth = '32'
    fout.base_path = out_dir.rstrip('/') + '/'

    fout.layer_slots.clear()
    for s in slots:
        fout.layer_slots.new(s)
    socket_map = {'rgb': 'Image', 'depth': 'Depth', 'normal': 'Normal',
                  'mist': 'Mist', 'alpha': 'Alpha'}
    for s in slots:
        sock = socket_map.get(s)
        if sock is None or sock not in rl.outputs:
            print(f'[blender_kit] warning: pass {s} not enabled or unknown')
            continue
        nt.links.new(rl.outputs[sock], fout.inputs[s])
    return fout


def setup_mask_multilayer(out_dir: str, with_indexob: bool = True):
    """Mask multilayer EXR. Slots: alpha (silhouette), indexob (per-part).

    alpha:   from RLayers' Alpha socket (needs film_transparent + use_pass_combined)
    indexob: from RLayers' IndexOB socket (needs use_pass_object_index +
             each part's bpy object has pass_index = part_id + 1; 0 = background)

    Downstream: thresholding indexob.V == k yields the binary mask for part
    (k - 1). alpha.V > 0.5 yields the whole-object silhouette.
    """
    import bpy
    os.makedirs(out_dir, exist_ok=True)
    bpy.context.scene.use_nodes = True
    nt = bpy.context.scene.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new('CompositorNodeRLayers')

    fout = nt.nodes.new('CompositorNodeOutputFile')
    fout.format.file_format = 'OPEN_EXR_MULTILAYER'
    fout.format.exr_codec = 'ZIP'
    fout.format.color_mode = 'RGB'
    fout.format.color_depth = '32'
    fout.base_path = out_dir.rstrip('/') + '/'

    fout.layer_slots.clear()
    fout.layer_slots.new('alpha')
    nt.links.new(rl.outputs['Alpha'], fout.inputs['alpha'])
    if with_indexob:
        fout.layer_slots.new('indexob')
        if 'IndexOB' in rl.outputs:
            nt.links.new(rl.outputs['IndexOB'], fout.inputs['indexob'])
        else:
            print('[blender_kit] IndexOB pass not enabled; '
                  'call enable_aux_passes(indexob=True)')
    return fout


def setup_png_output(filepath: str):
    """Plain PNG via render.filepath (no Compositor). For RGB-only Cycles."""
    import bpy
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.image_settings.color_mode = 'RGBA'
    bpy.context.scene.render.filepath = filepath
