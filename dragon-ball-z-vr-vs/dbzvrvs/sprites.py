"""Sprite extraction for Dragon Ball Z: V.R.V.S. (Sega System 32)."""
import os, struct, collections, json
from collections import Counter, defaultdict
import numpy as np
from PIL import Image

SPR_TABLE = 0x000300       # 2116 x 16-byte sprite descriptors
SPR_COUNT = 2116
NAME_PTRS = 0x02B246       # 2115 pointers to sprite names
NAME_COUNT = 2115
ANIM_START, ANIM_END = 0x008740, 0x025EB4   # 16-byte animation-frame records (tile-layer
                                             # screen headers and scripts follow)
# Sprite palettes: an object's palette id (= colour bank << 4, e.g. 0xE52 for Vegeta) is resolved by
# the palette allocator at 0x9ACEE, which copies the 16 colours straight from ROM into a free bank:
#   id < 0x1800: ROM 0xAE3DA + 2 * id      id >= 0x1800: ROM 0xAD3DA + 2 * id
# (one 16-colour palette = 32 bytes, format xBGRBBBBGGGGRRRR). The same ROM block is what 0xB553E
# loads at start-up into palette RAM banks 0x000-0x17F and 0x200-0x368.
PAL_LAST_BANK = 0x368
# Fighters' palette ids, set by 0x84639 from three tables of pointers indexed by character
# (0 Goku, 1 Gohan, 2 Trunks, 3 Vegeta, 4 Piccolo, 5 Ozotto), 4 ids per character:
#   0x87851 normal; 0x87869 alternate, used when the per-player byte 1/11 of work RAM is 0 (the second
#   player in a mirror match, e.g. green Vegeta); 0x87881 special (object flags 0x6E and 0x72 set)
FIGHTERS = ("gok", "han", "tra", "veg", "pic", "ozz")
FIGHTER_TABLES = {"normal": 0x87851, "alt": 0x87869, "special": 0x87881}
# groups that no animation record references, but that are recolours of a group that is
# (checked by eye: icycle = the ice blocks of the bonus stage, same art as ice2)
GROUP_PALETTE_HINTS = {"icycle": "ice2"}
PAL_FIRST_BANK = 4         # banks 0-3 hold the 0xfffe fill, not real colours


def bank_address(bank):
    """ROM address of the 16 colours of a palette id >> 4 (allocator at 0x9ACEE)."""
    if bank > PAL_LAST_BANK:
        return None
    return (0xAE3DA if bank < 0x180 else 0xAD3DA) + 32 * bank


def fighter_palettes(prog):
    """{character group: {"normal"/"alt"/"special": [4 colour banks]}} from the tables used by 0x84639."""
    out = {}
    for k, g in enumerate(FIGHTERS):
        out[g] = {}
        for kind, t in FIGHTER_TABLES.items():
            p = struct.unpack_from("<I", prog, t + 4 * k)[0]
            out[g][kind] = [struct.unpack_from("<H", prog, p + 2 * j)[0] >> 4 for j in range(4)]
    return out


def build_sprite_rom(files):
    """ROM_LOAD64_WORD: 4 ROMs interleaved by 16-bit words, two 8 MB halves."""
    spr = bytearray(0x1000000)
    for half, names in enumerate((("mpr-16546", "mpr-16548", "mpr-16550", "mpr-16552"),
                                  ("mpr-16547", "mpr-16549", "mpr-16551", "mpr-16553"))):
        arrs = [np.frombuffer(files[n], dtype=np.uint8).reshape(-1, 2) for n in names]
        spr[half * 0x800000:(half + 1) * 0x800000] = np.stack(arrs, axis=1).reshape(-1).tobytes()
    return np.frombuffer(bytes(spr), dtype=">u4")


def pal_rgb(words):
    """System 32 'xBGRBBBBGGGGRRRR' format (LSBs in bits 12-14) -> RGB888."""
    v = np.asarray(words, dtype=np.int32)
    r = ((v & 15) << 1) | ((v >> 12) & 1)
    g = (((v >> 4) & 15) << 1) | ((v >> 13) & 1)
    b = (((v >> 8) & 15) << 1) | ((v >> 14) & 1)
    rgb = np.stack([r, g, b], -1)
    return ((rgb << 3) | (rgb >> 2)).astype(np.uint8)   # pal5bit


class SpriteSet:
    def __init__(self, prog, sprwords):
        self.prog = prog
        self.W = np.frombuffer(prog, dtype="<u2").astype(np.int32)
        self.spr = sprwords
        self.recs = []
        for i in range(SPR_COUNT):
            w, h, b, lo = struct.unpack_from("<4H", prog, SPR_TABLE + 16 * i)
            bank = ((b & 0x800) >> 11) | ((b & 0x4000) >> 13)
            addr = (bank << 20) | ((h & 0xF000) << 4) | lo
            self.recs.append((w & 0x3FF, h & 0x3FF, addr))
        self.names = []
        for i in range(NAME_COUNT):
            a = struct.unpack_from("<I", prog, NAME_PTRS + 4 * i)[0]
            self.names.append(prog[a:prog.index(b"\0", a)].decode("latin1"))
        self.names += ["unnamed_%04d" % i for i in range(NAME_COUNT, SPR_COUNT)]
        self._detect_bpp()
        self._scan_anims()

    # ---- 8bpp detection: address gap to the next sprite = h*ceil(w/4) ----
    def _detect_bpp(self):
        self.bpp8 = [False] * SPR_COUNT
        order = sorted(range(SPR_COUNT), key=lambda i: self.recs[i][2])
        for k, i in enumerate(order[:-1]):
            w, h, a = self.recs[i]
            gap = self.recs[order[k + 1]][2] - a
            if w and h and gap == h * ((w + 3) // 4) and gap != h * ((w + 7) // 8):
                self.bpp8[i] = True

    # ---- colour bank of each sprite, from the animation records ----
    def _scan_anims(self):
        cnt = collections.defaultdict(collections.Counter)
        for a in range(ANIM_START, ANIM_END, 16):
            r = self.W[a // 2:a // 2 + 8]
            if r[0] < SPR_COUNT and r[6] == 0 and r[7] == 0 and r[5] != 0 and not (r[1] & 0x2000):
                cnt[int(r[0])][int(r[5])] += 1
        self.colour, self.colour_src = {}, {}
        fam = defaultdict(Counter)        # per name family (prefix before the first "_")
        for i, c in cnt.items():
            for bank, n in c.items():
                fam[self.group(i)][bank & 0x7FF0] += n
        for i, c in cnt.items():
            best = c.most_common(1)[0][0]
            f = fam[self.group(i)]
            dom, n_dom = f.most_common(1)[0]
            total = sum(f.values())
            mine = {k & 0x7FF0 for k in c}
            if n_dom >= 0.8 * total and (best & 0x7FF0) != dom and (dom in mine or sum(c.values()) <= 2):
                # the sprite also appears with its character's usual palette (or only once or
                # twice elsewhere): the other bank is a flash / attract-mode palette
                self.colour[i], self.colour_src[i] = dom, "family"
            else:
                self.colour[i], self.colour_src[i] = best, "anim"
        # sprites no animation uses: take the palette of the sprite with the most similar
        # developer name (jumpup_p_n4a -> jumpup_p_m4a), then the nearest index
        known = sorted(cnt)
        for i in range(SPR_COUNT):
            if i in self.colour:
                continue
            hint = GROUP_PALETTE_HINTS.get(self.group(i))
            if hint and fam[hint]:
                self.colour[i] = fam[hint].most_common(1)[0][0]
                self.colour_src[i] = "group hint:" + hint
                continue
            n = self.names[i]
            def score(k):
                m = self.names[k]
                l = 0
                while l < min(len(n), len(m)) and n[l] == m[l]:
                    l += 1
                return (l, -abs(k - i))
            j = max(known, key=score)
            if score(j)[0] > len(self.group(i)):
                self.colour[i], self.colour_src[i] = self.colour[j], "name:" + self.names[j]
            else:
                j = min(known, key=lambda k: abs(k - i))
                self.colour[i], self.colour_src[i] = self.colour[j], "neighbour:" + self.names[j]

    def group(self, i):
        return self.names[i].split("_")[0]

    def palette(self, i, colour=None):
        """256-entry RGB table for sprite i (16 entries used for 4bpp)."""
        c = self.colour.get(i) if colour is None else colour
        if c is None:
            return None
        if self.bpp8[i]:
            first = (c & 0x7F00) >> 4
            n = 16
        else:
            first = (c & 0x7FF0) >> 4
            n = 1
        out = np.zeros((256, 3), np.uint8)
        for k in range(n):
            bank = first + k
            a = bank_address(bank)
            if bank < PAL_FIRST_BANK or a is None:
                return None
            out[16 * k:16 * k + 16] = pal_rgb(self.W[a // 2:a // 2 + 16])
        return out

    def indices(self, i):
        """pixel indices + transparency mask, following MAME draw_one_sprite."""
        w, h, addr = self.recs[i]
        if not w or not h:
            return None, None
        if self.bpp8[i]:
            sw = (w + 3) // 4
            words = self.spr[addr:addr + sw * h].reshape(h, sw)
            px = np.stack([(words >> s) & 0xFF for s in (24, 16, 8, 0)], axis=2).reshape(h, sw * 4)
            endval, npw = 0xFF, 4
        else:
            sw = (w + 7) // 8
            words = self.spr[addr:addr + sw * h].reshape(h, sw)
            px = np.stack([(words >> s) & 0xF for s in tuple(range(28, -1, -4))], axis=2).reshape(h, sw * 8)
            endval, npw = 0xF, 8
        px = px.astype(np.int32)
        opaque = px != 0
        # If the max index only ever shows up on the first/last pixel of a word,
        # the sprite was drawn with transparency code 15/255 (end-of-line marker).
        inner = px.reshape(h, sw, npw)[:, :, 1:npw - 1]
        if not (inner == endval).any() and (px == endval).any():
            pw = px.reshape(h, sw, npw)
            edge = np.zeros_like(pw, dtype=bool)
            edge[:, :, 0] = pw[:, :, 0] == endval
            edge[:, :, -1] = pw[:, :, -1] == endval
            opaque &= ~edge.reshape(h, sw * npw)
            # end code: last pixel of a word == 15 stops the line
            stop = (pw[:, :, -1] == endval)
            after = np.cumsum(stop, axis=1) - stop  # words after a stop word
            dead = np.repeat(after > 0, npw, axis=1)
            opaque &= ~dead
        return px[:, :w], opaque[:, :w]

    def image(self, i, colour=None):
        px, op = self.indices(i)
        if px is None:
            return None
        pal = self.palette(i, colour)
        if pal is None:   # greyscale fallback
            m = 255 if self.bpp8[i] else 15
            g = (px * 255 // m).astype(np.uint8)
            rgb = np.stack([g, g, g], -1)
        else:
            rgb = pal[px]
        rgba = np.concatenate([rgb, (op * 255).astype(np.uint8)[..., None]], -1)
        return Image.fromarray(rgba, "RGBA")


def safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)


def contact_sheet(images, path, bg=(64, 128, 128), pad=4, maxw=1600):
    rows, row, x, rh = [], [], 0, 0
    for im in images:
        if x + im.width + pad > maxw and row:
            rows.append((row, rh)); row, x, rh = [], 0, 0
        row.append(im); x += im.width + pad; rh = max(rh, im.height)
    if row:
        rows.append((row, rh))
    W = min(maxw, max(sum(i.width + pad for i in r) for r, _ in rows) + pad)
    H = sum(h + pad for _, h in rows) + pad
    sheet = Image.new("RGBA", (W, H), bg + (255,))
    y = pad
    for r, h in rows:
        x = pad
        for im in r:
            sheet.alpha_composite(im, (x, y)); x += im.width + pad
        y += h + pad
    sheet.save(path, optimize=True)


def export(files, outdir, log=print):
    prog = files["epr-16543"] + files["epr-16542a"]
    ss = SpriteSet(prog, build_sprite_rom(files))
    by_group = collections.defaultdict(list)
    alt_group = collections.defaultdict(list)
    meta = []
    fp = fighter_palettes(prog)
    to_alt = {}                                    # normal colour bank -> alternate one
    for g, kinds in fp.items():
        for n, a in zip(kinds["normal"], kinds["alt"]):
            if n != a:
                to_alt[n] = a
    for i in range(SPR_COUNT):
        im = ss.image(i)
        if im is None:
            continue
        g = ss.group(i)
        d = os.path.join(outdir, "sprites", safe(g))
        os.makedirs(d, exist_ok=True)
        fn = "%04d_%s.png" % (i, safe(ss.names[i]))
        im.save(os.path.join(d, fn), optimize=True)
        by_group[g].append(im)
        w, h, a = ss.recs[i]
        meta.append({"index": i, "name": ss.names[i], "file": "%s/%s" % (safe(g), fn), "width": w, "height": h,
                     "bpp": 8 if ss.bpp8[i] else 4, "colour_bank": ss.colour.get(i),
                     "palette_source": ss.colour_src.get(i, "none")})
        c = ss.colour.get(i)
        if c is not None and not ss.bpp8[i] and (c & 0x7FF0) >> 4 in to_alt:
            ca = (to_alt[(c & 0x7FF0) >> 4] << 4) | (c & 0xF)
            ad = os.path.join(outdir, "sprites", safe(g) + "_alt")
            os.makedirs(ad, exist_ok=True)
            ima = ss.image(i, ca)
            ima.save(os.path.join(ad, fn), optimize=True)
            alt_group[g].append(ima)
            meta[-1]["alt_file"] = "%s_alt/%s" % (safe(g), fn)
            meta[-1]["alt_colour_bank"] = ca
    sd = os.path.join(outdir, "sprites", "_sheets")
    os.makedirs(sd, exist_ok=True)
    for g, ims in by_group.items():
        contact_sheet(ims, os.path.join(sd, safe(g) + ".png"))
    for g, ims in alt_group.items():
        contact_sheet(ims, os.path.join(sd, safe(g) + "_alt.png"))
    # palette strip of each fighter: normal (4), alternate (4), special (1), 16 colours each
    rows = []
    for g, kinds in fp.items():
        banks = kinds["normal"] + kinds["alt"] + kinds["special"][:1]
        rows.append([pal_rgb(ss.W[bank_address(b) // 2:bank_address(b) // 2 + 16]) for b in banks])
    strip = np.zeros((len(rows) * 10, 9 * 16 * 8 + 8 * 4, 3), np.uint8)
    for r, pals in enumerate(rows):
        for k, p in enumerate(pals):
            for c in range(16):
                x = k * (16 * 8 + 4) + c * 8
                strip[r * 10:r * 10 + 8, x:x + 8] = p[c]
    Image.fromarray(strip).resize((strip.shape[1] * 2, strip.shape[0] * 2), Image.NEAREST).save(
        os.path.join(outdir, "sprites", "_palettes.png"))
    with open(os.path.join(outdir, "sprites", "fighter_palettes.json"), "w") as f:
        json.dump({g: {k: [hex(b) for b in v] for k, v in kinds.items()} for g, kinds in fp.items()}, f, indent=1)
    with open(os.path.join(outdir, "sprites", "sprites.json"), "w") as f:
        json.dump(meta, f, indent=1)
    log("sprites: %d images in %d groups (%d 8bpp), %d in the fighters' alternate palette"
        % (len(meta), len(by_group), sum(ss.bpp8), sum(len(v) for v in alt_group.values())))
    return ss
