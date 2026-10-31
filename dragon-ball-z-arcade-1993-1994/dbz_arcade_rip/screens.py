"""Fixed screens drawn by the K056832 tilemap chip: HUD, title, logos, select
screen, hi-score table, endings, test mode.

Reverse-engineered from the 68000 program:
* maps are compressed with the same long-word RLE as the stage maps
  (routine 0x5C3A -> one 64x32 page of 8x8 tiles, 2 words per cell:
  attr (bits 0-1 flip X/Y, bits 4-7 palette), tile code)
* register 0x4CC033 selects the page being written: bank 9 -> page shown by
  layer 0, bank 0 -> page shown by layer 1. Layer 1 always uses palette RAM
  192+ (buffer 0x489D72) ; layer 0 uses 192+ or 224+ (buffer 0x489F74)
  depending on K053251 register 10 (0x36 / 0x37).
* each screen routine loads its palette block next to its map: the pairs
  below were found that way and checked visually.
"""
import numpy as np

from .gfx import decode_k056832, xrgb555_to_rgb
from .stages import decompress

# name, compressed map, palette block (counted palette list)
SCREENS = [
    ("hud",                 0xB401C, 0x21986),
    ("title_banpresto",     0xB1514, 0x20F52),
    ("title_cobra_team",    0xB1834, 0x20F74),
    ("title_logo",          0xB1E3C, 0x21076),
    ("title_copyright",     0xB260C, 0x21076),
    ("select_background",   0xB29F0, 0x21844),
    ("select_vs",           0xB275C, 0x21642),
    ("select_boxes",        0xB1334, 0x21642),
    ("hiscore_ranking",     0xB4508, 0x21540),
    ("test_menu",           0xB4184, 0x210B8),
    ("test_port_check",     0xB6730, 0x210B8),
    ("test_color_check",    0xB77B0, 0x210B8),
    ("test_screen_check",   0xB4EAC, 0x210B8),
    ("test_sound_check",    0xB7644, 0x210B8),
    ("test_obj_check",      0xB6F30, 0x210B8),
    ("test_bg_check",       0xB7088, 0x210B8),
    ("test_psac_a_check",   0xB73DC, 0x210B8),
    ("test_psac_b_check",   0xB7174, 0x210B8),
]
# endings: per character, [text page, picture page]; JP and EN text tables
ENDINGS_JP = 0xA9C1C
ENDINGS_EN = 0xA9C6C
ENDING_PALETTES = 0x1EBBC   # per character: (text palette block, picture palette block)
# fighters sharing an ending: name it after the group
ENDING_NAMES = {"recoome": "ginyu_force", "burter": "ginyu_force", "ginyu": "ginyu_force",
                "frieza_stage1": "frieza", "frieza_stage2": "frieza", "goku_super_saiyan": "goku"}


class ScreenRenderer:
    def __init__(self, maincpu, tile_region):
        self.m = maincpu
        self.tiles = decode_k056832(tile_region)

    def l(self, a):
        return int.from_bytes(self.m[a:a + 4], "big")

    def w(self, a):
        return int.from_bytes(self.m[a:a + 2], "big")

    def palette256(self, block):
        """Counted palette block -> 256 RGB entries (palette*16 + pen)."""
        n = min(16, self.w(block) + 1)
        pals = [xrgb555_to_rgb([self.w(block + 2 + 32 * p + 2 * k) for k in range(16)]) for p in range(n)]
        while len(pals) < 16:
            pals.append(pals[-1])
        return [c for p in pals for c in p]

    def page_cells(self, src):
        data = decompress(self.m, src, limit=0x800)[:0x2000].ljust(0x2000, b"\0")
        return np.frombuffer(data, ">u2").reshape(-1, 2)

    def tiles_sheet(self, src, per_row=32):
        """Every (tile, palette) the page uses, in ROM tile order, unflipped."""
        used = sorted({(int(code), (int(attr) >> 4) & 15) for attr, code in self.page_cells(src)})
        n = len(self.tiles)
        used = [u for u in used if u[0] < n and self.tiles[u[0]].any()]
        rows = (len(used) + per_row - 1) // per_row
        img = np.zeros((max(rows, 1) * 8, per_row * 8), np.uint8)
        for i, (t, col) in enumerate(used):
            y, x = divmod(i, per_row)
            tile = self.tiles[t]
            img[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = np.where(tile != 0, tile | (col << 4), 0)
        return img

    def page(self, src):
        data = decompress(self.m, src, limit=0x800)[:0x2000].ljust(0x2000, b"\0")
        cells = np.frombuffer(data, ">u2").reshape(-1, 2)
        img = np.zeros((256, 512), np.uint8)
        n = len(self.tiles)
        for i, (attr, code) in enumerate(cells):
            t = self.tiles[int(code) % n]
            if attr & 1:
                t = t[:, ::-1]
            if attr & 2:
                t = t[::-1, :]
            y, x = divmod(i, 64)
            col = ((int(attr) >> 4) & 15) << 4
            img[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = np.where(t != 0, t | col, 0)
        return img

    def all_screens(self, char_names):
        """-> list of (name, pens of the whole 512x256 page as stored, palette256, map address).
        The arcade only shows the left 384x256 (MAME visarea); the rest is kept as-is."""
        out = [(name, self.page(src), self.palette256(pal), src) for name, src, pal in SCREENS]
        seen = set()
        for c, cname in enumerate(char_names):
            cname = ENDING_NAMES.get(cname, cname)
            text_pal = self.l(ENDING_PALETTES + 8 * c)
            pic_pal = self.l(ENDING_PALETTES + 8 * c + 4)
            items = [(f"ending_{cname}_picture", self.l(ENDINGS_JP + 8 * c + 4), pic_pal),
                     (f"ending_{cname}_text_jp", self.l(ENDINGS_JP + 8 * c), text_pal),
                     (f"ending_{cname}_text_en", self.l(ENDINGS_EN + 8 * c), text_pal)]
            for name, src, pal in items:
                if (src, pal) in seen:
                    continue  # several fighters share the same ending
                seen.add((src, pal))
                out.append((name, self.page(src), self.palette256(pal), src))
        return out


# ---- tile "glyphs": small tile blocks blitted by routine 0x236E -------------------
GLYPH_TABLE = 0xFD8A        # pointers -> [width-1, height-1, tile codes...]
GLYPH_STRINGS = 0xFA3E      # top byte = colour attr, low 24 bits -> x, y, glyph ids..., 0xFFFF
FACE_GLYPHS = 0xF718        # per character: select/hi-score face glyph id
FACE_PALETTES = 0x21A88     # per character*2 (+1 = P2): one palette
HUD_PALETTES = 0x21986      # palette block loaded in fights (strings use it)


class GlyphRenderer(ScreenRenderer):
    def glyphs(self):
        """-> list of (id, pens with palette in high nibble = 0)."""
        out = []
        i = 0
        while True:
            p = self.l(GLYPH_TABLE + 4 * i)
            if p < 0x400 or p >= len(self.m):
                break
            w, h = self.m[p] + 1, self.m[p + 1] + 1
            if w > 64 or h > 32:
                break
            img = np.zeros((h * 8, w * 8), np.uint8)
            for k in range(w * h):
                code = self.w(p + 2 + 2 * k) % len(self.tiles)
                y, x = divmod(k, w)
                img[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = self.tiles[code]
            out.append((i, img))
            i += 1
        return out

    def string_colours(self):
        """glyph id -> palette index (from the strings that display it)."""
        cols = {}
        i = 0
        while i < 512:
            v = self.l(GLYPH_STRINGS + 4 * i)
            p = v & 0xFFFFFF
            if p < 0x400 or p >= len(self.m):
                break
            colour = (v >> 24) >> 4
            q = p + 2
            for _ in range(128):
                g = self.w(q)
                if g & 0x8000:
                    break
                cols.setdefault(g, colour)
                q += 2
            i += 1
        return cols

    def faces(self, char_names):
        """-> list of (char_name, glyph id, palette P1, palette P2) for the select/hi-score faces."""
        out = []
        for c, name in enumerate(char_names):
            g = self.w(FACE_GLYPHS + 2 * c)
            p1 = xrgb555_to_rgb([self.w(self.l(FACE_PALETTES + 8 * c) + 2 * k) for k in range(16)])
            p2 = xrgb555_to_rgb([self.w(self.l(FACE_PALETTES + 8 * c + 4) + 2 * k) for k in range(16)])
            out.append((name, g, p1, p2))
        return out
