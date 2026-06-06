"""Stage 2: material selection.

`make_factory(args)` returns a callable `(SceneObject, idx) -> bpy.Material`
that the Scene uses when it instantiates each object.

Material modes:
  diffuse      Principled BSDF, uniform color
  two_sided    backface-flipped diffuse, opaque
  tab20        per-part categorical color (uses idx)
  pbr          Poly Haven / ambientCG style folder; one material reused
  uv_color     emission (U, V, 0)
  uv_checker   procedural checker on UV
  embedded     for URDF: use URDF-declared per-object <material><color>
  mask         flat grey diffuse (passes carry the mask info, not the material)
"""
from . import materials


_NAMES = ('diffuse', 'two_sided', 'tab20', 'pbr', 'uv_color', 'uv_checker',
          'embedded', 'file_embedded', 'mask')


NAMES = _NAMES


def make_factory(args):
    """Dispatch on args.material. Returns callable(SceneObject, idx) -> Material."""
    m = args.material
    if m == 'diffuse':
        rgba = (*args.color, 1.0)
        return lambda o, i: materials.diffuse_realistic(
            f'mat_{i}', rgba, roughness=args.roughness, metallic=args.metallic)
    if m == 'two_sided':
        rgba = (*args.color, 1.0)
        return lambda o, i: materials.two_sided_diffuse(f'mat_{i}', rgba)
    if m == 'tab20':
        # Plain single-sided Diffuse: relies on Cycles' internal shading-normal
        # auto-flip for back-hits. The two_sided_diffuse wrapper was found to
        # break on single-shell dual-contoured meshes (microscope test 2026-06).
        # Color index = part_id (NOT enumeration index) so a part keeps the
        # same color regardless of --select_parts subsetting.
        return lambda o, i: materials.tab20_flat(
            f'mat_p{o.part_id}', o.part_id, two_sided=False)
    if m == 'pbr':
        # Build once, reuse for all objects.
        cached = None

        def _factory(o, i, _cached=[None]):
            if _cached[0] is None:
                mat, detected = materials.load_pbr_pack(
                    'pbr_mat', args.pbr_dir,
                    uv_scale=tuple(args.uv_scale),
                    normal_strength=args.normal_strength,
                    displacement_scale=args.displacement_scale)
                if i == 0:
                    print(f'[material:pbr] detected: {list(detected)}')
                _cached[0] = mat
            return _cached[0]
        return _factory
    if m == 'uv_color':
        return lambda o, i: materials.uv_color_emission(f'mat_{i}')
    if m == 'uv_checker':
        return lambda o, i: materials.uv_checker(f'mat_{i}', scale=args.checker_scale)
    if m == 'mask':
        return lambda o, i: materials.diffuse_realistic(
            f'mat_{i}', (0.8, 0.8, 0.8, 1.0))
    if m == 'file_embedded':
        # Sentinel — render.py must take the bpy-import path
        # (Scene.instantiate_with_file_materials) instead of calling this.
        return None
    if m == 'embedded':
        # URDF colors live on each SceneObject; materials.diffuse_realistic
        # builds a per-object material from the declared rgba.
        def _factory(o, i):
            rgba = o.color or (0.7, 0.7, 0.7, 1.0)
            return materials.diffuse_realistic(f'mat_{i}', tuple(rgba),
                                                 roughness=0.6)
        return _factory
    raise ValueError(f'unknown material: {m}; valid: {_NAMES}')
