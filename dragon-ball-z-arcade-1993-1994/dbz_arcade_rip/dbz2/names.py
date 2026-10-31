"""Names for the Dragon Ball Z 2 tilemaps that are not part of a stage.

Found by reading who loads each map code (trap #15 callers):
* endings: one cut-scene script per fighter, table 0x569C8 (interpreter 0x55890,
  command handlers 0x56914). Text commands (0x10, 0x26) load code+1 when the
  language is English (variable 0x4878F0), so even/odd pairs are JP/EN.
* quotes: table 0xFD2E (13 entries per fighter, routine 0xF2F0) and 0xFF5E
  (one per fighter, routine 0xF34A); code = Japanese, code + 1 = English.
  0x4151 is the empty window, 0x4152-0x4165 its opening animation (0xF760),
  0x4224-0x4227 its closing (0xF7B4).
* select screen background: two animations, lists at 0x5BC1E / 0x5BC40.
* logos: 0x40EB (Banpresto, routine 0x5A7AE), 0x40EE (Super Battle, 0x5BA98).
* the others below were named from what they show (and where they are loaded:
  fight start 0x52C0, select screen 0x5A85C / 0x5ABE4, hi-score 0x5CF9E, stage 5
  extra animation 0x5518).
"""
FIXED = {
    0x0000: "blank", 0x4000: "blank", 0x8000: "blank",
    0x000D: "hiscore_title", 0x000E: "hiscore_ranking_1-3", 0x000F: "hiscore_ranking_4-10",
    0x0010: "hiscore_ranking_1-3_b", 0x0011: "speed_lines_a", 0x0012: "speed_lines_b",
    0x0013: "gradient_orange", 0x001B: "sky_day", 0x001C: "sky_night", 0x001D: "frame_black",
    0x004F: "challenger_background", 0x0050: "a_challenger_shows_up",
    0x40EC: "lookout_sky_day", 0x40ED: "lookout_sky_night", 0x413D: "wasteland",
    0x8351: "congratulations_easy", 0x8352: "congratulations_normal", 0x8353: "congratulations_hard",
    0x8297: "picture_android_18", 0x82AE: "picture_cell", 0x8105: "crowd",
}
FIXED.update({0x0014 + i: f"difficulty_select_{i:02d}" for i in range(7)})
FIXED.update({0x40DD + i: f"clouds_night_{i:02d}" for i in range(14)})
FIXED.update({0x40B6 + i: f"switches_{i}" for i in range(4)})
FIXED.update({0x8256 + i: f"shenron_{i}" for i in range(6)})
FIXED.update({0x80EC + i: f"stage05_ground_extra_{i}" for i in range(7)})
FIXED.update({0x41E0: "quote_extra_00_jp", 0x41E1: "quote_extra_00_en"})
from .sprites import CHAR_NAMES

ENDING_SCRIPTS = 0x569C8
QUOTES = 0xFD2E
QUOTES_2 = 0xFF5E
SELECT_BG = (0x5BC1E, 0x5BC40)
# command -> (size in bytes, kind of map argument)
_ENDING_OPS = {
    0: (4, None), 1: (10, ("at", 4)), 2: (8, ("at", 2)), 3: (8, ("at", 2)), 4: (8, None),
    5: (10, None), 6: (12, None), 8: (6, None), 9: (4, None), 10: (4, None), 11: (16, None),
    13: (4, None), 14: (6, None), 15: (10, ("list", 1)), 16: (4, ("text", 2)),
    17: (10, ("list", 1)), 18: (10, ("list", 1)), 19: (10, ("list", 2)), 20: (4, None),
    21: (4, ("at", 2)), 22: (10, ("list", 1)), 24: (2, None), 25: (2, None), 26: (8, ("at", 2)),
    28: (12, None), 29: (2, ("fixed_text", 0x40F4)), 30: (2, ("fixed", 0x0048)), 32: (4, ("at", 2)),
    33: (4, ("at", 2)), 34: (4, ("at", 2)), 37: (4, None), 38: (4, ("text", 2)), 39: (2, None),
    42: (2, None), 43: (6, None), 44: (6, None),
}


def _w(m, a):
    return int.from_bytes(m[a:a + 2], "big")


def _l(m, a):
    return int.from_bytes(m[a:a + 4], "big")


def ending_codes(m, char):
    """-> list of (code, language or None) in script order."""
    p = _l(m, ENDING_SCRIPTS + 4 * char)
    out = []

    def add(code, lang=None):
        if (code, lang) not in out:
            out.append((code, lang))
    for _ in range(2000):
        op = _w(m, p)
        if op & 0x8000 or op not in _ENDING_OPS:
            break
        size, arg = _ENDING_OPS[op]
        if arg:
            kind, off = arg
            if kind == "at":
                add(_w(m, p + off))
            elif kind == "text":
                add(_w(m, p + off), "jp")
                add(_w(m, p + off) + 1, "en")
            elif kind == "fixed":
                add(off)
            elif kind == "fixed_text":
                add(off, "jp")
                add(off + 1, "en")
            elif kind == "list":
                q = _l(m, p + 6)       # +2 = task code, +6 = its list
                for _ in range(256):
                    c = _w(m, q)
                    if c == 0xFFFF:
                        break
                    add(c)
                    if off == 2:
                        add(_w(m, q + 2))
                    q += 2 * off + 2
        p += size
    return out


def screen_names(m):
    """-> {map code: name} for the maps used outside the stages."""
    names = {}

    def put(code, name):
        names.setdefault(code, name)
    for code, name in FIXED.items():
        put(code, name)
    put(0x40EB, "logo_banpresto")
    put(0x40EE, "logo_super_battle")
    put(0x4151, "quote_window")
    for i in range(20):
        put(0x4152 + i, f"quote_window_open_{i:02d}")
    for i in range(4):
        put(0x4224 + i, f"quote_window_close_{i}")
    for k, a in enumerate(SELECT_BG):
        i = 0
        while _w(m, a) < 0x8000 and i < 32:
            put(_w(m, a + 2), f"select_background_{'ab'[k]}_{i:02d}")
            a += 4
            i += 1
    # quotes: owner from the tables, JP = even code, EN = code + 1
    owner = {}
    for c, name in enumerate(CHAR_NAMES):
        p = _l(m, QUOTES + 4 * c)
        for k in range(26):
            v = _w(m, p + 2 * k)
            if v != 0xFFFF:
                owner.setdefault(v, name)
        owner.setdefault(_w(m, QUOTES_2 + 2 * c), name)
    count = {}
    for code in sorted(owner):
        name = owner[code]
        n = count.get(name, 0)
        count[name] = n + 1
        put(code, f"quote_{name}_{n:02d}_jp")
        put(code + 1, f"quote_{name}_{n:02d}_en")
    # endings (maps used by several endings: ending_common)
    per_char = [ending_codes(m, c) for c in range(len(CHAR_NAMES))]
    users = {}
    for c, codes in enumerate(per_char):
        for code, _ in codes:
            users.setdefault(code, set()).add(c)
    n = 0
    for codes in per_char:
        for code, lang in codes:
            if len(users[code]) > 1 and code not in names and code & 0x3FFF:
                put(code, f"ending_common_{n:02d}" + (f"_{lang}" if lang else ""))
                n += 1
    for c, name in enumerate(CHAR_NAMES):
        n = 0
        for code, lang in per_char[c]:
            if code in names or code & 0x3FFF == 0:
                continue
            if lang == "en":
                jp = names.get(code - 1, "")
                put(code, jp[:-3] + "_en" if jp.endswith("_jp") else f"ending_{name}_{n:02d}_en")
                continue
            put(code, f"ending_{name}_{n:02d}" + ("_jp" if lang else ""))
            n += 1
    return names
