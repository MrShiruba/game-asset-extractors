"""
Visual effect packages (auras, beams, impacts...): the common ones in the system archive
(entry 0..5), the special moves of each character (character archives, parts skill_NNN
and effect_common) and the story mode effects.

A package is a run of consecutive parts of an archive:

    header       ("effect"): u8 flags (0x20 / 0x21 / 0x24), u8 0x00 / 0x02 / 0x40 / 0x42,
                 u16 0, u8 layer count, u8 item count, ...; from +0x40 one 0x20-byte entry
                 per layer: u8 layer type, u8 item count, u8 texture count, u8 0; then one
                 0x40-byte record per item (start time, scale, ... as floats)
    then for each layer, in the order of the header:
        its textures (.tex, texture count of the layer)
        its items: a 3D shape (.v000) for the mesh layers, otherwise a settings record
        followed by its colour table (RGBA keys as floats 0..255, PlayStation alpha)

Layer types, named from what they draw (their textures and their values):
    0x05 particles  768-byte settings: sprites spawned in random ranges (count, speed,
                    size as min / max triples); textures: glows, flames, dust
    0x09 rings      640-byte settings; textures: rings, shock waves
    0x0E mesh       a .v000 shape (beam cylinders, arcs, spheres) textured by the layer
    0x10 glows      192-byte settings; textures: round glows, flares
    0x12 streaks    512-byte settings; textures: streaks, sparks, lightning
"""
import struct

LAYERS = {0x00: "no_data", 0x02: "trail", 0x0A: "crackles", 0x0F: "sparks", 0x11: "beam", 0x05: "particles", 0x09: "rings", 0x0E: "mesh", 0x10: "glows", 0x12: "lightning"}
MESH = 0x0E
SINGLE = (0x02,)       # one settings part, no colour table
FLAGS = (0x20, 0x21, 0x24)
# Some special moves have, just before the header, 176 float vectors (x, y, z, w):
# (0, -160, 0, 0) or zero in every file seen; probably offsets of the effect items.
OFFSETS_SIZE = 176 * 16


def header(part):
    """[(layer type, item count, texture count)] of an effect header, or None."""
    if len(part) == 0x40 and not any(part[:8]) and any(part[8:12]) and not any(part[12:]):
        return []       # a special move with no visual effect: header with no layer
    if len(part) < 0x60 or len(part) % 0x40 or part[0] & ~0x27 or part[1] & ~0xC6 or part[3]:
        return None
    count = part[4]
    if not 1 <= count <= 16 or 0x40 + 0x20 * count > len(part):
        return None
    layers = []
    for k in range(count):
        kind, items, textures, zero = part[0x40 + 0x20 * k:0x44 + 0x20 * k]
        if kind not in LAYERS or not 1 <= items <= 64 or zero \
                or any(part[0x44 + 0x20 * k:0x60 + 0x20 * k]):
            return None
        layers.append((kind, items, textures))
    return layers


def part_names(parts, is_texture):
    """{part number: name} for the effect packages found in the parts of one archive.

    parts: the (decompressed) parts; is_texture(data) -> bool. A package is named only
    when every part it should hold is where the header says, so a wrong guess names
    nothing."""
    names, k, number = {}, 0, 0
    while k < len(parts):
        layers = header(parts[k])
        if layers is None:
            k += 1
            continue
        found, pos = {}, k + 1
        tag = "fx%02d" % (number + 1)
        try:
            for kind, items, textures in layers:
                what = LAYERS[kind]
                if kind == 0:            # no part in the archive
                    continue
                for t in range(textures):
                    if not is_texture(parts[pos]):
                        raise ValueError
                    found[pos] = "%s_%s_texture" % (tag, what) + ("_%d" % (t + 1) if textures > 1 else "")
                    pos += 1
                for i in range(items):
                    item = "%s_%s_%d" % (tag, what, i + 1)
                    if kind in SINGLE:
                        if not parts[pos] or is_texture(parts[pos]) or header(parts[pos]):
                            raise ValueError
                        found[pos] = item
                        pos += 1
                    elif kind == MESH:
                        if parts[pos][:4] != b"V000":
                            raise ValueError
                        found[pos] = item
                        pos += 1
                    else:
                        settings, colors = parts[pos], parts[pos + 1]
                        if not settings or not colors or is_texture(settings) or is_texture(colors) \
                                or settings[:4] == b"V000" or header(settings):
                            raise ValueError
                        found[pos], found[pos + 1] = item, item + "_colors"
                        pos += 2
        except (ValueError, IndexError):
            k += 1
            continue
        number += 1
        names[k] = tag + "_effect"
        if k and k - 1 not in names and len(parts[k - 1]) == OFFSETS_SIZE:
            names[k - 1] = tag + "_offsets"
        names.update(found)
        k = pos
    return names
