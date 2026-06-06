"""Stitch a directory of PNG frames into mp4 via ffmpeg.

Useful for assembling videos from the per-frame PNG decoder outputs of the
EXR pipelines (depth_normal, mask), or for re-encoding any frame sequence.

Usage:
  python frames_to_mp4.py --pattern 'out/dn/f%04d/rgb.png' --out out/rgb.mp4
  python frames_to_mp4.py --pattern 'out/diffuse/f%04d.png' --out out/d.mp4
"""
import os
import sys
import argparse

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if KIT_ROOT not in sys.path:
    sys.path.insert(0, KIT_ROOT)

from lib import video  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pattern', required=True,
                    help='printf-style frame path, e.g. f%%04d.png')
    ap.add_argument('--out', required=True, help='output mp4 path')
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--crf', type=int, default=18)
    args = ap.parse_args()
    out = video.frames_to_mp4(args.pattern, args.out, fps=args.fps, crf=args.crf)
    print(f'[mp4] -> {out}')


if __name__ == '__main__':
    main()
