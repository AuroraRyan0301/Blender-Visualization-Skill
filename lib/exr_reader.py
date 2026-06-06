"""Read OPEN_EXR_MULTILAYER files produced by compositor.setup_multilayer_exr.

Layer names: 'rgb' (R,G,B,A), 'depth' (V), 'normal' (X,Y,Z).
Requires: pip install OpenEXR
"""
import numpy as np

# Channel suffix lookup per layer.
_CHANNEL_SUFFIXES = {
    'rgb': ('R', 'G', 'B', 'A'),
    'normal': ('X', 'Y', 'Z'),
    'depth': ('V',),
    'alpha': ('A',),
    'mist': ('V',),
}


def _read_layer(data, name, suffixes):
    import Imath
    pt = Imath.PixelType(Imath.PixelType.FLOAT)
    header = data.header()
    dw = header['dataWindow']
    h = dw.max.y - dw.min.y + 1
    w = dw.max.x - dw.min.x + 1
    chans = []
    for s in suffixes:
        buf = data.channel(f'{name}.{s}', pt)
        arr = np.frombuffer(buf, dtype=np.float32).reshape(h, w, 1)
        chans.append(arr)
    out = np.dstack(chans)
    if out.shape[-1] == 1:
        out = out[..., 0]
    return out


def read_multilayer(path: str, layers=('rgb', 'depth', 'normal')):
    """Return dict {layer_name: ndarray}.

    rgb -> (H,W,4) float32 linear; depth -> (H,W); normal -> (H,W,3).
    """
    import OpenEXR
    data = OpenEXR.InputFile(path)
    out = {}
    for L in layers:
        if L not in _CHANNEL_SUFFIXES:
            raise ValueError(f'unknown layer: {L}')
        out[L] = _read_layer(data, L, _CHANNEL_SUFFIXES[L])
    return out
