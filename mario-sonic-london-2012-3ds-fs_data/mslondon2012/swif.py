"""SWIF files (Sega 2D graphics container). Two kinds exist in this game:

texture SWIF:  "SWIF" header (0x20 bytes, 0x0C = offset of first block)
               "SWTD" block, +0x08 = offset of its data relative to the block,
               then one or more complete CGFX (.bcres) files holding textures.
layout SWIF:   "SWTL" block = list of the texture names used (xx_*, jp_*...),
               "SWPR" block = parts, positions and animations of a 2D screen.
               No image data: the textures live in texture SWIFs.
Both end with a "SOF0" / "SEND" footer.
"""
import struct


def _blocks(blob):
    """[(tag, offset, size)] of the blocks following the SWIF header."""
    if blob[:4] != b"SWIF":
        raise ValueError("not a SWIF file")
    count, pos = struct.unpack_from("<II", blob, 8)
    out = []
    for _ in range(count):
        if pos + 8 > len(blob):
            break
        tag = blob[pos:pos + 4]
        size, = struct.unpack_from("<I", blob, pos + 4)
        out.append((tag, pos, size))
        pos += 8 + size
    return out


def swif_kind(blob):
    """'texture', 'layout' or 'unknown'."""
    tags = [t for t, _, _ in _blocks(blob)]
    if b"SWTD" in tags:
        return "texture"
    if b"SWTL" in tags or b"SWPR" in tags:
        return "layout"
    return "unknown"


def unwrap_swif(blob):
    """Returns the CGFX (.bcres) files stored in a texture SWIF, unchanged."""
    for tag, pos, _ in _blocks(blob):
        if tag != b"SWTD":
            continue
        p = pos + struct.unpack_from("<I", blob, pos + 8)[0]
        out = []
        while blob[p:p + 4] == b"CGFX":
            size, = struct.unpack_from("<I", blob, p + 0x0C)
            if size < 0x14 or p + size > len(blob):
                raise ValueError("CGFX size out of bounds at 0x%x" % p)
            out.append(blob[p:p + size])
            p += size
        if out:
            return out
        raise ValueError("SWTD block holds no CGFX data")
    raise ValueError("no SWTD (texture) block")


def layout_texture_names(blob):
    """Texture names listed in the SWTL block of a layout SWIF."""
    for tag, pos, size in _blocks(blob):
        if tag != b"SWTL":
            continue
        names, p, end = [], pos + 0x10, pos + 8 + size
        while p < end:
            z = blob.find(b"\0", p, end)
            if z <= p:
                break
            s = blob[p:z]
            if not all(0x21 <= c < 0x7F for c in s):
                break
            names.append(s.decode("ascii"))
            p = (z + 4) & ~3          # strings are padded to 4 bytes
        return names
    return []
