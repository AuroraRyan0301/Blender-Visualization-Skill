"""Decode a KaiNinja ovoxel npz -> .obj + face_ids.npy via dual contouring.

Runs OUTSIDE Blender, in a torch+CUDA env that has o_voxel installed (on
Tsubame: `conda activate trellis2`). The decoded mesh is renderable by the
skill's standard --scene parts:

    python scripts/ovoxel_to_mesh.py --in ov.npz --out_obj mesh.obj
    $BLENDER -b --python scripts/render.py -- \\
        --scene parts --mesh mesh.obj --face_ids mesh.fids.npy \\
        --out_dir out

Input npz keys (KaiNinja convention):
    coords          (N,3) int   — voxel indices in [0, grid_size)
    dual_vertices   (N,3) float — per-voxel sub-cell offset
    intersected     (N,3) bool/float — per-voxel x/y/z edge intersection flag
    part_id         (N,)  int   — optional; emits face_ids.npy if present

Output OBJ verts are in the same frame as the original encoded mesh — for
KaiNinja preprocess that's Wavefront Y-up, so the skill's --source_frame auto
will apply the right Y->Z rotation.
"""
import os
import sys
import argparse
import numpy as np


def _majority_per_face(pid_per_vert: np.ndarray, F: np.ndarray) -> np.ndarray:
    """For each face F[i] = (v0,v1,v2), return mode of (pid[v0], pid[v1], pid[v2]).

    Tie-break: if all three differ, take pid[v0]. Vectorized.
    """
    pf = pid_per_vert[F]                      # (Nf, 3)
    a, b, c = pf[:, 0], pf[:, 1], pf[:, 2]
    same_ab = (a == b)
    same_bc = (b == c)
    same_ac = (a == c)
    # majority: at least 2 of 3 equal
    choice = np.where(same_ab | same_ac, a,
                       np.where(same_bc, b, a))
    return choice.astype(np.int32)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--in', dest='inp', required=True, help='ovoxel npz file')
    ap.add_argument('--out_obj', required=True, help='output OBJ path')
    ap.add_argument('--out_fids', default=None,
                    help='face_ids.npy output (default: <out_obj>.fids.npy)')
    ap.add_argument('--grid_size', type=int, default=512,
                    help='voxel grid resolution (default 512)')
    ap.add_argument('--aabb', type=float, nargs=6,
                    default=[-0.5, -0.5, -0.5, 0.5, 0.5, 0.5],
                    metavar=('XMIN', 'YMIN', 'ZMIN', 'XMAX', 'YMAX', 'ZMAX'),
                    help='world-space AABB (default unit cube centered at origin)')
    ap.add_argument('--src_axis', choices=['y_up', 'z_up'], default='y_up',
                    help='axis convention of the original encoded mesh. '
                         'KaiNinja preprocess varies per object: most are y_up, '
                         'but TRELLIS.2 / Articraft-derived tall-object meshes '
                         '(microscope, etc.) are z_up. When set to z_up the '
                         'decoder rotates Z->Y before writing the OBJ so the '
                         'output matches standard Wavefront convention.')
    ap.add_argument('--coords_key', default='coords')
    ap.add_argument('--dv_key', default='dual_vertices')
    ap.add_argument('--inter_key', default='intersected')
    ap.add_argument('--pid_key', default='part_id',
                    help='per-voxel part id (empty string = none)')
    args = ap.parse_args()

    try:
        import torch
        from o_voxel.convert import flexible_dual_grid_to_mesh
    except ImportError as e:
        sys.exit(f'[error] requires torch + o_voxel installed.\n'
                 f'  conda activate trellis2  # or env with o_voxel built\n'
                 f'  ImportError: {e}')

    if not torch.cuda.is_available():
        sys.exit('[error] o_voxel._C requires CUDA. Run on a GPU node.')

    d = np.load(args.inp)
    coords = d[args.coords_key].astype(np.int32)
    dv = d[args.dv_key].astype(np.float32)
    inter = d[args.inter_key].astype(bool)
    pid_per_vox = None
    if args.pid_key and args.pid_key in d.files:
        pid_per_vox = d[args.pid_key].astype(np.int32)

    print(f'[in] {args.inp}  voxels={coords.shape[0]}  '
          f'grid={args.grid_size}^3  '
          f'parts={"yes" if pid_per_vox is not None else "no"}')

    dev = 'cuda'
    coords_t = torch.from_numpy(coords).to(dev).contiguous()
    dv_t = torch.from_numpy(dv).to(dev).contiguous()
    inter_t = torch.from_numpy(inter).to(dev).contiguous()
    aabb = np.array(args.aabb).reshape(2, 3)

    verts_t, faces_t = flexible_dual_grid_to_mesh(
        coords_t, dv_t, inter_t, None,
        aabb=aabb, grid_size=args.grid_size, train=False,
    )
    V = verts_t.detach().cpu().numpy().astype(np.float32)
    F = faces_t.detach().cpu().numpy().astype(np.int64)
    print(f'[decode] V={V.shape[0]}  F={F.shape[0]}')

    if args.src_axis == 'z_up':
        # Rotate Z-up source to Y-up so the resulting OBJ matches Wavefront
        # convention; skill's default --source_frame=auto then handles it.
        # (x, y, z)_zup -> (x, z, -y)_yup
        V = np.stack([V[:, 0], V[:, 2], -V[:, 1]], axis=1)

    os.makedirs(os.path.dirname(os.path.abspath(args.out_obj)) or '.',
                exist_ok=True)
    with open(args.out_obj, 'w') as f:
        for v in V:
            f.write(f'v {v[0]} {v[1]} {v[2]}\n')
        for tri in F:
            f.write(f'f {tri[0] + 1} {tri[1] + 1} {tri[2] + 1}\n')
    print(f'[wrote] {args.out_obj}  (src_axis={args.src_axis}; '
          'OBJ in Y-up Wavefront convention)')

    if pid_per_vox is not None:
        # vertex index i corresponds to voxel index i (N voxels -> N verts).
        if pid_per_vox.shape[0] != V.shape[0]:
            print(f'[warn] part_id length {pid_per_vox.shape[0]} != V {V.shape[0]}; '
                  'skipping face_ids')
        else:
            fids = _majority_per_face(pid_per_vox, F)
            out_fids = args.out_fids or os.path.splitext(args.out_obj)[0] + '.fids.npy'
            np.save(out_fids, fids)
            uniq = sorted(int(p) for p in np.unique(fids))
            print(f'[wrote] {out_fids}  parts={uniq}')


if __name__ == '__main__':
    main()
