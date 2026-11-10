"""T2FP (.tfp): bitmap font.

    0x00 'T2FP'
    0x04 u32 character code table offset
    0x08 u16 glyph count
    0x0A u8  glyph width
    0x0B u8  glyph height
    0x10 u32 palette offset (RGBA8888)
    0x14 u32 glyph data offset

Char codes are u16: < 0x100 is a single byte, otherwise a Shift-JIS pair.
Glyphs are packed pixels, LSB first, no row padding;
bpp = glyph size * 8 / (width * height).
"""
import os
import struct

from .util import write_png, write_text

MAGIC = b'T2FP'
COLUMNS = 64


def code_to_char(c):
    raw = bytes([c]) if c < 0x100 else bytes([c >> 8, c & 0xFF])
    try:
        ch = raw.decode('cp932')
    except UnicodeDecodeError:
        return '\\x%04X' % c
    if not ch.isprintable() or ch.isspace():
        return '\\x%04X' % c
    return ch


def convert(path, b):
    """Write <name>.png (glyph atlas) and <name>.txt (index -> char). Returns 2."""
    if b[:4] != MAGIC:
        raise ValueError('not a T2FP font')
    coff = struct.unpack_from('<I', b, 4)[0]
    n, gw, gh = struct.unpack_from('<HBB', b, 8)
    poff, goff = struct.unpack_from('<II', b, 0x10)
    codes = struct.unpack_from('<%dH' % n, b, coff)
    gsize = (len(b) - goff) // n
    bpp = gsize * 8 // (gw * gh)
    if bpp not in (1, 2, 4, 8):
        raise ValueError('unexpected glyph size %d for %dx%d' % (gsize, gw, gh))
    npal = min(1 << bpp, (goff - poff) // 4)
    pal = [tuple(b[poff + i * 4:poff + i * 4 + 4]) for i in range(npal)]
    if bpp == 1:
        pal = [(0, 0, 0, 0), (255, 255, 255, 255)]   # clean black/white atlas
    pal += [(255, 255, 255, 255)] * ((1 << bpp) - len(pal))

    rows = -(-n // COLUMNS)
    W, H = COLUMNS * gw, rows * gh
    out = bytearray(W * H * 4)
    m = (1 << bpp) - 1
    for i in range(n):
        g = b[goff + i * gsize:goff + (i + 1) * gsize]
        ox, oy = (i % COLUMNS) * gw, (i // COLUMNS) * gh
        for p in range(gw * gh):
            bit = p * bpp
            v = (g[bit >> 3] >> (bit & 7)) & m
            if v:
                o = ((oy + p // gw) * W + ox + p % gw) * 4
                out[o:o + 4] = bytes(pal[v])

    base = os.path.splitext(path)[0]
    write_png(base + '.png', W, H, out)
    lines = ['# %d glyphs, %dx%d, %d bpp, %d per row in %s.png'
             % (n, gw, gh, bpp, COLUMNS, os.path.basename(base)),
             '# index\tcode\tchar']
    lines += ['%d\t%04X\t%s' % (i, c, code_to_char(c)) for i, c in enumerate(codes)]
    write_text(base + '.txt', '\n'.join(lines) + '\n')
    return 2
