"""Frame-iteration driver. All render scripts share this.

Caller provides two callables:
  build_scene(frame_idx)   sets up the per-frame Blender scene — meshes,
                            materials, world. Scene is cleared just before.
  configure_output(path)   wires Blender's render output for this frame.
                            For PNG / single-EXR: `path` is the file path.
                            For multilayer EXR: `path` is a directory containing
                            0001.exr.

Plus camera + trajectory + output naming, all centralized.
"""
import os


def render_frames(trajectory, scene_center, scene_diag, *,
                  out_dir: str,
                  build_scene,
                  configure_output,
                  extension: str = 'png',
                  use_multilayer_dirs: bool = False,
                  mp4_out: str = None,
                  fps: int = 24,
                  per_frame_setup=None) -> list:
    """Loop over trajectory, render one frame per (az, el, df) tuple.

    Frame naming: out_dir/f{NNNN}.{ext} (or out_dir/f{NNNN}/0001.exr in
    multilayer mode). NNNN is zero-padded to width 4.

    per_frame_setup(frame_idx) is invoked AFTER scene clear and BEFORE
    build_scene, for things like film_transparent toggle or filter type
    that need to be re-applied each frame.

    Returns the list of frame paths (file paths or directory paths).
    """
    import bpy
    from . import scene as scene_mod
    from . import camera as camera_mod

    os.makedirs(out_dir, exist_ok=True)
    written = []
    n = len(trajectory)
    for fi, (az, el, df) in enumerate(trajectory):
        scene_mod.clear_scene()
        if per_frame_setup:
            per_frame_setup(fi)
        build_scene(fi)
        camera_mod.place_camera(az, el, scene_center, scene_diag,
                                 distance_factor=df)
        if use_multilayer_dirs:
            frame_dir = os.path.join(out_dir, f'f{fi:04d}')
            os.makedirs(frame_dir, exist_ok=True)
            configure_output(frame_dir)
            bpy.context.scene.render.filepath = os.path.join(
                out_dir, f'_dummy_f{fi:04d}.png')
            written.append(frame_dir)
        else:
            frame_path = os.path.join(out_dir, f'f{fi:04d}.{extension}')
            configure_output(frame_path)
            bpy.context.scene.render.filepath = frame_path
            written.append(frame_path)
        bpy.ops.render.render(write_still=True)
        print(f'[frame {fi + 1}/{n}] -> {written[-1]}')

    if mp4_out and not use_multilayer_dirs:
        from . import video
        pattern = os.path.join(out_dir, 'f%04d.' + extension)
        video.frames_to_mp4(pattern, mp4_out, fps=fps)
        print(f'[mp4] -> {mp4_out}')
    return written
