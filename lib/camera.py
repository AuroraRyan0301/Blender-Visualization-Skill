"""Camera placement.

place_camera(az, el, ...)        primitive: spherical coordinates -> Blender cam
add_orbit_camera(i, n, ...)      legacy: pick view i of an N-view static orbit
add_look_at_camera(loc, target)  explicit pose
"""
import math


def place_camera(az_deg: float, el_deg: float, scene_center, scene_diag: float,
                 distance_factor: float = 2.5, focal_mm: float = 50.0,
                 name: str = 'cam'):
    """Spherical-coord camera. (az, el) in degrees, r = scene_diag * distance_factor.

    az = 0 along +X, increases CCW viewed from +Z. el = 0 in XY plane,
    el = +90 = +Z. Camera aimed at scene_center with up = +Z.
    """
    import bpy
    from mathutils import Vector
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    r = scene_diag * distance_factor
    cam_loc = Vector((
        float(scene_center[0]) + r * math.cos(el) * math.cos(az),
        float(scene_center[1]) + r * math.cos(el) * math.sin(az),
        float(scene_center[2]) + r * math.sin(el),
    ))
    cam = bpy.data.cameras.new(name)
    cam.lens = focal_mm
    cam_obj = bpy.data.objects.new(name, cam)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = cam_loc
    target = Vector((float(scene_center[0]), float(scene_center[1]),
                      float(scene_center[2])))
    direction = target - cam_loc
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj


def add_orbit_camera(view_idx: int, n_views: int, scene_center, scene_diag,
                     distance_factor: float = 2.5, elevation_deg: float = 25.0,
                     az_offset_deg: float = 35.0, focal_mm: float = 50.0):
    """Legacy: place camera at view_idx of n_views evenly spaced around a circle."""
    az = (view_idx / max(n_views, 1)) * 360.0 + az_offset_deg
    return place_camera(az, elevation_deg, scene_center, scene_diag,
                          distance_factor=distance_factor, focal_mm=focal_mm)


def add_look_at_camera(location, target, focal_mm: float = 50.0,
                       name: str = 'cam'):
    """Place camera at `location` aimed at `target`."""
    import bpy
    from mathutils import Vector
    cam = bpy.data.cameras.new(name)
    cam.lens = focal_mm
    cam_obj = bpy.data.objects.new(name, cam)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = Vector(location)
    direction = Vector(target) - Vector(location)
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj
