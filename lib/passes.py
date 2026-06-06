"""Stage 4: output passes.

A pass is a named slot routed through Blender's Compositor into a
multilayer EXR. Parsing a user-facing string like 'rgb,depth,normal,mask'
yields a normalized list of EXR layer names + the corresponding RenderLayer
sockets + the ViewLayer flags to enable.

User-facing alias:
  'mask' expands to {'alpha', 'indexob'}. When present, the render switches
  to mask-friendly settings (BOX filter, film_transparent, samples=1) — the
  caller should apply those, this module only describes the data shape.

Available:
  rgb       Image socket   (use_pass_combined)
  depth     Depth socket   (use_pass_z)
  normal    Normal socket  (use_pass_normal)
  alpha    (mask)          (use_pass_combined + film_transparent in caller)
  indexob  (mask)          (use_pass_object_index)
"""
import os

# (socket name on RLayers, view-layer flag attribute, channel suffixes)
_PASSES = {
    'rgb':     ('Image',   'use_pass_combined',       ('R', 'G', 'B', 'A')),
    'depth':   ('Depth',   'use_pass_z',              ('V',)),
    'normal':  ('Normal',  'use_pass_normal',         ('X', 'Y', 'Z')),
    'alpha':   ('Alpha',   'use_pass_combined',       ('V',)),
    'indexob': ('IndexOB', 'use_pass_object_index',   ('V',)),
}

ALIASES = {'mask': ('alpha', 'indexob')}


def parse(spec: str):
    """'rgb,depth,mask' -> ordered unique list of canonical pass names."""
    raw = [s.strip() for s in spec.split(',') if s.strip()]
    out = []
    seen = set()
    for name in raw:
        targets = ALIASES.get(name, (name,))
        for t in targets:
            if t not in _PASSES:
                raise ValueError(f'unknown pass: {t}; valid: '
                                  f'{list(_PASSES) + list(ALIASES)}')
            if t not in seen:
                out.append(t)
                seen.add(t)
    return out


def is_mask_render(passes: list) -> bool:
    return any(p in ('alpha', 'indexob') for p in passes)


def has_visual(passes: list) -> bool:
    return any(p in ('rgb', 'depth', 'normal') for p in passes)


def enable_on_view_layer(view_layer, passes: list):
    """Set the view-layer flags so each requested pass is generated."""
    for p in passes:
        _socket, flag, _suffixes = _PASSES[p]
        setattr(view_layer, flag, True)


def setup_compositor_multilayer(out_dir: str, passes: list):
    """Wire RLayers sockets into a multilayer EXR with one slot per pass.

    Resulting file: <out_dir>/0001.exr.
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
    for p in passes:
        socket, _flag, _suf = _PASSES[p]
        if socket not in rl.outputs:
            print(f'[passes] warning: socket {socket} for pass {p} not present')
            continue
        fout.layer_slots.new(p)
        nt.links.new(rl.outputs[socket], fout.inputs[p])
    return fout


def channel_suffixes(pass_name: str):
    """Channel suffixes for reading <pass_name>.<suffix> out of an EXR."""
    return _PASSES[pass_name][2]
