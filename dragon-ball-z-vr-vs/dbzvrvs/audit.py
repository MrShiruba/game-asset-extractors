"""Coverage report: how much of each ROM the extracted files account for.

Filler (bytes 0xFF, blank tiles) is not counted. Anything that is real data but not covered
by an exported file shows up here, so gaps are measured instead of guessed.
"""
import os, struct
import numpy as np
from . import sprites, tilemaps

KNOWN_GAPS = [
    "WARNING screen and text-layer fonts exported in greyscale: the text layer uses palette banks 0x1C0+ "
    "(mixer register 0x20 = 0x7F, from the table at 0x80516), which no ROM table loads; their colours are set some "
    "other way that was not found.",
    "Unused tiles (backgrounds/unused_tiles.png) are coloured with the palette of the nearest tile a screen uses: "
    "a guess. They look like the top rows of stage pictures that the scripts never place.",
    "The routine at 0xA7C47 runs tile scripts from a table at 0x2A140 that holds no valid script, and no caller of it "
    "was found: probably unused.",
    "Sound table 0 (6 commands) holds stop/fade control sequences, not sounds: not exported.",
    "Background layers are exported per video RAM page, not combined with scrolling into final screens.",
    "Program data ROM: the bytes not identified are a 0x300-byte block before the sprite table (0x000-0x2FF) and "
    "sparse 0/1/2 flag tables at 0x2A174-0x2AD34 (no graphics).",
    "The program code ROM (epr-16542a) mixes code and data; only the structures it uses that were traced are "
    "exported (palettes 0xAE3DA/0xB13DA/0xB40FA, palette sets 0xB551A, fonts 0xA9ED6/0xAA2D5-0xADBD6, WARNING strings "
    "0xA5874, scripts 0xA5AEC/0xAE0F4-0xAE372). Its share of data vs code is not measured.",
]


def pct(a, b):
    return "%6.2f%%" % (100.0 * a / b if b else 100.0)


def report(files, region, pcm_table, outdir, log=print):
    lines = []
    prog = files["epr-16543"] + files["epr-16542a"]

    # ---- sprite ROM: 32-bit words covered by the sprite table
    ss = sprites.SpriteSet(prog, sprites.build_sprite_rom(files))
    cov = np.zeros(len(ss.spr), bool)
    for i, (w, h, a) in enumerate(ss.recs):
        if w and h:
            sw = (w + 3) // 4 if ss.bpp8[i] else (w + 7) // 8
            cov[a:a + sw * h] = True
    real = (ss.spr != 0xFFFFFFFF) & (ss.spr != 0)     # 0xFF filler and zero padding excluded
    lines.append("sprite ROM (16 MB)   %s of non-filler data in exported sprites  (%d words not covered)"
                 % (pct((cov & real).sum(), real.sum()), (real & ~cov).sum()))
    shown = [i for i, (w, h, _) in enumerate(ss.recs) if w and h]
    guessed = sum(1 for i in shown if ss.colour_src.get(i, "").startswith("neighbour"))
    lines.append("  sprite palettes     %d of %d exported sprites have a guessed palette (palette_source = neighbour)"
                 % (guessed, len(shown)))

    # ---- tile ROM: tiles used by the exported screens
    tiles = tilemaps.decode_tiles(files)
    used = np.zeros(len(tiles), bool)
    for _, s, sid, d in tilemaps.screen_headers(prog):
        for e in tilemaps.run_script(prog, s, d).values():
            used[((sid & 3) << 13) | (e & 0x1FFF)] = True
    realt = np.array([t.any() and not (t == 15).all() for t in tiles])
    unused = np.nonzero(realt & ~used)[0]
    lines.append("tile ROM (2 MB)      %s of non-blank tiles exported: %s placed by screen scripts, %d tiles no "
                 "script places in backgrounds/unused_tiles.png" % (pct(realt.sum(), realt.sum()),
                                                                    pct((realt & used).sum(), realt.sum()), len(unused)))

    # ---- data ROM of the program (epr-16543, 0x00000-0x7FFFF): bytes inside identified structures
    cov = np.zeros(0x80000, bool)
    cov[sprites.SPR_TABLE:sprites.SPR_TABLE + 16 * sprites.SPR_COUNT] = True
    cov[sprites.ANIM_START:sprites.ANIM_END] = True
    cov[tilemaps.HEADERS[0]:tilemaps.HEADERS[1]] = True
    for _, s, sid, d in tilemaps.screen_headers(prog):
        tilemaps.run_script(prog, s, d)
        if s < 0x80000:
            cov[s:tilemaps.run_script.end] = True
    cov[sprites.NAME_PTRS:sprites.NAME_PTRS + 4 * sprites.NAME_COUNT] = True
    for i in range(sprites.NAME_COUNT):
        a = struct.unpack_from("<I", prog, sprites.NAME_PTRS + 4 * i)[0]
        cov[a:prog.index(b"\0", a) + 1] = True
    b = np.frombuffer(prog[:0x80000], np.uint8)
    realb = (b != 0xFF) & (b != 0)
    lines.append("program data ROM     %s of non-filler bytes in identified structures (sprite table, animations, "
                 "screen headers and scripts, sprite names); %d bytes not identified"
                 % (pct((cov & realb).sum(), realb.sum()), (realb & ~cov).sum()))

    # ---- PCM ROMs: bytes covered by the sample table + unused blocks
    pcm = np.frombuffer(region[0x100000:], np.uint8)
    c = np.zeros(len(pcm), bool)
    for s in pcm_table:
        e = region.index(b"\xff", s)
        c[s - 0x100000:e - 0x100000 + 1] = True
    realp = pcm != 0xFF
    n_tab = (c & realp).sum()
    # data no table points to = the unused_*.raw blocks (same rule as export_raw_pcm)
    u = np.zeros(len(pcm), bool)
    a = 0
    while a < len(pcm):
        if c[a] or pcm[a] == 0xFF:
            a += 1; continue
        e = a
        while e < len(pcm) and pcm[e] != 0xFF:
            e += 1
        blk = pcm[a:e]
        if e - a >= 256 and len(set(blk.tolist())) > 4 and not c[a:e].any():
            u[a:e] = True
        a = e
    lines.append("PCM ROMs (3 MB)      %s of non-filler bytes exported (%s in sample-table samples: table*/ files or "
                 "unused/, %d bytes in unused/unreferenced_*.raw, %d bytes not covered)"
                 % (pct(((c | u) & realp).sum(), realp.sum()), pct(n_tab, realp.sum()), (u & realp).sum(),
                    (realp & ~c & ~u).sum()))

    # ---- sound program: music parts played by the 27 tracks
    w = lambda a: region[a] | region[a + 1] << 8
    t = w(0x4757 + 2)
    parts = set()
    for code in range(region[t] + 1):
        a = w(t + 1 + 2 * code) + 1
        while 0 < region[a] < 0xF0:
            parts.add(region[a]); a += 1
    ptrs = {w(0x4BCB + 2 * i) for i in range(4, 37)}
    lines.append("sound program        %d/%d music commands exported, %d/%d musical parts played by them"
                 % (region[t] + 1, region[t] + 1, len({p for p in parts if 4 <= p <= 36}), len(ptrs)))

    lines.append("")
    lines.append("Known gaps:")
    lines += ["  - " + g for g in KNOWN_GAPS]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(outdir, "coverage.txt"), "w") as f:
        f.write(text)
    log("coverage (also in coverage.txt):\n" + text)
