"""Graphics decoding for the Konami chips used by DBZ.

* K053246/K053247 sprites : 16x16 4bpp, 128 bytes/tile, rows of 8 bytes.
  Multi-tile sprites address sub-tiles in Morton (Z) order:
  code bits = x0 y0 x1 y1 x2 y2  -> 8x8 tiles form a 128x128 "block".
* K056832 tilemaps : 8x8 4bpp, 32 bytes/tile.
* K053936 PSAC (ROZ) : 16x16 4bpp packed MSB, 128 bytes/tile.
"""
import numpy as np

# nibble order of a 16-pixel sprite row (MAME k053247 spritelayout x offsets / 4)
_SPRITE_NIBBLES = np.array([2, 3, 0, 1, 6, 7, 4, 5, 10, 11, 8, 9, 14, 15, 12, 13])
_CHAR_NIBBLES = np.array([2, 3, 0, 1, 6, 7, 4, 5])


def _nibbles(data):
    b = np.frombuffer(data, dtype=np.uint8)
    n = np.empty(b.size * 2, dtype=np.uint8)
    n[0::2] = b >> 4
    n[1::2] = b & 15
    return n


def decode_sprites(region):
    """-> uint8 array (ntiles, 16, 16) of pen indices 0..15."""
    n = _nibbles(region).reshape(-1, 16, 16)
    return n[:, :, _SPRITE_NIBBLES]


def decode_k056832(region):
    """-> uint8 array (ntiles, 8, 8)."""
    n = _nibbles(region).reshape(-1, 8, 8)
    return n[:, :, _CHAR_NIBBLES]


def decode_psac(region):
    """gfx_16x16x4_packed_msb -> (ntiles, 16, 16)."""
    return _nibbles(region).reshape(-1, 16, 16)


def morton_blocks(tiles, side=8):
    """Arrange tiles (N,h,w) into blocks of side x side tiles following the
    K053247 sub-tile addressing. Returns (nblocks, side*h, side*w)."""
    n, h, w = tiles.shape
    per = side * side
    nblk = n // per
    t = tiles[:nblk * per].reshape(nblk, per, h, w)
    out = np.zeros((nblk, side * h, side * w), dtype=tiles.dtype)
    for code in range(per):
        x = (code & 1) | ((code >> 1) & 2) | ((code >> 2) & 4)
        y = ((code >> 1) & 1) | ((code >> 2) & 2) | ((code >> 3) & 4)
        out[:, y * h:(y + 1) * h, x * w:(x + 1) * w] = t[:, code]
    return out


def grid(images, cols, pad=0, fill=0):
    """Tile a stack (N,h,w) into one 2D image of `cols` columns."""
    n, h, w = images.shape
    rows = (n + cols - 1) // cols
    out = np.full((rows * (h + pad) - pad if rows else 0, cols * (w + pad) - pad), fill, dtype=images.dtype)
    for i in range(n):
        r, c = divmod(i, cols)
        out[r * (h + pad):r * (h + pad) + h, c * (w + pad):c * (w + pad) + w] = images[i]
    return out


# ---- palettes ----------------------------------------------------------------

def gray_palette(transparent0=True):
    """16-level ramp, pen 0 transparent (Konami sprites use pen 0 as transparency)."""
    pal = [(i * 17, i * 17, i * 17) for i in range(16)]
    return pal


def xrgb555_to_rgb(words):
    """Big-endian xRGB_555 words -> list of (r,g,b)."""
    out = []
    for w in words:
        r = (w >> 10) & 31
        g = (w >> 5) & 31
        b = w & 31
        out.append(((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2)))
    return out


def load_palette_dump(path):
    """Load a dump of palette RAM (0x4a8000-0x4abfff, 8 KB of big-endian words),
    as saved from MAME's debugger with:  save dbzpal.bin,4a8000,4000
    Returns list of 512 palettes of 16 colours."""
    data = open(path, "rb").read()
    words = [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data) - 1, 2)]
    cols = xrgb555_to_rgb(words)
    return [cols[i:i + 16] for i in range(0, len(cols) - 15, 16)]


def to_png(path, pens, palette, transparent0=True):
    """Save an indexed PNG (pen indices -> palette), pen 0 transparent."""
    from PIL import Image
    img = Image.fromarray(pens.astype(np.uint8), mode="P")
    flat = []
    for c in palette[:256]:
        flat.extend(c)
    flat.extend([0] * (768 - len(flat)))
    img.putpalette(flat)
    if transparent0:
        img.save(path, transparency=0, optimize=True)
    else:
        img.save(path, optimize=True)
