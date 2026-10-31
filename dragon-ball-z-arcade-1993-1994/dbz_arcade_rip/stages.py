"""Stage backgrounds: the two K053936 (PSAC) rotate/zoom layers of every stage.

Reverse-engineered from the 68000 program (stage init at 0x4F28):
* stage number = word at 0x486434 (also selects music 1+stage and sprite palette set)
* 0x21D18 + 8*stage : two pointers to counted palette blocks
      [0] -> palette RAM block 1 (layer at 0x500000, gfx 222a08, K053251 CI1)
      [1] -> palette RAM block 2 (layer at 0x508000, gfx 222a09, K053251 CI2)
* 0xB7D00 + 16*stage : compressed map for 0x500000, compressed map for 0x508000, ...
* decompressor at 0x5C72 (long-word RLE): control byte c at the current position,
      c == 0     : end
      c & 0x80   : copy (c & 0x7F) longs verbatim (the first long starts AT c)
      else       : repeat the long that starts at c, c times
* map = 64x32 cells of 2 words: w0 bits 0-3 colour, bit 7 flip X ; w1 & 0x7FFF tile.
"""
import numpy as np

from .gfx import decode_psac, xrgb555_to_rgb

STAGE_PALETTES = 0x21D18
STAGE_MAPS = 0xB7D00
ANIM_TABLE = 0xD0D44
NUM_STAGES = 9
MAP_W, MAP_H = 64, 32


def decompress(m, src, limit=0x4000):
    out = bytearray()
    p = src
    while len(out) < limit * 4:
        c = m[p]
        if c == 0:
            break
        n = c & 0x7F
        if c & 0x80:
            if n == 0:
                break
            out += m[p:p + 4 * n]
            p += 4 * n
        else:
            out += m[p:p + 4] * n
            p += 4
    return bytes(out)


class StageRenderer:
    def __init__(self, maincpu, psac0_rom, psac1_rom):
        self.m = maincpu
        # layer at 0x508000 uses roztiles0 (222a09), layer at 0x500000 uses roztiles1 (222a08)
        self.tiles = {0x508000: decode_psac(psac0_rom), 0x500000: decode_psac(psac1_rom)}

    def l(self, a):
        return int.from_bytes(self.m[a:a + 4], "big")

    def w(self, a):
        return int.from_bytes(self.m[a:a + 2], "big")

    def palettes(self, block):
        n = self.w(block) + 1
        return [xrgb555_to_rgb([self.w(block + 2 + 32 * p + 2 * k) for k in range(16)]) for p in range(n)]

    def cells_image(self, data, cols, rows, which):
        """Raw map cells (2 words each) -> pens (rows*16 x cols*16), colour in high nibble."""
        need = cols * rows * 4
        cells = np.frombuffer(data[:need].ljust(need, b"\0"), ">u2").reshape(-1, 2)
        tiles = self.tiles[which]
        img = np.zeros((rows * 16, cols * 16), np.uint8)
        for i, (w0, w1) in enumerate(cells):
            t = int(w1) & 0x7FFF
            if t >= len(tiles):
                continue
            tile = tiles[t]
            if w0 & 0x80:
                tile = tile[:, ::-1]
            y, x = divmod(i, cols)
            col = (int(w0) & 0xF) << 4
            img[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = np.where(tile != 0, tile | col, 0)
        return img

    def layer(self, stage, which):
        """which = 0x500000 or 0x508000 -> (pens uint8 512x1024 with colour in high nibble)."""
        k = 0 if which == 0x500000 else 1
        data = decompress(self.m, self.l(STAGE_MAPS + 16 * stage + 4 * k))
        return self.cells_image(data, MAP_W, MAP_H, which)

    def animations(self, stage):
        """Animated tile patches of a stage (table 0xD0D44, applied by routine 0x5136).
        Record (18 bytes): layer (0 = 0x500000 back, else 0x508000 front), x, y,
        cols-1, rows-1, timing group, frame pointer table, frame count.
        -> list of dicts with the unique frames (pens) in play order."""
        p = self.l(ANIM_TABLE + 4 * stage)
        out = []
        if p == 0xFFFFFFFF or p >= len(self.m):
            return out
        while self.w(p) < 0x8000 and len(out) < 32:
            layer = 0x500000 if self.w(p) == 0 else 0x508000
            x, y = self.w(p + 2), self.w(p + 4)
            cols, rows = self.w(p + 6) + 1, self.w(p + 8) + 1
            table, count = self.l(p + 12), self.w(p + 16)
            ptrs = [self.l(table + 4 * k) for k in range(count)]
            unique = list(dict.fromkeys(ptrs))  # ping-pong sequences repeat frames
            frames = [self.cells_image(self.m[a:a + cols * rows * 4], cols, rows, layer) for a in unique]
            out.append({"layer": "back" if layer == 0x500000 else "front", "which": layer,
                        "x": x, "y": y, "cols": cols, "rows": rows,
                        "sequence": [unique.index(a) for a in ptrs], "frames": frames,
                        "addresses": [hex(a) for a in unique]})
            p += 18
        return out

    def tiles_sheet(self, stage, which, per_row=16):
        """Every (tile, colour) the layer and its animations use, in ROM tile order,
        drawn unflipped with its colour -> pens sheet (16x16 tiles, per_row wide)."""
        k = 0 if which == 0x500000 else 1
        datas = [decompress(self.m, self.l(STAGE_MAPS + 16 * stage + 4 * k))[:MAP_W * MAP_H * 4]]
        for a in self.animations(stage):
            if a["which"] == which:
                n = a["cols"] * a["rows"] * 4
                datas += [self.m[int(addr, 16):int(addr, 16) + n] for addr in a["addresses"]]
        used = set()
        for data in datas:
            cells = np.frombuffer(data[:len(data) // 4 * 4], ">u2").reshape(-1, 2)
            for w0, w1 in cells:
                used.add((int(w1) & 0x7FFF, int(w0) & 0xF))
        tiles = self.tiles[which]
        used = sorted(u for u in used if u[0] < len(tiles) and tiles[u[0]].any())
        rows = (len(used) + per_row - 1) // per_row
        img = np.zeros((max(rows, 1) * 16, per_row * 16), np.uint8)
        for i, (t, col) in enumerate(used):
            y, x = divmod(i, per_row)
            tile = tiles[t]
            img[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = np.where(tile != 0, tile | (col << 4), 0)
        return img

    def layer_palette(self, stage, which):
        k = 0 if which == 0x500000 else 1
        pals = self.palettes(self.l(STAGE_PALETTES + 8 * stage + 4 * k))
        flat = []
        for c in range(16):
            p = pals[c] if c < len(pals) else pals[-1]
            flat.extend(p)
        return flat  # 256 colours: index = colour*16 + pen


def save_layer(path, pens, flat_palette):
    """Indexed 256-colour PNG (index = colour*16 + pen); every pen 0 is transparent."""
    from PIL import Image
    img = Image.fromarray(pens, mode="P")
    pal = list(flat_palette[:256])
    pal += [(0, 0, 0)] * (256 - len(pal))
    img.putpalette([v for c in pal for v in c])
    alpha = bytes(0 if i % 16 == 0 else 255 for i in range(256))
    img.save(path, transparency=alpha, optimize=True)
