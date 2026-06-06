"""Render engine + device + sampling setup.

GPU-only by policy: if no CUDA/OPTIX device is found, setup raises
RuntimeError. CPU fallback is explicitly disabled — this skill prohibits CPU
rendering. Workbench is also forbidden; everything goes through Cycles.
"""


class NoGPUError(RuntimeError):
    pass


def setup_cycles(samples: int = 64, resolution: int = 1024,
                 denoise: bool = True, max_bounces: int = 12,
                 tile_size: int = 2048):
    """Configure scene.render + scene.cycles for a render. GPU-only.

    samples=64 is the cheap dataset default. 128-256 for hero renders.
    max_bounces=12 generous; drop to 6 for simple scenes.
    """
    import bpy
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    s.cycles.samples = samples
    s.render.resolution_x = resolution
    s.render.resolution_y = resolution
    s.render.resolution_percentage = 100
    s.cycles.max_bounces = max_bounces
    s.cycles.diffuse_bounces = max_bounces
    s.cycles.glossy_bounces = max_bounces
    s.cycles.transparent_max_bounces = max_bounces
    s.cycles.transmission_bounces = max_bounces

    prefs = bpy.context.preferences.addons['cycles'].preferences
    has_optix = any(d.type == 'OPTIX' for d in prefs.devices) or \
        _try_compute_device_type(prefs, 'OPTIX')
    if not has_optix:
        _try_compute_device_type(prefs, 'CUDA')
    prefs.get_devices()
    gpu_devs = [d for d in prefs.devices if d.type in ('OPTIX', 'CUDA')]
    if not gpu_devs:
        raise NoGPUError(
            'no CUDA/OPTIX GPU detected. This skill prohibits CPU rendering. '
            'ssh to a node_q/node_f node before invoking.')
    for d in prefs.devices:
        d.use = (d.type in ('OPTIX', 'CUDA'))
    s.cycles.device = 'GPU'

    if denoise:
        s.cycles.use_denoising = True
        try:
            s.cycles.denoiser = 'OPTIX' if any(d.type == 'OPTIX' for d in gpu_devs) \
                else 'OPENIMAGEDENOISE'
        except Exception:
            s.cycles.denoiser = 'OPENIMAGEDENOISE'


def _try_compute_device_type(prefs, kind: str) -> bool:
    try:
        prefs.compute_device_type = kind
        return True
    except TypeError:
        return False


def enable_aux_passes(z: bool = True, normal: bool = True, mist: bool = False):
    """Enable depth/normal passes on the active ViewLayer."""
    import bpy
    vl = bpy.context.scene.view_layers[0]
    vl.use_pass_combined = True
    vl.use_pass_z = bool(z)
    vl.use_pass_normal = bool(normal)
    vl.use_pass_mist = bool(mist)
