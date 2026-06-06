"""Camera trajectories.

Each function returns a list of (azimuth_deg, elevation_deg, distance_factor)
tuples. distance_factor multiplies the scene diagonal — same convention as
lib.camera.place_camera.

Trajectories:
  static            evenly-spaced views around a full circle (legacy default)
  circle            full 360° orbit, used for a turntable video
  half_circle       partial sweep at constant elevation
  hemisphere_jitter random patch on a hemisphere — novel-view training data
"""
import math
import random


def static(n_frames, start_az=35.0, elevation=25.0, distance=2.5, **_):
    return [(start_az + 360.0 * i / max(n_frames, 1), elevation, distance)
            for i in range(n_frames)]


def circle(n_frames, start_az=0.0, elevation=25.0, distance=2.5, **_):
    return [(start_az + 360.0 * i / max(n_frames, 1), elevation, distance)
            for i in range(n_frames)]


def half_circle(n_frames, start_az=0.0, sweep=180.0, elevation=25.0,
                distance=2.5, **_):
    denom = max(n_frames - 1, 1)
    return [(start_az + sweep * i / denom, elevation, distance)
            for i in range(n_frames)]


def hemisphere_jitter(n_frames, center_az=0.0, center_el=45.0,
                      az_range=30.0, el_range=30.0,
                      distance=2.5, distance_jitter=0.1, seed=0, **_):
    rng = random.Random(seed)
    out = []
    for _ in range(n_frames):
        az = center_az + (rng.random() * 2 - 1) * az_range
        el = max(-89.0, min(89.0, center_el + (rng.random() * 2 - 1) * el_range))
        d = distance * (1.0 + (rng.random() * 2 - 1) * distance_jitter)
        out.append((az, el, d))
    return out


_REGISTRY = {
    'static': static,
    'circle': circle,
    'half_circle': half_circle,
    'hemisphere_jitter': hemisphere_jitter,
}

NAMES = tuple(_REGISTRY)


def build(name: str, n_frames: int, **kwargs):
    if name not in _REGISTRY:
        raise ValueError(f'unknown trajectory: {name}; valid: {NAMES}')
    return _REGISTRY[name](n_frames, **kwargs)
