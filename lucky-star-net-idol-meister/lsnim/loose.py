"""lt.bin (font) and pr.bin (images): the two files of DATA that are not CPK."""
import os
import sys

from .tables import LT_GLYPH, PR_IMAGES, PR_OFFSETS, PR_PALETTES, PR_WIDTHS
from .images import Image, best_layout, decode_font, find_blocks, np, to_indices


def extract_lt(path, output_dir):
    """lt.bin -> <output_dir>/png/lt.png (glyph sheet, 64 glyphs per row)."""
    with open(path, 'rb') as f:
        data = f.read()
    width, height, stride = LT_GLYPH
    sheet = decode_font(data, width, height, stride)
    count = len(data) // stride
    target = os.path.join(output_dir, 'png', 'lt.png')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    Image.fromarray(np.ascontiguousarray(sheet), 'RGBA').save(target)
    print('  %d glyphs of %dx%d -> %s' % (count, width, height, os.path.join('png', 'lt.png')))


def decode_pr(data):
    """pr.bin -> [(name suffix, rgba)] for its 30 images."""
    offsets = list(PR_OFFSETS) + [len(data)]
    out = []
    for n in range(PR_IMAGES):
        raw = data[offsets[n]:offsets[n + 1]]
        blocks = find_blocks(raw)
        pixels = blocks[0][1] if blocks else raw
        for variant, p in enumerate(PR_PALETTES.get(n, [n + 31])):
            bpp = 4 if offsets[p + 1] - offsets[p] == 0x100 else 8
            palette = np.frombuffer(data[offsets[p]:offsets[p] + 0x400], np.uint8).reshape(256, 4)
            palette = palette[:16] if bpp == 4 else palette
            if n in PR_WIDTHS:
                indices = to_indices(pixels, PR_WIDTHS[n], bpp)
            else:
                indices = best_layout(pixels, palette, bpp)[1]
            out.append(('%02d' % n + ('_v%d' % variant if variant else ''), palette[indices]))
    return out


def extract_pr(path, output_dir):
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < PR_OFFSETS[-1] + 0x400:
        sys.exit('%s: not the pr.bin of ULJM05542 (too small)' % path)
    images = decode_pr(data)
    for name, rgba in images:
        target = os.path.join(output_dir, 'png', name + '.png')
        os.makedirs(os.path.dirname(target), exist_ok=True)
        Image.fromarray(np.ascontiguousarray(rgba), 'RGBA').save(target)
    print('  %d images (%d PNG with the colour variants) -> png/' % (PR_IMAGES, len(images)))


LOOSE_FILES = {'lt.bin': extract_lt, 'pr.bin': extract_pr}
