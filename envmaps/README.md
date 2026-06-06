# HDRI envmaps

The kit ships **no** HDRIs by default — drop your own `*.exr` files here and
reference them by filename from any render script:

```bash
blender -b --python scripts/render_diffuse.py -- \
        --obj input.glb --out_dir out --hdri my_studio.exr
```

`lib/world.py` resolves bare filenames against this directory and absolute
paths verbatim.

## Where to get HDRIs

[Poly Haven](https://polyhaven.com/hdris) — CC0, free, high quality. Pick a
2k or 4k EXR. The defaults referenced in `SKILL.md` come from there:

- `studio.exr` ← `brown_photostudio_06_2k.exr`
- `studio_blocky.exr` ← `blocky_photo_studio_2k.exr`
- `church.exr` ← `church_meeting_room_2k.exr`

## Quick fetch

```bash
# pick any HDRI slug from polyhaven and download the 2k EXR:
curl -L -o studio.exr \
  "https://dl.polyhaven.org/file/ph-assets/HDRIs/exr/2k/brown_photostudio_06_2k.exr"
```

EXR files are intentionally gitignored — the kit is engine + materials, not a
HDRI distribution.
