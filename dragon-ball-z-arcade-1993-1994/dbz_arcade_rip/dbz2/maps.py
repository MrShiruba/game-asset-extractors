"""Tilemaps of Dragon Ball Z 2 (K056832 8x8 pages and K053936 PSAC 16x16 pages).

Reverse-engineered from the 68000 program:
* trap #15 (handler 0x150A) loads a map, d0 = kind << 14 | index:
    table 0x529A8 + 8*kind : [pointer table, destination]
      kind 0 / 3 -> 0x490000  K056832 (page chosen by trap #9), 81 maps
      kind 1     -> 0x500000  PSAC "back" layer  (gfx ds-p01/ds-p02 = roztiles1)
      kind 2     -> 0x508000  PSAC "front" layer (gfx ds-p03/ds-p04 = roztiles0)
* map data = 8-byte header + long-word RLE (same coding as the first game):
    header word 0 negative : a whole 64x32 page
    otherwise              : a patch, x = word 0, y = word 1 (cells), width = word 2;
                             cells are written row by row (handler 0x1574)
* trap #12 (handler 0x1498) loads a counted palette block with the SAME code:
    table 0x540FC + 8*kind : [pointer table, RAM buffer]; block = count-1 word + 16 colours
  every caller issues trap #15 and trap #12 with the same d0, so map N uses palette N.
* cells: K056832 = attr word (bits 0-1 flip X/Y, bits 4-7 palette) + tile word;
         PSAC    = attr word (bits 0-3 palette, bit 7 flip X, bit 6 flip Y) + tile word.
"""
import numpy as np

from ..gfx import decode_k056832, decode_psac, xrgb555_to_rgb

MAP_DIR = 0x529A8
PAL_DIR = 0x540FC
COUNTS = {0: 81, 1: 552, 2: 852}
# folder names: K056832 = fixed 8x8 tile layer, K053936 (PSAC) = rotate/zoom layers
KIND_NAMES = {0: "fixed_layer", 1: "zoom_layer_back", 2: "zoom_layer_front"}
# K056832 test mode / logos / HUD (other names: names.py)
K056832_NAMES = {1: "test_color_check", 2: "test_screen_check", 3: "test_port_check",
                 4: "test_sound_check", 5: "test_obj_check", 6: "test_bg_check",
                 7: "test_psac_a_check", 8: "test_psac_b_check", 9: "test_menu",
                 10: "title_banpresto", 11: "title_cobra_team", 12: "hud"}


class Maps:
    def __init__(self, maincpu, tile_region=None, psac=None):
        self.m = maincpu
        self._tiles = {}
        self._src = {0: tile_region}
        if psac is not None:
            self._src[1], self._src[2] = psac[1], psac[0]  # back = roztiles1, front = roztiles0

    def w(self, a):
        return int.from_bytes(self.m[a:a + 2], "big")

    def l(self, a):
        return int.from_bytes(self.m[a:a + 4], "big")

    def tiles(self, kind):
        kind = 0 if kind == 3 else kind
        if kind not in self._tiles:
            src = self._src[kind]
            self._tiles[kind] = decode_k056832(src) if kind == 0 else decode_psac(src)
        return self._tiles[kind]

    # -- data -------------------------------------------------------------------
    def address(self, code):
        kind, idx = (code >> 14) & 3, code & 0x3FFF
        return self.l(self.l(MAP_DIR + 8 * kind) + 4 * idx)

    def palette_address(self, code):
        kind, idx = (code >> 14) & 3, code & 0x3FFF
        return self.l(self.l(PAL_DIR + 8 * kind) + 4 * idx)

    def _rle(self, p):
        """-> list of (w0, w1) cells, and the run sizes (for patch row handling)."""
        m, out, runs = self.m, [], []
        while True:
            c = m[p]
            n = c & 0x7F
            if c == 0 or (c & 0x80 and n == 0):
                break
            if c & 0x80:
                vals = [(self.w(p + 4 * k), self.w(p + 4 * k + 2)) for k in range(n)]
                p += 4 * n
            else:
                vals = [(self.w(p), self.w(p + 2))] * n
                p += 4
            out += vals
            runs.append(n)
        return out

    def load(self, code):
        """-> dict(x, y, cols, rows, cells uint16 (rows, cols, 2), full)"""
        a = self.address(code)
        cells = self._rle(a + 8)
        if self.w(a) & 0x8000:
            arr = np.zeros((32 * 64, 2), np.uint16)
            n = min(len(cells), 32 * 64)
            if n:
                arr[:n] = cells[:n]
            return {"x": 0, "y": 0, "cols": 64, "rows": 32, "cells": arr.reshape(32, 64, 2), "full": True}
        x, y, cols = self.w(a), self.w(a + 2), max(1, self.w(a + 4))
        rows = max(1, (len(cells) + cols - 1) // cols)
        arr = np.zeros((rows * cols, 2), np.uint16)
        if cells:
            arr[:len(cells)] = cells
        return {"x": x, "y": y, "cols": cols, "rows": rows, "cells": arr.reshape(rows, cols, 2), "full": False}

    def palette256(self, code):
        """Counted palette block -> 256 RGB (palette*16 + pen), last palette repeated."""
        a = self.palette_address(code)
        n = min(16, self.w(a) + 1)
        pals = [xrgb555_to_rgb([self.w(a + 2 + 32 * p + 2 * k) for k in range(16)]) for p in range(n)]
        while len(pals) < 16:
            pals.append(pals[-1])
        return [c for p in pals for c in p]

    # -- drawing ----------------------------------------------------------------
    def render(self, kind, cells):
        """cells (rows, cols, 2) -> pens with the palette in the high nibble."""
        kind = 0 if kind == 3 else kind
        tiles = self.tiles(kind)
        size = 8 if kind == 0 else 16
        rows, cols = cells.shape[:2]
        img = np.zeros((rows * size, cols * size), np.uint8)
        n = len(tiles)
        for y in range(rows):
            for x in range(cols):
                w0, w1 = int(cells[y, x, 0]), int(cells[y, x, 1])
                if kind == 0:
                    t = tiles[w1 % n]
                    fx, fy, col = w0 & 1, w0 & 2, (w0 >> 4) & 15
                else:
                    code = w1 & 0x7FFF
                    if code >= n:
                        continue
                    t = tiles[code]
                    fx, fy, col = w0 & 0x80, w0 & 0x40, w0 & 15
                if fx:
                    t = t[:, ::-1]
                if fy:
                    t = t[::-1, :]
                img[y * size:(y + 1) * size, x * size:(x + 1) * size] = np.where(t != 0, t | (col << 4), 0)
        return img

    def tiles_sheet(self, kind, cell_lists, per_row=None):
        """Every (tile, palette) used by the given cell arrays, ROM order, unflipped."""
        kind = 0 if kind == 3 else kind
        tiles = self.tiles(kind)
        size = 8 if kind == 0 else 16
        per_row = per_row or (32 if kind == 0 else 16)
        used = set()
        for cells in cell_lists:
            for w0, w1 in cells.reshape(-1, 2):
                w0, w1 = int(w0), int(w1)
                if kind == 0:
                    used.add((w1 % len(tiles), (w0 >> 4) & 15))
                else:
                    used.add((w1 & 0x7FFF, w0 & 15))
        used = sorted(u for u in used if u[0] < len(tiles) and tiles[u[0]].any())
        rows = (len(used) + per_row - 1) // per_row
        img = np.zeros((max(rows, 1) * size, per_row * size), np.uint8)
        for i, (t, col) in enumerate(used):
            y, x = divmod(i, per_row)
            img[y * size:(y + 1) * size, x * size:(x + 1) * size] = np.where(tiles[t] != 0, tiles[t] | (col << 4), 0)
        return img
