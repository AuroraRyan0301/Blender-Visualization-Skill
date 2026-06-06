"""blender_kit.lib — primitives for Blender Cycles rendering.

Modules:
  coord, mesh_io, normalize, normals    pure-numpy mesh helpers
  materials, camera, world, scene       bpy-backed builders
  render_setup, compositor              Cycles + Compositor config
  exr_reader, postproc                  EXR decode + sRGB / depth / normal viz

Importing the package does not import bpy. Each bpy-backed module imports bpy
at call time so the modules can be inspected from non-Blender python too.
"""
