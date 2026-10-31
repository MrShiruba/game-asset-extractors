"""Non-fighter sprites: effects, projectiles, HUD/texts, portraits, spectators, credits.

Sprite colours (MAME dbz + K053251 with the values the game writes): a sprite
uses palette (colour & 0x1F) of the first palette RAM block. In a fight that
block holds (routine 0x5CAC):
    0-3   player 1 character palettes (base, effects, alternates)
    4-7   player 2 character palettes
    8-19  shared palettes, from table 0x2056E indexed by the stage number
Frame tables below were located in the 68000 program together with the
colour each drawing routine passes.
"""
SHARED_TABLE = 0x2056E
SHARED_COUNT = 9            # stage palette sets
SPECTATOR_TABLE = 0xCEAA    # per stage: scene records (type, x, y, colour, ?, frames, count)
PORTRAITS = 0xDBF0          # 4 entries per character; palette = select-screen pair
SELECT_PALETTES = 0x1F856   # entries 0-19: select screen pair per character (and alt colour)

# (folder, table, header_bytes, max_entries, palette rule)
#   ("shared", n) -> shared palette n (8-19) of stage set 0
#   ("char", c, v)  -> character c palette variant v (P1)
#   ("player",)     -> rendered once per fighter, with its base palette (P1 and P2)
TABLES = [
    ("effects",        0xE756, 0, 94, ("shared", 9)),
    ("effects_2",      0xE8E6, 0, 47, ("player",)),   # one copy per fighter palette
    ("projectiles",    0xF404, 2, 41, ("player",)),   # colour = shooter's base palette
    ("goku_parts",     0xE932, 2, 8,  ("char", 0, 0)),
    ("win_quotes",     0xD150, 0, 20, ("shared", 8)),
    ("hud_text",       0xDA58, 0, 15, ("shared", 8)),
    ("shadows",        0xE32C, 0, 10, ("shared", 8)),
    ("credits",        0xBF46, 0, 4,  ("shared", 8)),
    ("credits_2",      0xBF5E, 0, 4,  ("shared", 8)),
]


class ObjectExtractor:
    def __init__(self, renderer):
        self.fr = renderer
        self.m = renderer.m

    def l(self, a):
        return self.fr.l(a)

    def w(self, a):
        return self.fr.w(a)

    def shared_palettes(self, stage):
        base = self.l(SHARED_TABLE + 4 * stage)
        return [self.fr.palette(base + 32 * k) for k in range(12)]  # palettes 8..19

    def palette(self, rule, chars, stage=0):
        if rule[0] == "shared":
            return self.shared_palettes(stage)[rule[1] - 8]
        _, c, v = rule
        return self.fr.palette(chars[c]["variants_p1"][v])

    def entries(self, table, header, max_entries):
        """Frame table entries: (index, count, address) ; stops at the first invalid one."""
        out = []
        for i in range(max_entries):
            v = self.l(table + 4 * i)
            if v == 0x00FFFFFF:
                continue
            n, addr = v >> 24, v & 0xFFFFFF
            if not (1 <= n <= 64) or addr + header + 6 * n > len(self.m):
                break
            out.append((i, n, addr))
        return out

    def render_table(self, table, header, max_entries):
        res = []
        for i, n, addr in self.entries(table, header, max_entries):
            pens, ox, oy = self.fr.render(addr, n, header=bool(header))
            res.append((i, pens, ox, oy, addr))
        return res

    def portraits(self, chars):
        """Select-screen portraits. Each one is two layers drawn at the same spot:
        entry 4c+k (colour 0) and 4c+k+1 (colour 1), k = 0 (idle) or 2 (selected).
        -> list of (char_name, [(name, pens, ox, oy, addr)], palette32)."""
        import numpy as np
        out = []
        for c, ch in enumerate(chars):
            pair = self.l(SELECT_PALETTES + 4 * (2 * c))
            pal32 = self.fr.palette(pair) + self.fr.palette(pair + 32)
            rows = []
            for k, label in ((0, "idle"), (2, "selected")):
                layers = []
                for j in range(2):
                    v = self.l(PORTRAITS + 4 * (4 * c + k + j))
                    n, addr = v >> 24, v & 0xFFFFFF
                    if 1 <= n <= 64 and addr < len(self.m):
                        pens, ox, oy = self.fr.render(addr, n, header=False)
                        layers.append((pens, ox, oy, j, addr))
                if not layers:
                    continue
                left = max(l[1] for l in layers)
                top = max(l[2] for l in layers)
                right = max(l[0].shape[1] - l[1] for l in layers)
                bottom = max(l[0].shape[0] - l[2] for l in layers)
                canvas = np.zeros((top + bottom, left + right), np.uint8)
                for pens, ox, oy, j, _ in layers:  # layer 1 drawn over layer 0
                    y0, x0 = top - oy, left - ox
                    sub = canvas[y0:y0 + pens.shape[0], x0:x0 + pens.shape[1]]
                    mask = pens != 0
                    sub[mask] = pens[mask] + 16 * j
                rows.append((label, canvas, left, top, layers[0][4]))
            out.append((ch["name"], rows, pal32))
        return out

    def spectators(self):
        """-> list of (stage, record_no, colour, [(entry, pens, ox, oy, addr)], palette)."""
        out = []
        for stage in range(SHARED_COUNT):
            p = self.l(SPECTATOR_TABLE + 4 * stage)
            if p == 0xFFFFFFFF or p >= len(self.m):
                continue
            shared = self.shared_palettes(stage)
            rec = 0
            while self.w(p) < 0x8000 and rec < 16:
                colour = self.w(p + 6)
                table = self.l(p + 10)
                count = self.w(p + 14)
                frames = self.render_table(table, 0, count)
                pal = shared[(colour & 0x1F) - 8] if 8 <= (colour & 0x1F) < 20 else shared[0]
                out.append((stage, rec, colour, frames, pal))
                p += 16
                rec += 1
        return out
