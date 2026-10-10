#!/usr/bin/env python3
"""
Reconstructs CGs from KonoSuba: Clothes of Desire based on "scrambled" atlases.

Format (deduced from the JSON):
  - Atlas split into cells of cellSize x cellSize (64x64), ordered from left
    to right, starting from the BOTTOM of the texture (Unity convention).
  - Each cell contains a useful piece of (cellSize - 2*padding) = 58x58 px,
    surrounded by a 3 px duplicated border (hence the repeating borders).
  - The final image is a grid of ceil(W/58) x ceil(H/58) pieces
    (2560x1440 -> 45 x 25 = 1125 entries in cellIndexList), also
    filled row by row starting from the BOTTOM.
  - cellIndexList[k] = index of the atlas cell to place at position k
    (duplicates = identical cells reused, e.g., solid background).

Usage:
  python unscramble_atlas.py EV085.json [atlas_directory] [output_directory]
  (atlases must be named <atlasName>.png, e.g., EV085_Atlas0.png)
Requires: pip install pillow
"""
import json
import math
import os
import sys

from PIL import Image


def rebuild(json_path, atlas_dir=None, out_dir=None):
    atlas_dir = atlas_dir or os.path.dirname(os.path.abspath(json_path))
    out_dir = out_dir or atlas_dir
    os.makedirs(out_dir, exist_ok=True)

    data = json.load(open(json_path, encoding="utf-8"))
    cell = data["cellSize"]
    pad = data["padding"]
    inner = cell - 2 * pad
    atlases = {}
    outputs = []

    for tex in data["textureDataList"]:
        name = tex["atlasName"]
        if name not in atlases:
            atlases[name] = Image.open(os.path.join(atlas_dir, name + ".png")).convert("RGBA")
        atlas = atlases[name]
        aw, ah = atlas.size
        per_row = aw // cell

        W, H = tex["width"], tex["height"]
        cols = math.ceil(W / inner)
        idx = tex["cellIndexList"]
        rows = math.ceil(len(idx) / cols)

        # Work on a "Unity-style" canvas (origin at the bottom), flipped at the end
        canvas = Image.new("RGBA", (cols * inner, rows * inner), (0, 0, 0, 0))
        atlas_flip = atlas.transpose(Image.FLIP_TOP_BOTTOM)
        for k, ci in enumerate(idx):
            if ci == tex.get("transparentIndex", -1):
                continue
            ax = (ci % per_row) * cell + pad
            ay = (ci // per_row) * cell + pad
            tile = atlas_flip.crop((ax, ay, ax + inner, ay + inner))
            canvas.paste(tile, ((k % cols) * inner, (k // cols) * inner))

        img = canvas.crop((0, 0, W, H)).transpose(Image.FLIP_TOP_BOTTOM)
        if tex.get("transparentIndex", -1) == -1:
            img = img.convert("RGB")
        out = os.path.join(out_dir, tex["name"] + ".png")
        img.save(out)
        outputs.append(out)
        print(f"{tex['name']}: {W}x{H} -> {out}")
    return outputs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rebuild(*sys.argv[1:4])
