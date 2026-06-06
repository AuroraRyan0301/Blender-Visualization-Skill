# HDRI envmaps

`studio.exr` ships with the repo: **brown_photostudio_06_2k** from
[Poly Haven](https://polyhaven.com/a/brown_photostudio_06), CC0. It's the
default `--hdri` for all render scripts.

Drop additional `*.exr` files here and reference them by filename:

```bash
$BLENDER -b --python scripts/render_diffuse.py -- \
        --obj input.glb --out_dir out --hdri church_meeting_room_2k.exr
```

`lib/world.py` resolves bare filenames against this directory and absolute
paths verbatim.

## Quick fetch from Poly Haven

```bash
# any HDRI slug + a resolution preset (2k / 4k / 1k / 8k):
SLUG=blocky_photo_studio
curl -L -o envmaps/${SLUG}_2k.exr \
  "https://dl.polyhaven.org/file/ph-assets/HDRIs/exr/2k/${SLUG}_2k.exr"
```

Additional EXRs beyond `studio.exr` are gitignored.
