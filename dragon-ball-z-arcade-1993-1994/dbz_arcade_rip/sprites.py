"""Full-frame sprite reconstruction from the 68000 program data.

Reverse-engineered from the `dbz` program ROM (222b11/222b12):

* Character descriptor table at 0x5AEE, 10 entries of 32 bytes:
    +0x04 long  frame bank (normal moves)
    +0x14 long  frame bank (special moves) or 0xFFFFFFFF
* A frame bank starts with a table of longs: top byte = piece count,
  low 24 bits = frame address (0x00FFFFFF = unused slot).
  The table ends where the first frame data begins.
* A frame = 1 header word + N pieces of 3 words (routine at 0x801C):
    w0 : sprite code (16x16 tile index, K053247 Morton sub-tile order)
    w1 : bits 0-11 X (0x80 = origin), bit 13 flip X, bits 14-15 log2(width)
    w2 : bits 0-11 Y (upwards),       bit 13 flip Y, bits 14-15 log2(height)
  Coordinates are the *centre* of the piece (K053247 behaviour).
* Player palettes: pointer table at 0x1F856, entry 20+2*char (P1 colours)
  and 21+2*char (P2 colours); each points to 16 xRGB555 words.
"""
import numpy as np

from .gfx import xrgb555_to_rgb

DESCRIPTORS = 0x5AEE
PALETTE_TABLE = 0x1F856
# Palette slots used on the fighter's body (script command 0x6?nn adds nn to the colour):
# only Goku and SSJ Goku do it, with +2 = Kaioken. v1/v2 are otherwise used by effects.
BODY_PALETTES = {"goku": {"kaioken": 2}, "goku_super_saiyan": {"kaioken": 2}}
PALETTE_USAGE = ["v0: body", "v1: most effects of this fighter (relative colour +1)",
                 "v2: some effects (+2); Kaioken body for Goku / SSJ Goku", "v3: no use found"]

CHAR_NAMES = [
    "goku", "vegeta", "gohan", "piccolo", "recoome",
    "burter", "ginyu", "frieza_stage1", "frieza_stage2", "goku_super_saiyan",
]

_XO = [0, 1, 4, 5, 16, 17, 20, 21]


class FrameRenderer:
    def __init__(self, maincpu, blocks):
        self.m = maincpu
        self.blocks = blocks  # (nblocks, 128, 128) pens, from gfx.morton_blocks

    def w(self, a):
        return int.from_bytes(self.m[a:a + 2], "big")

    def l(self, a):
        return int.from_bytes(self.m[a:a + 4], "big")

    # -- tables ---------------------------------------------------------------
    def characters(self):
        out = []
        starts = sorted({self.l(PALETTE_TABLE + 4 * (20 + k)) for k in range(2 * len(CHAR_NAMES))})
        for i, name in enumerate(CHAR_NAMES):
            d = DESCRIPTORS + 32 * i
            bank = self.l(d + 4)
            special = self.l(d + 0x14)
            p1 = self.l(PALETTE_TABLE + 4 * (20 + 2 * i))
            p2 = self.l(PALETTE_TABLE + 4 * (21 + 2 * i))
            # each player colour set is a run of palettes: base, effects, alternates
            # (Kaioken red...) ; it ends where the next set starts
            nxt = [a for a in starts if a > p1]
            count = 4  # the game always loads 4 consecutive palettes per player (routine 0x5CAC)
            out.append({
                "index": i, "name": name, "bank": bank,
                "special_bank": special if special < len(self.m) else None,
                "palette_p1": p1, "palette_p2": p2,
                "variants_p1": [p1 + 32 * k for k in range(count)],
                "variants_p2": [p2 + 32 * k for k in range(count)],
            })
        return out

    def frame_table(self, bank):
        """-> list of (slot, count, address) for a frame bank."""
        frames, a, first = [], bank, None
        while first is None or a < first:
            if a + 4 > len(self.m) or a - bank > 0x4000:
                break
            v = self.l(a)
            if v != 0x00FFFFFF:
                n, addr = v >> 24, v & 0xFFFFFF
                if n == 0 or addr >= len(self.m) or addr < bank:
                    break
                frames.append(((a - bank) // 4, n, addr))
                first = addr if first is None else min(first, addr)
            a += 4
        return frames

    def palette(self, addr):
        return xrgb555_to_rgb([self.w(addr + 2 * k) for k in range(16)])

    # -- rendering --------------------------------------------------------------
    def _piece(self, code, w, h):
        blk = self.blocks[code >> 6]
        xa = (code & 1) | ((code >> 1) & 2) | ((code >> 2) & 4)
        ya = ((code >> 1) & 1) | ((code >> 2) & 2) | ((code >> 3) & 4)
        out = np.empty((h * 16, w * 16), dtype=np.uint8)
        for y in range(h):
            cy = (ya + y) & 7
            for x in range(w):
                cx = (xa + x) & 7
                out[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = blk[cy * 16:cy * 16 + 16, cx * 16:cx * 16 + 16]
        return out

    def pieces(self, addr, count, header=True):
        p = addr + (2 if header else 0)
        out = []
        for k in range(count):
            code, x, y = self.w(p), self.w(p + 2), self.w(p + 4)
            p += 6
            w, h = 1 << ((x >> 14) & 3), 1 << ((y >> 14) & 3)
            if (code >> 6) >= len(self.blocks):
                continue
            img = self._piece(code, w, h)
            if x & 0x2000:
                img = img[:, ::-1]
            if y & 0x2000:
                img = img[::-1, :]
            cx = (x & 0xFFF) - 0x80
            cy = -(y & 0xFFF)
            out.append((cx - w * 8, cy - h * 8, img))
        return out

    def render(self, addr, count, header=True):
        """-> (pens uint8 HxW, origin_x, origin_y) ; origin = object anchor in image."""
        pcs = self.pieces(addr, count, header)
        if not pcs:
            return np.zeros((1, 1), np.uint8), 0, 0
        x0 = min(p[0] for p in pcs)
        y0 = min(p[1] for p in pcs)
        x1 = max(p[0] + p[2].shape[1] for p in pcs)
        y1 = max(p[1] + p[2].shape[0] for p in pcs)
        canvas = np.zeros((y1 - y0, x1 - x0), np.uint8)
        for px, py, img in reversed(pcs):  # first piece drawn last (on top)
            sub = canvas[py - y0:py - y0 + img.shape[0], px - x0:px - x0 + img.shape[1]]
            mask = img != 0
            sub[mask] = img[mask]
        return canvas, -x0, -y0


def rgba(pens, palette):
    """Pens + 16-colour palette -> RGBA uint8 (pen 0 transparent)."""
    pal = np.zeros((16, 4), np.uint8)
    for i, c in enumerate(palette[:16]):
        pal[i, :3] = c
        pal[i, 3] = 255
    pal[0, 3] = 0
    return pal[pens]


def compose_on_baseline(images, origins, pad=4):
    """Lay out frames (2D pen arrays) side by side, aligned on their anchor point."""
    up = max(oy for _, oy in origins)
    down = max(im.shape[0] - oy for im, (_, oy) in zip(images, origins))
    width = sum(im.shape[1] + pad for im in images)
    out = np.zeros((up + down, width) + images[0].shape[2:], np.uint8)
    x = 0
    for im, (_, oy) in zip(images, origins):
        y = up - oy
        out[y:y + im.shape[0], x:x + im.shape[1]] = im
        x += im.shape[1] + pad
    return out
