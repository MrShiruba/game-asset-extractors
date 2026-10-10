"""Images: the game's own palette + gzip format, 2-bit fonts, sprites, GIM."""
import struct
import zlib


try:
    import numpy as np
    from PIL import Image
except ImportError:                              # images then stay raw (.bin)
    np = Image = None

#
# Image files of union.cpk use a format of their own; they are converted to PNG.
# File layout (little endian), as observed:
#   palettes      one per image, back to back from offset 0, each sorted dark to light:
#                   8-bit image: 256 RGBA colours (0x400 bytes)
#                   4-bit image:  16 RGBA colours padded to 0x100 bytes
#   [MAP chunk]   optional ("MAP\0" ...), sprite layout, not used yet
#   zero padding
#   image blocks  u32 tile_count, u32 offsets[tile_count + 1] (from block start),
#                 each tile = u32 uncompressed_size + 12 zero bytes + gzip stream
# Decompressed tiles concatenated = pixel indices, PSP swizzled (16 bytes x 8 rows).
# Neither dimensions nor bit depth are stored: they are chosen by trying the
# power-of-two widths and both depths, keeping the smoothest result that also
# fills the palette area exactly.

PALETTE_SIZE = {8: 0x400, 4: 0x100}
WIDTHS = (16, 32, 64, 128, 256, 512, 1024)


def find_blocks(data):
    """Return [(offset, pixel_bytes)] for every gzip image block."""
    blocks = []
    pos = 0
    while pos < len(data) - 16:
        count, first = struct.unpack_from('<II', data, pos)
        if 1 <= count <= 256 and first == (4 + 4 * (count + 1) + 15) // 16 * 16 \
                and data[pos + first + 16:pos + first + 19] == b'\x1f\x8b\x08':
            offsets = struct.unpack_from('<%dI' % (count + 1), data, pos + 4)
            pixels = b''.join(zlib.decompress(data[pos + offsets[k] + 16:pos + offsets[k + 1]], 31)
                              for k in range(count))
            blocks.append((pos, pixels))
            pos += offsets[-1]
            continue
        pos += 16
    return blocks


def unswizzle_bytes(raw, width_bytes, height):
    a = np.frombuffer(raw, np.uint8)[:width_bytes * height]
    a = a.reshape(height // 8, width_bytes // 16, 8, 16).transpose(0, 2, 1, 3)
    return a.reshape(height, width_bytes)


def to_indices(pixels, width, bpp):
    width_bytes = width * bpp // 8
    if width_bytes < 16 or len(pixels) % width_bytes:
        return None
    height = len(pixels) // width_bytes
    if height % 8:
        return None
    raw = unswizzle_bytes(pixels, width_bytes, height)
    if bpp == 8:
        return raw
    out = np.empty((height, width), np.uint8)
    out[:, 0::2] = raw & 15
    out[:, 1::2] = raw >> 4
    return out


def roughness(rgba):
    rgb = rgba[..., :3].astype(np.int16)
    return float(np.abs(np.diff(rgb, axis=0)).mean() + np.abs(np.diff(rgb, axis=1)).mean())


def best_layout(pixels, palette, bpp):
    """Return (roughness, indices) of the best width for this depth and palette."""
    best = None
    for width in WIDTHS:
        indices = to_indices(pixels, width, bpp)
        if indices is None:
            continue
        height = indices.shape[0]
        if width < 64 or height > 2 * width or height < width // 8:
            continue                                  # implausible shape for a texture
        score = roughness(palette[indices]) * (1 + 0.02 * abs(np.log2(width / indices.shape[0])))   # near-ties: squarer shape
        if best is None or score < best[0]:
            best = (score, indices)
    return best


def decode_font(data, width, height, stride=None):
    """Raw 2-bit font (2 bits per pixel, low bits first) -> RGBA sheet, 64 glyphs per row.
    stride = bytes per glyph when glyphs are padded (default: width * height / 4)."""
    glyph_bytes = width * height // 4
    stride = stride or glyph_bytes
    count = len(data) // stride
    raw = np.frombuffer(data[:count * stride], np.uint8).reshape(count, stride)[:, :glyph_bytes]
    pixels = np.stack([(raw >> shift) & 3 for shift in (0, 2, 4, 6)], -1).reshape(count, height, width)
    columns = 64
    rows = -(-count // columns)
    pixels = np.concatenate([pixels, np.zeros((rows * columns - count, height, width), np.uint8)])
    sheet = pixels.reshape(rows, columns, height, width).transpose(0, 2, 1, 3).reshape(rows * height, columns * width)
    alpha = (sheet * 85).astype(np.uint8)
    white = np.full(alpha.shape, 255, np.uint8)
    return np.dstack([white, white, white, alpha])


def sprite_atlas(data, header):
    """Decode a sprite atlas with the size stored in its MAP header."""
    width, height = header[12], header[13]
    blocks = find_blocks(data)
    if not blocks or not width or not height:
        return None
    pixels = blocks[0][1]
    bpp = 8 if len(pixels) == width * height else 4
    indices = to_indices(pixels, width, bpp)
    if indices is None:
        return None
    palette = np.frombuffer(data[:0x400], np.uint8).reshape(256, 4)
    return (palette[:16] if bpp == 4 else palette)[indices]


SPRITE_GAP = 8          # transparent pixels between the faces, and between faces and body


def rebuild_sprite(data):
    """Character sprite (tachi-e): rebuild its body from the MAP chunk.

    The file holds one atlas: the faces at the top (side by side, usually 2 expressions,
    face_h rows) and below them the body cut in cells, row by row in the order of the
    MAP positions. MAP chunk (u16 values after "MAP\\0"): [1] cell count, [2][3] cell
    width/height, [12][13] atlas width/height, [15] face height; cell positions
    (u16 x, u16 y) start at MAP+0x30.
    Neither the face width nor the face position on the body is stored, so the faces are
    not pasted on the body. Output (one image, file order): the 2 faces on top, cut in 2
    equal parts and SPRITE_GAP px apart, then the rebuilt body SPRITE_GAP px below.
    Returns None when the layout is not understood (the raw atlas is kept instead).
    """
    pos = data.find(b'MAP\x00')
    header = struct.unpack_from('<22H', data, pos + 4)
    count, cell_w, cell_h, face_h = header[1], header[2], header[3], header[15]
    if not count or not cell_w or not cell_h:
        return None
    atlas = sprite_atlas(data, header)
    if atlas is None:
        return None
    cells = struct.unpack_from('<%dH' % (2 * count), data, pos + 0x30)
    cells = list(zip(cells[0::2], cells[1::2]))
    per_row = atlas.shape[1] // cell_w
    width = max(x for x, _ in cells) + cell_w
    height = max(y for _, y in cells) + cell_h
    body = np.zeros((height, width, 4), np.uint8)
    for k, (x, y) in enumerate(cells):
        ax, ay = (k % per_row) * cell_w, face_h + (k // per_row) * cell_h
        if ay + cell_h > atlas.shape[0]:
            return None
        body[y:y + cell_h, x:x + cell_w] = atlas[ay:ay + cell_h, ax:ax + cell_w]
    if not face_h:
        return body
    strip = atlas[:face_h]
    filled = strip[..., 3].any(0)
    if not filled.any():
        return body
    # faces are side by side (always 2 here) and end at the first empty band
    first = int(np.argmax(filled))
    used = next((x for x in range(max(first, 32), len(filled) - 15)
                 if not filled[x:x + 16].any()), len(filled))
    face_w = used // 2
    # one image, same order as the file: faces on top, body below, SPRITE_GAP px apart
    out = np.zeros((face_h + SPRITE_GAP + height, max(width, 2 * face_w + SPRITE_GAP), 4), np.uint8)
    for k in range(2):
        x = k * (face_w + SPRITE_GAP)
        out[:face_h, x:x + face_w] = strip[:, k * face_w:(k + 1) * face_w]
    out[face_h + SPRITE_GAP:, :width] = body
    return out

def gim_colours(raw, fmt):
    """Decode GIM colour data (formats 0-3) to an RGBA array."""
    if fmt == 3:                                       # RGBA8888
        return np.frombuffer(raw, np.uint8).reshape(-1, 4)
    v = np.frombuffer(raw[:len(raw) // 2 * 2], '<u2').astype(np.uint32)
    if fmt == 0:                                       # RGB565
        r, g, b, a = v & 31, (v >> 5) & 63, (v >> 11) & 31, np.full_like(v, 1)
        return np.stack([r * 255 // 31, g * 255 // 63, b * 255 // 31, a * 255], -1).astype(np.uint8)
    if fmt == 1:                                       # RGBA5551
        r, g, b, a = v & 31, (v >> 5) & 31, (v >> 10) & 31, v >> 15
        return np.stack([r * 255 // 31, g * 255 // 31, b * 255 // 31, a * 255], -1).astype(np.uint8)
    r, g, b, a = v & 15, (v >> 4) & 15, (v >> 8) & 15, v >> 12   # RGBA4444
    return (np.stack([r, g, b, a], -1) * 17).astype(np.uint8)


def decode_gim(data):
    """Standard PSP GIM -> list of RGBA arrays (one per frame).

    Pixels may be stored in "faster" order (pix_order 1 = PSP swizzle, 16 bytes x 8 rows);
    viewers that ignore this flag show shifted lines. Indexed images may hold one palette
    per frame. Formats: 0-3 direct colour, 4 = 4-bit index, 5 = 8-bit index.
    """
    if data[:11] != b'MIG.00.1PSP':
        return []
    blocks = {}
    pos = 0x10
    while pos < len(data) - 16:
        block_id, _, size, next_offset, data_offset = struct.unpack_from('<HHIII', data, pos)
        blocks.setdefault(block_id, (pos, data_offset))
        pos += next_offset if block_id in (2, 3) else size
        if not size:
            break

    def header(block_id):
        start, data_offset = blocks[block_id]
        base = start + data_offset
        h = struct.unpack_from('<HHHHHHHHHHIIII', data, base)
        return h, base

    if 4 not in blocks:
        return []
    (_, _, fmt, order, width, height, bpp, _, _, _, _, _, first, end), base = header(4)
    pixels = data[base + first:base + end]
    frame_bytes = width * height * bpp // 8
    frames = max(1, len(pixels) // frame_bytes)
    palettes = None
    if fmt in (4, 5) and 5 in blocks:
        (_, _, pfmt, _, pwidth, _, _, _, _, _, _, _, pfirst, pend), pbase = header(5)
        colours = gim_colours(data[pbase + pfirst:pbase + pend], pfmt)
        palettes = colours.reshape(-1, pwidth, 4)
    images = []
    for k in range(frames):
        raw = pixels[k * frame_bytes:(k + 1) * frame_bytes]
        if fmt in (4, 5):
            indices = to_indices(raw, width, bpp) if order == 1 else None
            if indices is None:
                flat = np.frombuffer(raw, np.uint8)
                if bpp == 4:
                    flat = np.stack([flat & 15, flat >> 4], -1).reshape(-1)
                indices = flat.reshape(height, width)
            palette = palettes[min(k, len(palettes) - 1)] if palettes is not None else None
            if palette is None:
                return images
            images.append(palette[np.minimum(indices, len(palette) - 1)])
        else:
            width_bytes = width * bpp // 8
            rows = unswizzle_bytes(raw, width_bytes, height) if order == 1 else \
                np.frombuffer(raw, np.uint8).reshape(height, width_bytes)
            images.append(gim_colours(rows.tobytes(), fmt).reshape(height, width, 4))
    return images


def palette_drops(palette):
    """Palettes of this game are sorted from dark to light: count sharp brightness drops."""
    rgb = palette[:, :3].astype(np.float32)
    luminance = rgb @ np.array([0.3, 0.59, 0.11], np.float32)
    return int((np.diff(luminance) < -60).sum())


def place_cells(rgba, cells):
    """Rebuild a sheet from its 32x16 cell atlas; cells = (x / 32, y / 16) byte pairs."""
    xs, ys = cells[0::2], cells[1::2]
    out = np.zeros(((max(ys) + 1) * 16, (max(xs) + 1) * 32, 4), np.uint8)
    for k, (x, y) in enumerate(zip(xs, ys)):
        cx, cy = k % 16 * 32, k // 16 * 16
        out[y * 16:y * 16 + 16, x * 32:x * 32 + 32] = rgba[cy:cy + 16, cx:cx + 32]
    return out


LINE_GAP = 8             # transparent pixels between two lines of pieces


def lay_out_pieces(rgba, lines):
    rows = []
    for gap, pieces in lines:
        height = max(y1 - y0 for x0, y0, x1, y1 in pieces)
        width = sum(x1 - x0 for x0, y0, x1, y1 in pieces) + gap * (len(pieces) - 1)
        row = np.zeros((height, width, 4), np.uint8)
        x = 0
        for x0, y0, x1, y1 in pieces:
            row[:y1 - y0, x:x + x1 - x0] = rgba[y0:y1, x0:x1]
            x += x1 - x0 + gap
        rows.append(row)
    out = np.zeros((sum(r.shape[0] for r in rows) + LINE_GAP * (len(rows) - 1),
                    max(r.shape[1] for r in rows), 4), np.uint8)
    y = 0
    for row in rows:
        out[y:y + row.shape[0], :row.shape[1]] = row
        y += row.shape[0] + LINE_GAP
    return out


def decode_with_palettes(data, counts):
    """Decode an 8-bit image file whose images own counts[k] palettes each. Returns [(suffix, rgba)]."""
    out = []
    index = 0
    for k, (_, pixels) in enumerate(find_blocks(data)):
        for variant in range(counts.get(k, 1)):
            palette = np.frombuffer(data[index * 0x400:index * 0x400 + 0x400], np.uint8).reshape(256, 4)
            suffix = '_%02d' % k + ('_v%d' % variant if variant else '')
            out.append((suffix, palette[best_layout(pixels, palette, 8)[1]]))
            index += 1
    return out


def decode_images(data):
    """Return a list of RGBA numpy arrays, one per image in the file ([] if not an image)."""
    blocks = find_blocks(data)
    if not blocks:
        return []
    area = blocks[0][0]
    map_pos = data.find(b'MAP\x00', 0, area)
    if map_pos >= 0:
        area = map_pos
    count = len(blocks)

    def palette_at(offset, bpp):
        size = PALETTE_SIZE[bpp]
        raw = data[offset:offset + size]
        if len(raw) < size:
            return None
        palette = np.frombuffer(raw, np.uint8).reshape(-1, 4)
        return palette[:16] if bpp == 4 else palette

    # 0) one 8-bit palette per image, in image order (extra palettes after them are
    #    alternative colourings, e.g. photo filters of the mini-games)
    if area % 0x400 == 0 and area // 0x400 >= count:
        images = []
        for k, (_, pixels) in enumerate(blocks):
            palette = palette_at(k * 0x400, 8)
            padded = not data[k * 0x400 + 0x40:k * 0x400 + 0x100].strip(b'\x00')
            result = best_layout(pixels, palette, 8) if not padded else None
            if result is None:
                images = None
                break
            images.append(palette[result[1]])
        if images:
            return images

    # 1) direct reading: palettes follow each other in image order; a 4-bit palette is
    #    16 colours followed by zero padding up to 0x100 (then the next palette starts)
    images = []
    offset = 0
    for _, pixels in blocks:
        padded = not data[offset + 0x40:offset + 0x100].strip(b'\x00')
        nxt = data[offset + 0x100:offset + 0x140]
        bpp = 4 if padded and nxt.strip(b'\x00') and offset + 0x100 < area else 8
        palette = palette_at(offset, bpp)
        result = best_layout(pixels, palette, bpp) if palette is not None else None
        if result is None or offset + PALETTE_SIZE[bpp] > area:
            images = None
            break
        images.append(palette[result[1]])
        offset += PALETTE_SIZE[bpp]
    if images:
        return images

    # 2) fallback: dynamic programming over (image index, palette offset)
    states = {0: (0.0, [])}            # offset -> (total roughness, [(bpp, indices, offset)])
    for _, pixels in blocks:
        new_states = {}
        for offset, (total, chosen) in states.items():
            for bpp in (8, 4):
                palette = palette_at(offset, bpp)
                if palette is None:
                    continue
                result = best_layout(pixels, palette, bpp)
                if result is None:
                    continue
                score, indices = result
                score += 1000 * palette_drops(palette)     # misaligned palette: not sorted
                if bpp == 4 and data[offset + 0x40:offset + 0x100].strip(b'\x00'):
                    score += 1000                          # 4-bit palettes are zero-padded
                key = offset + PALETTE_SIZE[bpp]
                candidate = (total + score, chosen + [(bpp, indices, offset)])
                if key not in new_states or candidate[0] < new_states[key][0]:
                    new_states[key] = candidate
        states = new_states
    if not states:
        return []
    # palettes must end inside the palette area; prefer the end closest to the used area
    used = len(data[:area].rstrip(b'\x00'))
    valid = {k: v for k, v in states.items() if k <= area}
    if not valid:
        valid = states
    end = min(valid, key=lambda k: (abs(k - used) > 0x100, valid[k][0]))
    images = []
    for bpp, indices, offset in valid[end][1]:
        palette = palette_at(offset, bpp)
        images.append(palette[indices])
    return images
