"""Tile-layer screens (backgrounds, cut-scenes, ROUND/GAME OVER...) of Dragon Ball Z: V.R.V.S.

How the game builds them (V60 code, see README):
  * screen headers: 8-byte records {u32 script | screen id << 24, u32 video RAM destination}
    in 0x25EB4-0x26083 of the program ROM; the routine at 0xA78D2 runs them.
  * screen id -> tile bank (id & 3) and palette set (table 0xB551A, 8 bytes per id:
    ROM source, word count), loaded at colour banks 0x180+.
  * the script is a small byte code interpreted at 0xA791B that writes 16-bit tile entries
    into video RAM pages (32x16 tiles of 16x16 pixels).
  * tile entry: bits 0-12 tile, 14 flip X, 15 flip Y; colour bank = 0x180 + (entry >> 7) & 0x3F
    (mixer: palette base 0x1800, shift 3).
"""
import os, struct, hashlib, json
from collections import Counter
import numpy as np
from PIL import Image
from .sprites import pal_rgb, contact_sheet

HEADERS = (0x25EB4, 0x26084)
# text layer (8x8 characters): font copies done by the V60 code at 0xA9330
# (ROM source, word count, video RAM destination); the warning-screen font is the block
# copied to 0x31C000 (character n at 0x31C000 + 32*n, n = ASCII code)
TEXT_FONT_COPIES = ((0xADBD6, 0x280, 0x31D100), (0xAA2D5, 0x410, 0x31D600), (0xAAAF5, 0x3B0, 0x31E400),
                    (0xAB255, 0x3B0, 0x31EB60), (0xAB9B5, 0x600, 0x31F400), (0xAC5B5, 0x300, 0x31DE00),
                    (0xACBB5, 0x060, 0x31F300), (0xACC75, 0x5E0, 0x31C000), (0xAD835, 0x1C0, 0x31CC20))
# string lists printed by 0xA9599: u16 position in the text map (0x31Bxxx), colour byte, ASCII, 0
# (a second, mixed-case list at 0xA59B0 needs lowercase glyphs this font upload does not
#  provide: probably for another region, not shown by this version, not exported)
TEXT_SCREENS = (("warning", 0xA5874),)
# fonts the same routine (0xA9336) expands before the copies above:
#   0xA949B: 1bpp font, 8 bytes per character, pen = colour where a bit is set, colour+1 for the
#            drop shadow (previous row shifted one pixel right)
#   0xA9537: 2bpp font, one 16-bit word per row, pen = 2-bit value + colour (0 stays transparent)
FONT_1BPP = (0xA9ED6, 0x83, 1, 0x31C000)          # source, characters, colour, video RAM destination
FONT_2BPP = (0xADBB6, 16, 0, 0x31D080)            # source, rows, colour, destination
# tile-layer scripts the code runs directly, outside the screen-header table (address, caller)
OFF_TABLE_SCRIPTS = ((0xA5AEC, "0xA5BA9 (WARNING screen code)"),
                     (0xAE0F4, "0x870EB (4-step animation, table 0x87282)"),
                     (0xAE156, "0x870EB (4-step animation, table 0x87282)"),
                     (0xAE1B8, "0x870EB (4-step animation, table 0x87282)"),
                     (0xAE24C, "0x870EB (4-step animation, table 0x87292)"),
                     (0xAE2AE, "0x870EB (4-step animation, table 0x87292)"),
                     (0xAE310, "0x870EB (4-step animation, table 0x87292)"),
                     (0xAE21A, "0x87147"), (0xAE372, "0x87156"))
PAL_SET_TABLE = 0xB551A


def decode_tiles(files):
    """mpr-16545/16544 (ROM_LOAD16_BYTE) -> (16384, 16, 16) pixel indices (MAME bgcharlayout)."""
    a = np.frombuffer(files["mpr-16545"], np.uint8)
    b = np.frombuffer(files["mpr-16544"], np.uint8)
    t = np.stack([a, b], 1).reshape(-1, 16, 8)
    hi, lo = t >> 4, t & 15
    order = [(0, 1), (0, 0), (2, 1), (2, 0), (1, 1), (1, 0), (3, 1), (3, 0)]
    cols = []
    for half in (0, 4):
        for byt, h in order:
            cols.append(hi[:, :, byt + half] if h else lo[:, :, byt + half])
    return np.stack(cols, 2)


def run_script(prog, script, dest):
    """Byte-code interpreter (0xA791B). Returns {video RAM byte offset: tile entry}."""
    rd16 = lambda a: struct.unpack_from("<H", prog, a)[0]
    vram, dic, dp = {}, [0] * 0x400, 0
    a, r11 = script, dest - 0x300000
    for _ in range(200000):
        b = prog[a]; a += 1
        if b < 0x80:                                  # dictionary entry
            vram[r11] = dic[b]; r11 += 2; continue
        op = b & 0x7F
        if op == 0x00:                                # set position
            r11 = 2 * rd16(a); a += 2
        elif op == 0x03:                              # relative move (byte)
            r11 += 2 * struct.unpack_from("<b", prog, a)[0]; a += 1
        elif op == 0x27:                              # relative move (word)
            r11 += 2 * struct.unpack_from("<h", prog, a)[0]; a += 2
        elif op in (0x06, 0x09, 0x0C):                # run: same / +1 / -1
            n, v = prog[a] or 256, rd16(a + 1); a += 3
            for _ in range(n):
                vram[r11] = v & 0xFFFF; r11 += 2
                v += {0x06: 0, 0x09: 1, 0x0C: -1}[op]
        elif op == 0x0F:                              # bytes with a fixed high byte
            n, hi = prog[a] or 256, prog[a + 1]; a += 2
            for _ in range(n):
                vram[r11] = (hi << 8) | prog[a]; a += 1; r11 += 2
        elif op in (0x12, 0x15):                      # raw entries (0x15 also fills the dictionary)
            n = prog[a] or 256; a += 1
            for _ in range(n):
                v = rd16(a); a += 2
                vram[r11] = v; r11 += 2
                if op == 0x15:
                    dic[dp & 0x3FF] = v; dp += 1
        elif op == 0x18:                              # clear pages
            r11 = 2 * rd16(a); c = prog[a + 2]; a += 3
            for k in range(c << 9):
                vram[r11 + 2 * k] = 0
        elif op in (0x1B, 0x1E, 0x21, 0x24):          # vertical runs
            n, v = prog[a] or 256, rd16(a + 1); a += 3
            step = {0x1B: 0x40, 0x1E: 0x80, 0x21: -0x40, 0x24: -0x80}[op]
            for _ in range(n):
                vram[r11] = v; r11 += step
        elif op == 0x2A:                              # end
            run_script.end = a                        # first byte after the script (for the coverage report)
            return vram
        else:
            raise ValueError("unknown tilemap op %02x at %06x" % (b, a - 1))
    raise ValueError("tilemap script at %06x does not end" % script)


def screen_headers(prog):
    out = []
    for a in range(HEADERS[0], HEADERS[1], 8):
        s, d = struct.unpack_from("<II", prog, a)
        out.append((a, s & 0xFFFFFF, s >> 24, d))
    return out


def render_page(vram, page, tiles, bank, pals):
    """one video RAM page -> RGBA image cropped to the tiles the script wrote."""
    idx = [(o - (page << 10)) // 2 for o in vram if o >> 10 == page]
    if not idx:
        return None
    ys, xs = [k // 32 for k in idx], [k % 32 for k in idx]
    y0, x0 = min(ys), min(xs)
    img = np.zeros(((max(ys) - y0 + 1) * 16, (max(xs) - x0 + 1) * 16, 4), np.uint8)
    for k in idx:
        e = vram[(page << 10) + 2 * k]
        px = tiles[(bank << 13) | (e & 0x1FFF)]
        if e & 0x4000: px = px[:, ::-1]
        if e & 0x8000: px = px[::-1, :]
        pal = pals((e >> 7) & 0x3F)
        y, x = (k // 32 - y0) * 16, (k % 32 - x0) * 16
        blk = img[y:y + 16, x:x + 16]
        op = px != 0
        blk[op, :3] = pal[px][op]
        blk[op, 3] = 255
    if not img[..., 3].any():
        return None
    return Image.fromarray(img, "RGBA")


def expand_1bpp(prog, src, chars, colour):
    out, shadow = bytearray(), 0
    for i in range(chars * 8):
        b, row = prog[src + i], 0
        for k in range(8):
            row = row << 4 | (b >> (7 - k) & 1)
        pix = (shadow & ~(row * 15)) | row * colour
        out += pix.to_bytes(4, "big")
        shadow = ((row * (colour + 1)) >> 4) & 0xFFFFFFFF
    return bytes(out)


def expand_2bpp(prog, src, rows, colour):
    out = bytearray()
    for i in range(rows):
        h, row = struct.unpack_from("<H", prog, src + 2 * i)[0], 0
        for k in range(8):
            v = h >> (14 - 2 * k) & 3
            row = row << 4 | ((v + colour) & 15 if v else 0)
        out += row.to_bytes(4, "big")
    return bytes(out)


def text_char_ram(prog):
    """Text-layer character RAM (0x31C000-0x31FFFF, 512 characters of 8x8 4bpp) as set up by 0xA9336."""
    vram = bytearray(0x20000)
    src, n, col, dst = FONT_1BPP
    d = expand_1bpp(prog, src, n, col); vram[dst - 0x300000:dst - 0x300000 + len(d)] = d
    src, n, col, dst = FONT_2BPP
    d = expand_2bpp(prog, src, n, col); vram[dst - 0x300000:dst - 0x300000 + len(d)] = d
    for src, cnt, dst in TEXT_FONT_COPIES:
        vram[dst - 0x300000:dst - 0x300000 + 2 * cnt] = prog[src:src + 2 * cnt]
    return vram


def char_sheet(data, cols=32):
    """8x8 4bpp characters -> greyscale RGBA sheet (real colours unknown: each character's pens
    are spread over a grey ramp, pen 0 transparent)."""
    n = len(data) // 32
    rows = (n + cols - 1) // cols
    img = np.zeros((rows * 9, cols * 9, 4), np.uint8)
    for c in range(n):
        g = np.frombuffer(data[32 * c:32 * c + 32], np.uint8).reshape(8, 4)
        px = np.stack([g >> 4, g & 15], -1).reshape(8, 8).astype(np.int32)
        if not px.any():
            continue
        lo, hi = px[px > 0].min(), px.max()
        grey = np.where(px > 0, 255 - (px - lo) * 175 // max(hi - lo, 1), 0).astype(np.uint8)
        y, x = (c // cols) * 9, (c % cols) * 9
        img[y:y + 8, x:x + 8] = np.stack([grey, grey, grey, np.where(px > 0, 255, 0).astype(np.uint8)], -1)
    return Image.fromarray(img, "RGBA")


def text_screen(prog, strings):
    """Pre-title WARNING screen (text layer). The text palette (banks 0x1C0+, mixer register 0x20
    set from the table at 0x80516) is not loaded from any ROM table found, so pens are drawn as a
    grey ramp (pen 0 transparent)."""
    vram = text_char_ram(prog)
    cells = {}
    a = strings
    while struct.unpack_from("<H", prog, a)[0]:
        pos, col = struct.unpack_from("<H", prog, a)[0], prog[a + 2]
        a += 3
        cell = (pos - 0xB000) // 2
        while prog[a]:
            cells[cell] = ((col << 8) | prog[a]) & 0x1FF; cell += 1; a += 1
        a += 1
    rows = [c // 64 for c in cells]; cols = [c % 64 for c in cells]
    r0, c0 = min(rows), min(cols)
    px = np.zeros(((max(rows) - r0 + 1) * 8, (max(cols) - c0 + 1) * 8), np.uint8)
    for c, ch in cells.items():
        g = np.frombuffer(bytes(vram[0x1C000 + 32 * ch:0x1C000 + 32 * ch + 32]), np.uint8).reshape(8, 4)
        y, x = (c // 64 - r0) * 8, (c % 64 - c0) * 8
        px[y:y + 8, x:x + 8] = np.stack([g >> 4, g & 15], -1).reshape(8, 8)
    top = max(int(px.max()), 1)
    grey = (px.astype(np.int32) * 255 // top).astype(np.uint8)
    rgba = np.stack([grey, grey, grey, np.where(px > 0, 255, 0).astype(np.uint8)], -1)
    return Image.fromarray(rgba, "RGBA")


def export(files, outdir, log=print):
    prog = files["epr-16543"] + files["epr-16542a"]
    W = np.frombuffer(prog, "<u2").astype(np.int32)
    tiles = decode_tiles(files)
    d = os.path.join(outdir, "backgrounds")
    os.makedirs(d, exist_ok=True)
    seen_script, seen_img, meta, ims = set(), {}, [], []

    def palette_set(sid):
        src, cache = struct.unpack_from("<I", prog, PAL_SET_TABLE + 8 * sid)[0], {}

        def pals(k):
            if k not in cache:
                a = src + 32 * k
                cache[k] = pal_rgb(W[a // 2:a // 2 + 16])
            return cache[k]
        return pals

    def save_pages(vram, sid, prefix, script, entry0):
        pals = palette_set(sid)
        for page in sorted({o >> 10 for o in vram}):
            im = render_page(vram, page, tiles, sid & 3, pals)
            if im is None:
                continue
            h = hashlib.md5(im.tobytes()).hexdigest()
            entry = dict(entry0, script=hex(script), screen_id=sid, vram_page=page, width=im.width, height=im.height)
            if h in seen_img:
                entry["same_as"] = seen_img[h]
            else:
                fn = "%s_%05X_page%02X.png" % (prefix, script, page)
                im.save(os.path.join(d, fn), optimize=True)
                seen_img[h] = entry["file"] = fn
                ims.append(im)
            meta.append(entry)

    tile_use = {}                                  # tile -> (screen id, colour) of a screen using it
    for hdr, script, sid, dest in screen_headers(prog):
        if script in seen_script:
            continue
        seen_script.add(script)
        vram = run_script(prog, script, dest)
        for e in vram.values():
            tile_use.setdefault(((sid & 3) << 13) | (e & 0x1FFF), (sid, (e >> 7) & 0x3F))
        save_pages(vram, sid, "screen", script, {"header": hex(hdr)})

    # scripts the code runs directly: partial updates drawn over a screen (animation steps, frame);
    # palette set = the one of the header screens that use the same tiles
    n_patch = 0
    for script, caller in OFF_TABLE_SCRIPTS:
        vram = run_script(prog, script, 0x300000)
        votes = Counter(tile_use[((s & 3) << 13) | (e & 0x1FFF)][0]
                        for s in range(4) for e in vram.values() if ((s & 3) << 13) | (e & 0x1FFF) in tile_use)
        if not votes:      # only solid filler tiles (no colour data): nothing to show
            meta.append({"script": hex(script), "called_from": caller, "note": "only blank/solid filler tiles, not exported"})
            continue
        before = len(meta)
        save_pages(vram, votes.most_common(1)[0][0], "patch", script, {"called_from": caller, "off_table": True})
        n_patch += sum(1 for m in meta[before:] if "file" in m)

    # tiles no script places: shown in ROM order, coloured like the nearest tile a screen uses
    realt = np.array([t.any() and not (t == 15).all() for t in tiles])
    unused = [i for i in np.nonzero(realt)[0].tolist() if i not in tile_use]
    if unused:
        used_sorted = sorted(tile_use)
        runs = []                                  # one row per run of consecutive tiles (gaps of 1 kept blank)
        for i in unused:
            if runs and i - runs[-1][-1] <= 2:
                runs[-1].append(i)
            else:
                runs.append([i])
        cols = max(r[-1] - r[0] + 1 for r in runs)
        img = np.zeros((len(runs) * 16, cols * 16, 4), np.uint8)
        for row, r in enumerate(runs):
            for i in r:
                near = min((u for u in used_sorted if u >> 13 == i >> 13), key=lambda u: abs(u - i))
                sid, col = tile_use[near]
                pal = palette_set(sid)(col)
                px = tiles[i]
                y, x = row * 16, (i - r[0]) * 16
                blk = img[y:y + 16, x:x + 16]
                op = px != 0
                blk[op, :3] = pal[px][op]
                blk[op, 3] = 255
        Image.fromarray(img, "RGBA").save(os.path.join(d, "unused_tiles.png"), optimize=True)
        meta.append({"file": "unused_tiles.png", "rows": [[r[0], r[-1]] for r in runs],
                     "note": "tiles no script places: one row per run of consecutive tile numbers (first, last); "
                             "palette of the nearest used tile (guess)"})
    for name, addr in TEXT_SCREENS:
        im = text_screen(prog, addr)
        fn = "text_%s_greyscale.png" % name
        im.save(os.path.join(d, fn), optimize=True)
        meta.append({"text_layer": True, "strings": hex(addr), "file": fn, "width": im.width,
                     "height": im.height, "note": "real colours not found in ROM; grey ramp"})
    vram = text_char_ram(prog)
    char_sheet(bytes(vram[0x1C000:0x20000])).save(os.path.join(d, "text_layer_characters.png"), optimize=True)
    meta.append({"text_layer": True, "file": "text_layer_characters.png",
                 "note": "the 512 characters of text-layer RAM (0x31C000) after the font set-up at 0xA9336, "
                         "32 per row, greyscale (real colours unknown)"})
    src, n, col, _ = FONT_1BPP
    char_sheet(expand_1bpp(prog, src, n, col), cols=16).save(os.path.join(d, "text_font_1bpp_A9ED6.png"), optimize=True)
    meta.append({"text_layer": True, "file": "text_font_1bpp_A9ED6.png",
                 "note": "1bpp font with drop shadow (0xA9ED6, 131 characters) as expanded by 0xA949B; most of it "
                         "is then overwritten in character RAM by the copy from 0xACC75"})
    contact_sheet(ims, os.path.join(d, "_sheet.png"), maxw=2100)
    with open(os.path.join(d, "backgrounds.json"), "w") as f:
        json.dump(meta, f, indent=1)
    log("backgrounds: %d tile-layer images from %d screen scripts + %d patches from scripts outside the table, "
        "%d unused tiles, %d text screens and 2 font sheets (greyscale)"
        % (len(seen_img) - n_patch, len(seen_script), n_patch, len(unused), len(TEXT_SCREENS)))
