"""
Nested archives used everywhere inside PACKFILE entries.

Layout (big-endian):
    u32 count, then count + 1 u32 offsets (the last one is the archive size),
    the table is padded with zeros up to a multiple of 64 and every part
    starts on a 64-byte boundary. Parts can be empty (two equal offsets) and
    can be archives themselves.

unpack() writes an archive as a folder: entry 01427 gives
    arc/01427/01427_000.<ext>, arc/01427/01427_490/01427_490_021.<ext>, ...
so the PACKFILE index still comes first in every name.
Parts compressed with zlib (u32 BE size, u32 BE packed size, zlib stream) are written
decompressed; they are almost all animations (.mot). Empty ones are skipped.
Textures (see texture.py) are written as NNNNN_KKK.tex (raw) plus NNNNN_KKK.png
(NNNNN_KKK_II.png when the file holds several images or palettes).
"""
import collections
import os
import re
import struct

from .formats import guess_ext, unwrap_zlib
from . import effect, identify, names, rhg, texture

ALIGN = 64
MAX_DEPTH = 8


def parts(data):
    """Sub-entries of a nested archive, or None. Strict: the whole layout must match."""
    if len(data) < 8:
        return None
    count = struct.unpack_from(">I", data, 0)[0]
    table = 4 + 4 * (count + 1)
    if not 1 <= count <= 4096 or table > len(data):
        return None
    offsets = struct.unpack_from(">%dI" % (count + 1), data, 4)
    first = -(-table // ALIGN) * ALIGN
    if offsets[0] != first or offsets[-1] != len(data):
        return None
    if any(o % ALIGN or b < o for o, b in zip(offsets, offsets[1:])):
        return None
    if any(data[table:first]):
        return None
    return [data[a:b] for a, b in zip(offsets, offsets[1:])]


def leaf_ext(data):
    ext = guess_ext(data)
    return ext if re.fullmatch(r"[a-z0-9]{1,8}", ext) else "bin"


LANGUAGES = ("jp", "en", "es", "fr", "de", "it")      # the order of the entries too


def _language_slot(plain, k):
    """Language of image k when it is in a group of language slots after an animation:
    1 animation slot + 6 image slots (settings 21: "Option", "Opciones", "Options",
    "Optionen", "Opzioni"), or 6 animation slots + 6 image slots (the button labels);
    the slots go jp, en, es, fr, de, it, and the release fills its own (JP: jp only, EU:
    the 5 others, US: en / es / fr). The trailing empty slots at the end of an archive
    are not stored."""
    is_rhg = lambda p: p[:4] == b"RHG\0"
    is_ags = lambda p: p[:4] == b"AGS\0"
    start = k
    while start > 0 and (not plain[start - 1] or is_rhg(plain[start - 1])):
        start -= 1
    first = start
    while first > 0 and (not plain[first - 1] or is_ags(plain[first - 1])):
        first -= 1
    ags = [i for i in range(first, start) if is_ags(plain[i])]
    if not ags:
        return None
    end = k
    while end + 1 < len(plain) and (not plain[end + 1] or is_rhg(plain[end + 1])):
        end += 1
    at_end = end == len(plain) - 1
    # empty parts before the animation may belong to the previous group (US title
    # screen: the empty de / it slots of the previous images): try without them too
    for first in range(first, ags[0] + 1):
        size = end - first + 1
        slots = 6 if size == 12 or at_end and 7 < size < 12 else \
            1 if size == 7 or at_end and size < 7 else None
        if slots is not None and not any(p and not is_ags(p) for p in plain[first:first + slots]) \
                and not any(p and not is_rhg(p) for p in plain[first + slots:end + 1]):
            break
    else:
        return None
    slot = k - first - slots
    if not 0 <= slot < len(LANGUAGES):
        return None
    # one image alone outside the Japanese slot is shown in every language (the EU
    # title screen's copyright line, in the de slot): no language
    if sum(1 for p in plain[first + slots:end + 1] if p) == 1 and slot:
        return None
    return LANGUAGES[slot]


# True: unpack() only works out the names (tools/make_entry_list.py), writes nothing
DRY_RUN = False


def write_leaf(part, folder, name, types, png=True, ext=None, label=None):
    """Write one file; textures get .tex and their PNG images next to them, named data
    files the extension of their format (names.data_extension).
    Returns the path of the file written (the raw part, not the PNG images)."""
    ext = ext or leaf_ext(part)
    images = texture.decode(part) if ext in ("bin", "tex") else None
    if images:
        ext = "tex"
    elif ext == "bin" and label:
        ext = names.data_extension(label)
    if DRY_RUN:
        types[ext] += 1
        return os.path.join(folder, "%s.%s" % (name, ext))
    os.makedirs(folder, exist_ok=True)
    if ext == "rhg":
        images = rhg.decode(part)      # 2D interface graphics, PNG next to the .rhg
    elif ext == "map":
        images = texture.map_textures(part)    # the textures of a stage, PNG next to the .map
    if images:
        if png:              # one PNG per file: its images side by side on one sheet
            with open(os.path.join(folder, "%s.png" % name), "wb") as out:
                out.write(texture.to_png(*texture.sheet(images)))
            types["png images"] += 1
    types[ext] += 1
    path = os.path.join(folder, "%s.%s" % (name, ext))
    with open(path, "wb") as out:
        out.write(part)
    return path


STAGE_PARTS = {
    b"MAPD": "map_settings",       # section table; first section: a position and a direction
    b"EVPp": "event_positions",    # groups of positions (x, y, z, 1.0) with flags
    b"MEF0": "map_effects",        # three lists (empty in the stages seen)
}


def model_names(plain):
    """{part: name} for a small archive holding a 3D model (.pmdl, or a DBES mesh) — props,
    the models of special moves (part 0 of skill_NNN): "model", "mesh", its "textures"
    and its animations "animation_N". Archives of the character layout (497 parts) are named by patch.txt."""
    if len(plain) >= 497:
        return {}
    kinds = [leaf_ext(p) if p and not parts(p) else None for p in plain]
    if "pmdl" not in kinds and "dbes" not in kinds:
        return {}
    kinds = [("tex" if texture.decode(p) else kind) if kind == "bin" else kind
             for p, kind in zip(plain, kinds)]
    found, counts = {}, collections.Counter(kinds)
    seen = collections.Counter()
    for k, kind in enumerate(kinds):
        base = {"pmdl": "model", "tex": "textures", "mot": "animation", "dbes": "mesh"}.get(kind)
        if not base:
            continue
        seen[kind] += 1
        found[k] = base if counts[kind] == 1 and kind != "mot" else "%s_%d" % (base, seen[kind])
    return found


def stage_names(plain):
    """{part: name} for a stage or board archive (part 0 is the .map geometry): its
    camera moves (.cman) and, at parts 21 / 22, a colour and a colour + floats (the
    same layouts as parts 620 / 619 of the system archive)."""
    if not plain or plain[0][:4] != b"\x60\x0b\x9a\x7e":
        return {}
    found, cameras = {}, 0
    for k, part in enumerate(plain):
        if part[:4] == b"CMAn":
            cameras += 1
            found[k] = "camera_%d" % cameras
        elif part[:4] in STAGE_PARTS:
            found[k] = STAGE_PARTS[part[:4]]
        elif len(part) >= 16 and struct.unpack_from(">I", part, 0)[0] == 1 \
                and len(part) == 16 + 48 * struct.unpack_from(">I", part, 4)[0]:
            # big-endian: u32 1, u32 node count, 8 bytes, then 48-byte nodes: x, y, z, 1.0,
            # 4 words, up to 8 u16 numbers of the linked nodes (0xFFFF = none)
            found[k] = "waypoints"
    for k, name in ((21, "ambient_color"), (22, "lighting")):
        if k < len(plain) and len(plain[k]) == 64:
            found[k] = name
    for k, part in enumerate(plain):
        if k in found or not part:
            continue
        if part[:2] == b"BM":
            # a small palette image whose colours mark zones of the board (grass,
            # roads, rocks...): read by colour, not drawn
            found[k] = "region_map"
            continue
        images = texture.decode(part) if part[:4] not in (b"RHG\0", b"AGS\0") else None
        size = images[0][:2] if images and len(images) == 1 else None
        # part 20 of the stages and boards: a 64 x 64 pattern with alpha, horizontal
        # cyan stripes or green diamonds (Earth 5..8, Supreme Kai world), drawn by the
        # renderer at 0x088926B4 with the lighting of part 22
        if k == 20 and size == (64, 64):
            found[k] = "light_pattern"
        # the sky of the unused Earth board (entry 1019): clouds, the moon, the sky
        # meshes (a list of DBES meshes) and the sky settings (grey colour, light
        # direction as a unit vector, ...)
        elif k == 5 and size == (256, 256):
            found[k] = "clouds"
        elif k == 19 and size == (128, 128):
            found[k] = "moon"
        elif k == 6 and b"DBES" in part[:64]:
            found[k] = "sky_meshes"
        elif k == 12 and len(part) == 25088:
            found[k] = "sky_settings"
    return found


def roster_portraits(plain):
    """{part: name} for a run of at least 70 consecutive .rhg parts: the menus keep one
    portrait per character in the order of the character select screen (official.ROSTER
    with the Frieza soldier after Frieza full power), then the "random" portrait and its
    "?" icon. Checked on the images of training menu 48, part 3, parts 183..254."""
    from .official import ROSTER
    order = [n for n in ROSTER if n != "frieza_soldier"]
    order.insert(order.index("frieza_full_power") + 1, "frieza_soldier")
    order = [n + "_portrait" for n in order] + ["random_portrait", "random_icon"]
    found, k = {}, 0
    while k < len(plain):
        end = k
        while end < len(plain) and plain[end][:4] == b"RHG\0":
            end += 1
        if end - k >= len(ROSTER):
            for i, name in enumerate(order[:end - k]):
                found[k + i] = name
        k = max(end, k + 1)
    return found


def unpack(data, folder, prefix, depth=0, types=None, png=True, index=None, path=(), root=None,
           counts=()):
    """Write the parts of an archive below folder.

    Returns the layout of the archive: a list with one item per part,
        None                   empty part
        {"file": relpath}      part written as a file (relpath from root, "/" separators)
        {"arc": [...]}         part that is itself an archive
    plus "zlib": true when the part is stored compressed in the game (its file holds
    the decompressed data; an empty decompressed part has no "file").
    types (a Counter) counts the leaf types. index / path: PACKFILE entry and part
    numbers, used to add the community names of the parts (names.archive_part).
    """
    root = folder if root is None else root
    layout = []
    types = collections.Counter() if types is None else types
    all_parts = parts(data)
    bank_name = None
    # visual effect packages: their parts are named from the effect header (effect.py)
    plain = [unwrap_zlib(p) if unwrap_zlib(p) is not None else p for p in all_parts]
    effect_names = effect.part_names(
        plain, lambda d: d[:4] != b"V000" and texture.decode(d) is not None)
    portraits = roster_portraits(plain)
    stage = stage_names(plain)
    model = model_names(plain)
    for k, part in enumerate(all_parts):
        prefix_k = "%s_%03d" % (prefix, k)
        label = names.archive_part(index, path + (k,), len(all_parts), counts) if index is not None else None
        label = label or effect_names.get(k) or portraits.get(k) or stage.get(k) \
            or identify.name(plain[k]) or None
        if not label and index is not None:
            label = names.system_part(index, path + (k,), plain[k])
        label = label or model.get(k)
        if not label and plain[k][:4] == b"RHG\0":
            # the graphics an animation moves: a run of N animations (.ags) followed by
            # a run of images (.rhg) pairs them in order (the button labels of the story
            # texts: 5 animations, then the 5 language strips)
            before = [p for p in plain[:k] if p]           # non-empty parts before
            images = 0
            while images < len(before) and before[-1 - images][:4] == b"RHG\0":
                images += 1
            anims = 0
            while images + anims < len(before) and before[-1 - images - anims][:4] == b"AGS\0":
                anims += 1
            # more images than animations: the image of an animation is followed by 5
            # more slots, one per language (empty in the Japanese release; in the
            # European one the Japanese slot is empty): they take the name of the last
            # animation of the run, and the language of their slot
            if anims:
                label = identify.ags_name(before[-1 - images - (anims - 1 - min(images, anims - 1))])
                lang = _language_slot(plain, k)
                if label and lang:
                    label += "_" + lang
        name = "%s_%s" % (prefix_k, label) if label else prefix_k
        # Sound bank = sample data + its "PPHD" header in the next part: written as
        # NAME.pbd + NAME.phd (the names vgmstream expects), both named after the data part
        is_body = k + 1 < len(all_parts) and all_parts[k + 1][:4] == b"PPHD"
        is_header = part[:4] == b"PPHD" and bank_name is not None
        if is_header:
            name, bank_name = bank_name, None
        elif is_body:
            if not label:
                name = "%s_sounds" % prefix_k
            bank_name = name
        if not part:
            layout.append(None)
            continue
        node = {}
        inflated = unwrap_zlib(part)
        if inflated is not None:
            types["zlib"] += 1
            node["zlib"] = True
            part = inflated
            if not inflated:
                layout.append(node)
                continue
        if depth + 1 < MAX_DEPTH and parts(part):
            node["arc"] = unpack(part, os.path.join(folder, name), prefix_k, depth + 1, types, png,
                                 index, path + (k,), root, counts + (len(all_parts),))
            node["name"] = name
        else:
            written = write_leaf(part, folder, name, types, png,
                                 "pbd" if is_body else "phd" if is_header else None, label)
            node["file"] = os.path.relpath(written, root).replace(os.sep, "/")
        layout.append(node)
    return layout
