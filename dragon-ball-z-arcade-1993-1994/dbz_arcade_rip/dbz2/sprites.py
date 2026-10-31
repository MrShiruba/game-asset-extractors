"""Fighters and sprite frames of Dragon Ball Z 2.

Reverse-engineered from the 68000 program (a9e.9e / a9f.9f):
* character descriptor table at 0x59AC, 10 entries of 32 bytes, +4 = frame bank.
  Order (checked against the in-game name list): Goku (SSJ), Gohan, Vegeta, Trunks,
  Mr. Satan, Piccolo, No.20, No.18, No.16, Cell.
* frame bank = 416 longs (top byte = piece count, low 24 bits = frame address,
  0x00FFFFFF = unused). The shared object bank at 0x8E900 has 832.
* frame = 1 header word + pieces of 8 bytes (routine 0x854A):
    byte 0 : bit 7 set, bits 0-1 log2(width), bits 2-3 log2(height),
             bit 4 flip X, bit 5 flip Y
    byte 1 : colour offset added to the object colour (0-7)
    word   : sprite code (16x16 tile index, K053247 Morton sub-tile order)
    word   : Y (centre, upwards), word : X (centre, 0x80 = origin)
  A 2-byte word with bit 15 clear inside the list ends the first group: the
  pieces after it form a second group drawn with that word as priority
  (fighters: aura/attached effect, routine 0x82C0).
* colours (routine 0x5AEC): 4 colour sets per fighter, 8 palettes each,
  pointer table 0x4FB38 + 4*(char*4 + set). Sprite palette RAM in a fight:
    0-7 player 1 set, 8-15 player 2 set, 16-21 common (0x4F5A0),
    22-24 stage (0x4F640 + 4*stage).
  The set (0-3) is picked at the select screen (variables 0x48768C / 0x48768E);
  a mirror match forces a different one.
"""
import numpy as np

from ..gfx import xrgb555_to_rgb

DESCRIPTORS = 0x59AC
COLOUR_SETS = 0x4FB38
COMMON_PALETTES = 0x4F5A0
STAGE_SPRITE_PALETTES = 0x4F640
SHARED_BANK = 0x8E900
CHAR_NAMES = ["goku", "gohan", "vegeta", "trunks", "satan",
              "piccolo", "android_20", "android_18", "android_16", "cell"]


class FrameRenderer2:
    def __init__(self, maincpu, blocks):
        self.m = maincpu
        self.blocks = blocks

    def w(self, a):
        return int.from_bytes(self.m[a:a + 2], "big")

    def l(self, a):
        return int.from_bytes(self.m[a:a + 4], "big")

    def palettes(self, addr, n):
        return [xrgb555_to_rgb([self.w(addr + 32 * p + 2 * k) for k in range(16)]) for p in range(n)]

    # -- tables ---------------------------------------------------------------
    def characters(self):
        out = []
        for i, name in enumerate(CHAR_NAMES):
            sets = [self.l(COLOUR_SETS + 4 * (i * 4 + s)) for s in range(4)]
            out.append({"index": i, "name": name, "bank": self.l(DESCRIPTORS + 32 * i + 4),
                        "colour_sets": sets})
        return out

    def frame_table(self, bank, slots=416):
        frames = []
        for s in range(slots):
            v = self.l(bank + 4 * s)
            if v == 0x00FFFFFF:
                continue
            n, addr = v >> 24, v & 0xFFFFFF
            if n == 0 or addr >= len(self.m):
                continue
            frames.append((s, n, addr))
        return frames

    # -- rendering ------------------------------------------------------------
    def _piece(self, code, w, h):
        blk = self.blocks[(code >> 6) % len(self.blocks)]
        xa = (code & 1) | ((code >> 1) & 2) | ((code >> 2) & 4)
        ya = ((code >> 1) & 1) | ((code >> 2) & 2) | ((code >> 3) & 4)
        out = np.empty((h * 16, w * 16), dtype=np.uint8)
        for y in range(h):
            cy = (ya + y) & 7
            for x in range(w):
                cx = (xa + x) & 7
                out[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = blk[cy * 16:cy * 16 + 16, cx * 16:cx * 16 + 16]
        return out

    def pieces(self, addr, count):
        """-> list of (x, y, pens, colour offset, group)."""
        p, group, out = addr + 2, 0, []
        for _ in range(count):
            if not self.m[p] & 0x80:      # group separator (priority word)
                group += 1
                p += 2
            attr, coff, code = self.m[p], self.m[p + 1], self.w(p + 2)
            y, x = self.w(p + 4), self.w(p + 6)
            p += 8
            y = y - 0x10000 if y & 0x8000 else y
            x = x - 0x10000 if x & 0x8000 else x
            w, h = 1 << (attr & 3), 1 << ((attr >> 2) & 3)
            img = self._piece(code, w, h)
            if attr & 0x10:
                img = img[:, ::-1]
            if attr & 0x20:
                img = img[::-1, :]
            out.append((x - 0x80 - w * 8, -y - h * 8, img, coff & 7, group))
        return out

    def render(self, addr, count):
        """-> (pens, ox, oy, colour offsets used). Pens carry the colour offset in
        bits 4-6 (index = offset*16 + pen), so one 128-colour palette covers a frame."""
        pcs = self.pieces(addr, count)
        if not pcs:
            return np.zeros((1, 1), np.uint8), 0, 0, []
        x0 = min(p[0] for p in pcs)
        y0 = min(p[1] for p in pcs)
        x1 = max(p[0] + p[2].shape[1] for p in pcs)
        y1 = max(p[1] + p[2].shape[0] for p in pcs)
        canvas = np.zeros((y1 - y0, x1 - x0), np.uint8)
        # first piece of a group on top; later groups (priority 0) above the first
        order = sorted(range(len(pcs)), key=lambda i: (-pcs[i][4], i))
        for i in reversed(order):
            px, py, img, coff, _ = pcs[i]
            sub = canvas[py - y0:py - y0 + img.shape[0], px - x0:px - x0 + img.shape[1]]
            mask = img != 0
            sub[mask] = img[mask] | (coff << 4)
        return canvas, -x0, -y0, sorted({p[3] for p in pcs})


def palette128(pals):
    """8 palettes of 16 -> flat list of 128 colours."""
    out = [c for p in pals[:8] for c in p]
    return out + [(0, 0, 0)] * (128 - len(out))
