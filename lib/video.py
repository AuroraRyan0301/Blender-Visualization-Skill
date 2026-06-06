"""Frame sequence -> mp4 via ffmpeg.

Pure subprocess wrapper. No dependency on bpy.
"""
import os
import shutil
import subprocess


def frames_to_mp4(pattern: str, out_path: str, fps: int = 24,
                  crf: int = 18, codec: str = 'libx264') -> str:
    """`pattern` is a printf-style frame path (e.g. 'f%04d.png').

    Returns out_path on success. Raises if ffmpeg is missing or returns non-zero.
    """
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise RuntimeError('ffmpeg not in PATH; install or extend $PATH')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-framerate', str(fps), '-i', pattern,
        '-c:v', codec, '-pix_fmt', 'yuv420p',
        '-crf', str(crf), '-movflags', '+faststart',
        # Ensure dimensions are even for yuv420p
        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path
