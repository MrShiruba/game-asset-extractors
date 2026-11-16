"""
RHG files ("RHG\\0"): 2D graphics of the interface (HUD portraits, menu parts,
character renders...). The AGS files next to them animate these graphics.

Layout (little-endian u32), worked out from the files:
    0x00 "RHG\\0", 1, 0, 0
    0x10 (pointer, region count), (pointer, image count), (pointer, palette count), 2, 0, 1, ...
    0x40 region records (visible part of an image: ..., width, height; their size varies)
    then image records, 0x24 bytes each, one after the other (found by their content):
        +0x00 2, +0x04 format (0x11 = 8-bit indices, 0x12 = 4-bit indices),
        +0x08 width, +0x0C height, +0x10 pointer, +0x14 byte size, +0x18 row stride
    then palette records, 0x20 bytes each, from the next 16-byte boundary:
        +0x00 0x14, +0x04 pointer, +0x08 byte size, +0x0C colour count (RGBA8888)
    then the data: every image, then every palette, in record order, each block
    starting on a 0x80-byte boundary (the first one after the records). The pointers
    are memory addresses from the tool that made the file and are not used.
    Pixels are in the PSP swizzled layout, like the textures.
The n-th 8-bit image uses the n-th 256-colour palette and the n-th 4-bit image the
n-th 16-colour palette: a file can hold more palettes than images.
"""
import struct

from .texture import _palette, _unswizzle

MAGIC = b"RHG\0"


BLOCK = 0x80


def _align(x, a):
    return (x + a - 1) // a * a


def _align16(x):
    return _align(x, 16)


def _first_image_record(data):
    for pos in range(0x40, len(data) - 0x24, 4):
        two, fmt, width, height, _, size = struct.unpack_from("<6I", data, pos)
        if two == 2 and fmt in (0x11, 0x12) and 0 < width <= 1024 and 0 < height <= 1024:
            if size * 8 == width * height * (8 if fmt == 0x11 else 4):
                return pos
    return None


def _layout(pixels, width, height, bits):
    """Pixels are stored in the PSP swizzled layout (16-byte x 8-row blocks)."""
    row = width * bits // 8
    if row >= 16 and row % 16 == 0 and height % 8 == 0 and row * height == len(pixels):
        pixels = _unswizzle(pixels, row, height)
    if bits == 4:
        pixels = bytes(v for b in pixels for v in (b & 15, b >> 4))
    return pixels


def _palette_map(image_records, colours):
    """The n-th 8-bit image uses the n-th 256-colour palette, the n-th 4-bit image the
    n-th 16-colour palette (files can have more palettes than images)."""
    by_size = {16: [c for c in colours if len(c) == 16], 256: [c for c in colours if len(c) == 256]}
    used = {16: 0, 256: 0}
    result = []
    for fmt, *_ in image_records:
        wanted = 256 if fmt == 0x11 else 16
        found = by_size[wanted]
        result.append(found[used[wanted]] if used[wanted] < len(found) else found[0] if found else None)
        used[wanted] += 1
    return result


def decode(data):
    """[(width, height, rgba)] for every image of an RHG file, or None."""
    if data[:4] != MAGIC or len(data) < 0x40:
        return None
    regions, images, palettes = (struct.unpack_from("<I", data, off)[0] for off in (0x14, 0x1C, 0x24))
    if not images or images > 256 or palettes > 256 or regions > 4096:
        return None
    pos = _first_image_record(data)
    if pos is None or pos + 0x24 * images > len(data):
        return None
    image_records = []
    for _ in range(images):
        fmt, width, height, _, size, stride = struct.unpack_from("<6I", data, pos + 4)
        image_records.append((fmt, width, height, size, stride))
        pos += 0x24
    pos = _align16(pos)
    palette_records = []
    for _ in range(palettes):
        if pos + 0x20 > len(data):
            return None
        tag, _, size, count = struct.unpack_from("<4I", data, pos)
        if tag != 0x14:
            return None
        palette_records.append((size, count))
        pos += 0x20
    offset = pos
    pixel_data = []
    for record in image_records:
        offset = _align(offset, BLOCK)
        pixel_data.append(data[offset:offset + record[3]])
        offset += record[3]
    colours = []
    for size, count in palette_records:
        offset = _align(offset, BLOCK)
        colours.append(_palette(data[offset:offset + size], 4))
        offset += size
    if offset > len(data):
        return None

    palettes_used = _palette_map(image_records, colours)
    result = []
    for (fmt, width, height, size, stride), pixels, palette in zip(image_records, pixel_data, palettes_used):
        bits = 8 if fmt == 0x11 else 4 if fmt == 0x12 else None
        if bits is None or not width or not height or size * 8 != width * height * bits:
            return None
        indices = _layout(pixels, width, height, bits)
        if not palette or max(indices) >= len(palette):
            return None
        result.append((width, height, b"".join(palette[i] for i in indices)))
    return result
