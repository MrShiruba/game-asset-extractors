"""
Textures (no signature; found as bin parts of the nested archives).

Header, little-endian u32:
    +0x00 image count, +0x04 8, +0x08 / +0x0C unknown, then from +0x20 one 0x60-byte
    record per image:
        +0x00 pixel offset / 4      +0x04 palette offset / 4   (from the file start)
        +0x08 pixel bytes           +0x0C palette bytes
        +0x10 unknown               +0x14 1 for 4-bit, 4 for 8-bit images
    palettes are RGBA8888
        +0x18 mipmap levels?        +0x28 u8 log2(height), u8 log2(width),
                                          u8 flags, u8 format
    A record with 0 pixel bytes is another palette for the previous image's pixels.
Pixels are 4 or 8 bit palette indices in the PSP layout (blocks of 16 bytes x 8 rows). Palette alpha is PlayStation style (0x80 = opaque).

decode() returns [(width, height, RGBA bytes)]; to_png() needs no library.
"""
import struct
import zlib

RECORD = 0x60
FIRST = 0x20


def _records(data, start=0):
    if len(data) < start + FIRST + RECORD:
        return None
    count, eight = struct.unpack_from("<II", data, start)
    if not 1 <= count <= 256 or (eight != 8 and not start) \
            or start + FIRST + RECORD * count > len(data):
        return None
    records = []
    for k in range(count):
        base = start + FIRST + RECORD * k
        pix, pal, pix_size, pal_size, _, color = struct.unpack_from("<6I", data, base)
        lh, lw, flags, fmt = data[base + 0x28:base + 0x2C]
        records.append((4 * pix, 4 * pal, pix_size, pal_size, color, lw, lh, flags))
    return records


def _unswizzle(pixels, row_bytes, height):
    out = bytearray(len(pixels))
    blocks = row_bytes // 16
    i = 0
    for by in range(height // 8):
        for bx in range(blocks):
            for r in range(8):
                o = (by * 8 + r) * row_bytes + bx * 16
                out[o:o + 16] = pixels[i:i + 16]
                i += 16
    return bytes(out)


def _palette(raw, color):
    if color == 4:
        return [bytes((raw[i], raw[i + 1], raw[i + 2], min(255, raw[i + 3] * 2)))
                for i in range(0, len(raw) - 3, 4)]
    if color == 2:      # RGBA5551
        cols = []
        for i in range(0, len(raw) - 1, 2):
            v = raw[i] | raw[i + 1] << 8
            cols.append(bytes(((v & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31,
                               (v >> 10 & 31) * 255 // 31, 255 if v >> 15 else 0)))
        return cols
    return None


MAP_MAGIC = b"\x60\x0b\x9a\x7e"


def map_textures(data):
    """Textures of a stage geometry file (.map, signature 60 0B 9A 7E): the same texture
    block as a .tex file, at the offset in u32 +0x2C of the header (its size is u32 +0x1C,
    its record count u32 +0x18), with offsets from the start of the .map. The rest of the
    file is geometry (+0x08 / +0x0C: count and offset of the mesh records, 0x20 bytes
    each) and is not decoded."""
    if data[:4] != MAP_MAGIC or len(data) < 0x30:
        return None
    start = struct.unpack_from("<I", data, 0x2C)[0]
    return decode(data, start)


def decode(data, start=0):
    """[(width, height, rgba)] for every image of a texture file, or None."""
    records = _records(data, start)
    if not records:
        return None
    images, last = [], None
    for pix, pal, pix_size, pal_size, color, lw, lh, flags in records:
        if pal + pal_size > len(data) or pix + pix_size > len(data):
            return None
        if pix_size:
            if not (1 <= lw <= 10 and 1 <= lh <= 10):
                return None
            w, h = 1 << lw, 1 << lh
            bits = pix_size * 8 // (w * h)
            if bits not in (4, 8) or pix_size * 8 != bits * w * h:
                return None
            pixels = data[pix:pix + pix_size]
            row = w * bits // 8
            if row >= 16 and h % 8 == 0:
                pixels = _unswizzle(pixels, row, h)
            if bits == 4:
                pixels = bytes(v for b in pixels for v in (b & 15, b >> 4))
            last = (w, h, pixels)
        if last is None:
            return None
        colors = _palette(data[pal:pal + pal_size], 4)
        if not colors or max(last[2]) >= len(colors):
            return None
        w, h, pixels = last
        images.append((w, h, b"".join(colors[i] for i in pixels)))
    return images


SHEET_WIDTH = 1024
SHEET_GAP = 2


def sheet(images):
    """Put several images on one transparent sheet, in rows (left to right, top to
    bottom, in file order, 2 pixels apart): (width, height, rgba)."""
    if len(images) == 1:
        return images[0]
    limit = max(SHEET_WIDTH, max(w for w, _, _ in images))
    places, x, y, row_h, width = [], 0, 0, 0, 0
    for w, h, _ in images:
        if x and x + w > limit:
            x, y, row_h = 0, y + row_h + SHEET_GAP, 0
        places.append((x, y))
        width = max(width, x + w)
        x, row_h = x + w + SHEET_GAP, max(row_h, h)
    height = y + row_h
    canvas = bytearray(width * height * 4)
    for (w, h, rgba), (px, py) in zip(images, places):
        for row in range(h):
            start = ((py + row) * width + px) * 4
            canvas[start:start + w * 4] = rgba[row * w * 4:(row + 1) * w * 4]
    return width, height, bytes(canvas)


def to_png(width, height, rgba):
    rows = b"".join(b"\0" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    chunk = lambda tag, body: (struct.pack(">I", len(body)) + tag + body
                               + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))
