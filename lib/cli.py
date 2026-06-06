"""Shared argparse helpers + parse-time post-processing.

Render scripts compose their CLI by calling the add_*_args helpers below.
Keeps every script's argument list consistent and centrally documented.
"""
from . import trajectory


def add_io_args(ap):
    ap.add_argument('--obj', required=True,
                    help='mesh path (any supported format) or KaiNinja obj-id')
    ap.add_argument('--out_dir', required=True)
    ap.add_argument('--source_frame', choices=['auto', 'y_up', 'z_up'],
                    default='auto',
                    help='override per-format default coord frame')


def add_render_args(ap, *, samples_default: int = 64, res_default: int = 1024):
    ap.add_argument('--samples', type=int, default=samples_default)
    ap.add_argument('--res', type=int, default=res_default)
    ap.add_argument('--output_format', choices=['png', 'exr'], default='png')


def add_world_args(ap, default_hdri: str = 'studio.exr'):
    ap.add_argument('--hdri', default=default_hdri,
                    help='HDRI in envmaps/ or absolute path')
    ap.add_argument('--hdri_strength', type=float, default=1.0)


def add_camera_args(ap):
    ap.add_argument('--trajectory', choices=trajectory.NAMES, default='static',
                    help='static: N legacy views around a circle (default)')
    ap.add_argument('--frames', type=int, default=4,
                    help='number of frames / views')
    ap.add_argument('--start_az', type=float, default=35.0,
                    help='[static/circle/half_circle] starting azimuth deg')
    ap.add_argument('--sweep', type=float, default=180.0,
                    help='[half_circle] sweep degrees')
    ap.add_argument('--elevation', type=float, default=25.0)
    ap.add_argument('--distance', type=float, default=2.5,
                    help='camera distance factor × scene_diag')
    ap.add_argument('--center_az', type=float, default=0.0,
                    help='[hemisphere_jitter] center azimuth deg')
    ap.add_argument('--center_el', type=float, default=45.0,
                    help='[hemisphere_jitter] center elevation deg')
    ap.add_argument('--az_range', type=float, default=30.0,
                    help='[hemisphere_jitter] +/-az range deg')
    ap.add_argument('--el_range', type=float, default=30.0,
                    help='[hemisphere_jitter] +/-el range deg')
    ap.add_argument('--distance_jitter', type=float, default=0.1,
                    help='[hemisphere_jitter] +/-distance factor range')
    ap.add_argument('--seed', type=int, default=0,
                    help='[hemisphere_jitter] random seed')


def add_video_args(ap):
    ap.add_argument('--mp4', action='store_true',
                    help='post-stitch frames into out_dir/video.mp4 via ffmpeg')
    ap.add_argument('--fps', type=int, default=24)


def build_trajectory(args):
    """Build the (az, el, df) trajectory list from parsed argparse args."""
    return trajectory.build(
        args.trajectory, args.frames,
        start_az=args.start_az, sweep=args.sweep, elevation=args.elevation,
        center_az=args.center_az, center_el=args.center_el,
        az_range=args.az_range, el_range=args.el_range,
        distance=args.distance, distance_jitter=args.distance_jitter,
        seed=args.seed,
    )


def configure_output_format(scene, output_format: str):
    """Set Blender's image_settings + view_transform for png|exr."""
    s = scene
    if output_format == 'png':
        s.render.image_settings.file_format = 'PNG'
        s.render.image_settings.color_mode = 'RGBA'
        s.render.image_settings.color_depth = '8'
        s.view_settings.view_transform = 'Standard'
    elif output_format == 'exr':
        s.render.image_settings.file_format = 'OPEN_EXR'
        s.render.image_settings.color_mode = 'RGB'
        s.render.image_settings.color_depth = '32'
        s.render.image_settings.exr_codec = 'ZIP'
        s.view_settings.view_transform = 'Raw'
    else:
        raise ValueError(f'output_format must be png|exr, got {output_format}')
