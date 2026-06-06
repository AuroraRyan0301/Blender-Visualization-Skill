"""Camera placement.

Two patterns:
  - orbit:      parametric on (az, el, distance × scene_diag). Multi-view
    consistent. Used for 4-view / 8-view turntable renders.
  - look_at:    place at explicit world position aimed at target. Use when
    caller already has a camera trajectory.
"""
import math
import numpy as np


def add_orbit_camera(view_idx: int, n_views: int, scene_center, scene_diag: float,
                     distance_factor: float = 2.5, elevation_deg: float = 25.0,
                     az_offset_deg: float = 35.0, focal_mm: float = 50.0):
    """One camera, full orbit around scene_center on a horizontal ring.

    Convention: az increases CCW viewed from above. view 0 starts at
    az_offset_deg so 4-view renders avoid axis-aligned trivial views.
    Returns the new camera object and makes it the scene's active camera.
    """
    import bpy
    from mathutils import Vector

    az = (view_idx / max(n_views, 1)) * 2 * math.pi + math.radians(az_offset_deg)
    el = math.radians(elevation_deg)
    r = scene_diag * distance_factor
    cam_loc = Vector((
        float(scene_center[0]) + r * math.cos(el) * math.cos(az),
        float(scene_center[1]) + r * math.cos(el) * math.sin(az),
        float(scene_center[2]) + r * math.sin(el),
    ))
    cam = bpy.data.cameras.new('cam')
    cam.lens = focal_mm
    cam_obj = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = cam_loc
    target = Vector((float(scene_center[0]), float(scene_center[1]), float(scene_center[2])))
    direction = target - cam_loc
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj


def add_look_at_camera(location, target, focal_mm: float = 50.0):
    """Place camera at `location` aimed at `target`."""
    import bpy
    from mathutils import Vector
    cam = bpy.data.cameras.new('cam')
    cam.lens = focal_mm
    cam_obj = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = Vector(location)
    direction = Vector(target) - Vector(location)
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj
