"""
Names found from the content of a part, for the parts that neither the community lists
nor the effect headers (effect.py) name. Each rule is checked on real data; a part
that matches none keeps its number only (see unnamed.txt after an extraction).
"""
import re
import struct

_AGS_BLOCK = re.compile(rb"(\d\d_[\x21-\x7e]+?)\x00((?:[\x21-\x7e]+\x00)*)")
_GENERIC = {"open", "normal", "close", "main", "in", "out", "loop", "stop", "on", "off",
            "bg", "start", "end", "wait", "idle", "anime", "anim"}


def ags_name(part):
    """Name of a 2D animation (.ags, signature AGS\\0) from the names stored in it:
    each animation has a name ("00_open", "01_normal"...) followed by the names of the
    sprites it moves ("WINDOW", "BUTTON_01", "cursor"...). The name is made of the
    first sprite names (numbers dropped), or of the animation names when the sprites
    have none."""
    if part[:4] != b"AGS\0":
        return None
    sprites, anims = [], []
    for m in _AGS_BLOCK.finditer(part):
        anims.append(m.group(1).decode("ascii", "replace"))
        sprites += [x.decode("ascii", "replace") for x in m.group(2).split(b"\0") if x]

    def words(names, strip_number):
        out = []
        for raw in names:
            word = raw.lower()
            if strip_number:
                word = re.sub(r"^\d+_", "", word)
            word = re.sub(r"[^a-z0-9]+", "_", word)
            word = re.sub(r"(_?\d+)+$", "", word).strip("_")
            word = "_".join(t for t in word.split("_") if t not in _GENERIC)
            if word and not word[0].isdigit() and word not in _GENERIC \
                    and not any(word == w or word.startswith(w + "_") for w in out):
                out.append(word)
        return out

    chosen = words([x for x in sprites if not x[:1].isdigit()], False) or words(anims, True)
    if not chosen:      # names stored without the "NN_" animation number ("point_0"...)
        loose = [m.group(1).decode("ascii") for m in re.finditer(rb"([A-Za-z][A-Za-z0-9_]{2,})\x00", part)]
        chosen = words([x for x in loose if x not in ("AGS", "GHR", "SGA", "RHG")], False)
    if not chosen:      # only generic names ("01_normal"): kept as the developers wrote them
        chosen = []
        for raw in anims:
            word = re.sub(r"[^a-z0-9]+", "_", re.sub(r"^\d+_", "", raw.lower())).strip("_")
            if word and word not in chosen:
                chosen.append(word)
        if chosen and all(w.isdigit() for w in chosen):
            return "digits"     # one animation per digit, named "00_0", "01_1"...
    name = ""
    for word in chosen:              # up to 3 names, about 40 characters at most
        if name and (len(name) + len(word) > 40 or name.count("__") >= 2):
            break
        name += ("__" if name else "") + word
    return name.replace("__", "_") or None


def _font(part):
    """Bitmap font: u8 4 (4-bit pixels), u8 line height, u16 glyph count, 16 u16 =
    number of glyphs whose code point ends in hex digit 0..F (the glyphs are stored in
    these 16 groups, by code point inside a group), then one 10-byte record per glyph:
    u16 Unicode code point, u8 advance, u8 width, u8 height, u8 x, u8 y, u24 bitmap
    offset; then the bitmaps. The fonts of the system archives (entries 0..5)."""
    if len(part) < 0x40 or part[0] != 4 or not 8 <= part[1] <= 32:
        return None
    count = struct.unpack_from("<H", part, 2)[0]
    groups = struct.unpack_from("<16H", part, 4)
    if count < 32 or sum(groups) != count or 0x24 + 10 * count > len(part):
        return None
    pos = 0x24
    for digit, size in enumerate(groups):
        codes = [struct.unpack_from("<H", part, pos + 10 * k)[0] for k in range(size)]
        if any(c & 15 != digit for c in codes) or codes != sorted(codes):
            return None
        pos += 10 * size
    return "font_%dpx" % part[1]


def _text_table(part):
    """A text table (.tbl, see text.py) inside an archive."""
    from .formats import is_text
    return "text" if is_text(part) else None


def _story_script(part):
    """A BBQ script with dialogue (the chapter script of a language, inside the
    sm_txt_chNN archives of the second text set)."""
    if part[:8] != b".BBQ1.00":
        return None
    from . import bbq
    events = list(bbq.calls(part))
    speaker, line = bbq.dialogue_functions(events)
    if sum(1 for name, _ in events if name == line) >= 5:
        return "story_script"
    return None


def _geometry(part):
    """Stage / board geometry (.map, see texture.map_textures)."""
    return "geometry" if part[:4] == b"\x60\x0b\x9a\x7e" else None


def _bbq_sections(part):
    count = struct.unpack_from("<I", part, 0x14)[0] if len(part) >= 0x18 else 0
    if part[:8] != b".BBQ1.00" or not 1 <= count <= 16 or 0x18 + 20 * count > len(part):
        return None
    return [struct.unpack_from("<5I", part, 0x18 + 20 * k) for k in range(count)]


def _small_script(part):
    """BBQ scripts with no code, told apart by their section tables:
    the two small ones found as 13935 / 13936 and again in every sm_txt_chNN archive
    (parts 5 / 4, the same bytes), and part 1 of those archives, laid out like the
    chNN_3 scripts (the Dragon Walker module loads 13273 + 3 x map as the map's
    script: audio_map.py)."""
    sections = _bbq_sections(part)
    if not sections:
        return None
    kinds = [s[0] for s in sections]
    if kinds == [2, 3, 5, 6] and sections[2][2] == 1 and sections[0][2] == 1:
        return {180: "small_script_1", 24: "small_script_2"}.get(sections[2][4])
    if kinds == [2, 3, 5, 6] and sections[0][2] == 2 and sections[2][2] == 2 \
            and sections[3][4] == 56:
        return "map_script"
    return None


def _shadow(part):
    """A texture that is a black disc whose alpha fades to the edge: a drop shadow
    (one in every sm_txt_chNN archive)."""
    from . import texture
    if part[:4] in (b"RHG\0", b"AGS\0") or len(part) > 0x10000:
        return None
    images = texture.decode(part)
    if not images or len(images) != 1:
        return None
    w, h, px = images[0]
    if w != h or w < 16 or any(px[i] or px[i + 1] or px[i + 2] for i in range(0, len(px), 4)):
        return None
    alpha = lambda x, y: px[(y * w + x) * 4 + 3]
    return "shadow" if alpha(w // 2, h // 2) > 200 and alpha(0, 0) < 32 else None


def _named_script(part):
    """BBQ scripts told apart by their own strings: the staff roll (calls written as
    "staff_r_color( 0, 0, 60 )"...) and the field event script of the story mode (its
    debug message フィールドイベント開始, "field event start")."""
    if part[:8] != b".BBQ1.00":
        return None
    if b"staff_r_" in part:
        return "staff_roll_script"
    if "フィールドイベント開始".encode("shift_jis") in part:
        return "field_event_script"
    return None


RULES = (_font, _text_table, _story_script, _named_script, _geometry, ags_name, _small_script, _shadow)


def name(part):
    """Descriptive name of a part from its content, or None."""
    for rule in RULES:
        found = rule(part)
        if found:
            return found
    return None
