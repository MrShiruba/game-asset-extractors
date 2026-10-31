"""Extraction routines used by the CLI."""
import json
import os

import numpy as np
from PIL import Image

from . import gfx, oki
from .sprites import BODY_PALETTES, PALETTE_USAGE, FrameRenderer, compose_on_baseline


def _mk(path):
    os.makedirs(path, exist_ok=True)
    return path


def _log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------- samples ----
# OKI samples the music drivers play (percussion), found in the recorded VGMs
MUSIC_SAMPLES = {"dbz": set(range(100, 105)), "dbz2": set(range(100, 117)) - {113}}

def extract_voices(rs, out, keep_blank=False):
    """OKI M6295 samples -> one VGM per sample (original ADPCM data, lossless).

    Files keep the slot number of the OKI table, so the gaps (silent placeholder
    slots) show how the game groups its samples.
    """
    from .sound import write_oki_sample_vgm
    d = _mk(os.path.join(out, "samples"))
    for f in os.listdir(d):  # files left by a previous run
        if f.startswith("oki_") and f.endswith((".wav", ".vgm", ".vox")):
            os.remove(os.path.join(d, f))
    rom = rs.oki
    index = []
    for num, start, end in oki.read_table(rom):
        size = end - start + 1
        if size <= 32 and not keep_blank:  # 22-byte silent placeholders
            continue
        name = f"oki_{num:03d}.vgm"
        write_oki_sample_vgm(os.path.join(d, name), rom, num, start, end, rs.game)
        entry = {"file": name, "slot": num, "sound_command": hex(0x80 | num),
                 "start": hex(start), "end": hex(end), "seconds": round(size * 2 / oki.OKI_RATE, 3)}
        if num in MUSIC_SAMPLES.get(rs.game, ()):
            entry["note"] = "drum sample used by the music"
        index.append(entry)
    with open(os.path.join(d, "index.json"), "w") as fh:
        json.dump(index, fh, indent=1)
    _log(f"  samples: {len(index)} VGM -> {d}")
    return index


# -------------------------------------------------------------- graphics ----
def _blocks(rs):
    return gfx.morton_blocks(gfx.decode_sprites(rs.sprites))


def _grid_rows(images, origins, per_row=10, pad=4):
    rows = []
    for i in range(0, len(images), per_row):
        rows.append(compose_on_baseline(images[i:i + per_row], origins[i:i + per_row], pad))
    w = max(r.shape[1] for r in rows)
    h = sum(r.shape[0] + pad for r in rows)
    out = np.zeros((h, w), np.uint8)
    y = 0
    for r in rows:
        out[y:y + r.shape[0], :r.shape[1]] = r
        y += r.shape[0] + pad
    return out


def _clean_pngs(d):
    """Remove PNGs written by a previous run in d and its frames_* subfolders."""
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(".png"):
                os.remove(os.path.join(root, f))


def _swatches(path, palettes, labels=None, size=16):
    """PNG showing palettes as rows of 16 colour squares."""
    img = np.zeros((len(palettes) * size, 16 * size, 3), np.uint8)
    for r, pal in enumerate(palettes):
        for c, rgb in enumerate(pal[:16]):
            img[r * size:(r + 1) * size - 1, c * size:(c + 1) * size - 1] = rgb
    Image.fromarray(img).save(path, optimize=True)


def extract_characters(rs, out, blocks=None, frames=True, sheets=True, p2=True):
    """Rebuild every fighter frame. Indexed 16-colour PNGs (pen 0 = transparent),
    i.e. the exact pixel values of the ROM with the palette attached."""
    if rs.game == "dbz2":
        from .dbz2 import extract as x2
        return x2.extract_characters(rs, out, _blocks(rs) if blocks is None else blocks, frames=frames)
    blocks = _blocks(rs) if blocks is None else blocks
    fr = FrameRenderer(rs.maincpu, blocks)
    base = _mk(os.path.join(out, "sprites", "characters"))
    summary = {}
    for ch in fr.characters():
        cdir = _mk(os.path.join(base, f"{ch['index']:02d}_{ch['name']}"))
        _clean_pngs(cdir)
        sets = {"p1": [fr.palette(a) for a in ch["variants_p1"]]}
        if p2:
            sets["p2"] = [fr.palette(a) for a in ch["variants_p2"]]
        _swatches(os.path.join(cdir, "palettes.png"), sets["p1"] + sets.get("p2", []))
        meta = {"bank": hex(ch["bank"]),
                "palettes_p1": [hex(a) for a in ch["variants_p1"]],
                "palettes_p2": [hex(a) for a in ch["variants_p2"]],
                "palettes_png": "rows = P1 v0..v3 then P2 v0..v3",
                "palette_usage": PALETTE_USAGE,
                "frames": []}
        banks = [("normal", ch["bank"])]
        if ch["special_bank"]:
            banks.append(("special", ch["special_bank"]))
            meta["special_bank"] = hex(ch["special_bank"])
        total = 0
        for kind, bank in banks:
            rendered = []
            for slot, n, addr in fr.frame_table(bank):
                pens, ox, oy = fr.render(addr, n)
                rendered.append((slot, pens, ox, oy))
                meta["frames"].append({"set": kind, "slot": slot, "address": hex(addr),
                                       "pieces": n, "anchor": [ox, oy],
                                       "size": [pens.shape[1], pens.shape[0]]})
            total += len(rendered)
            if frames:
                fdir = _mk(os.path.join(cdir, f"frames_{kind}"))
                for slot, pens, _, _ in rendered:
                    gfx.to_png(os.path.join(fdir, f"{slot:03d}.png"), pens, sets["p1"][0])
            if sheets and rendered:
                sheet = _grid_rows([p for _, p, _, _ in rendered],
                                   [(ox, oy) for _, _, ox, oy in rendered])
                for pname, variants in sets.items():
                    gfx.to_png(os.path.join(cdir, f"sheet_{kind}_{pname}.png"), sheet, variants[0])
                    for label, v in BODY_PALETTES.get(ch["name"], {}).items():
                        gfx.to_png(os.path.join(cdir, f"sheet_{kind}_{pname}_{label}.png"), sheet, variants[v])
        with open(os.path.join(cdir, "frames.json"), "w") as fh:
            json.dump(meta, fh, indent=1)
        summary[ch["name"]] = total
        _log(f"  {ch['name']:<20} {total:4d} frames")
    return summary


def _dump_group(d, rendered, pal, sheet_name="sheet.png", per_row=10):
    """One indexed PNG per frame + a sheet (frames bottom-aligned, anchors in JSON)."""
    _mk(d)
    meta = []
    for i, pens, ox, oy, addr in rendered:
        name = f"{i:03d}" if isinstance(i, int) else str(i)
        gfx.to_png(os.path.join(d, name + ".png"), pens, pal)
        meta.append({"entry": i, "address": hex(addr), "anchor": [ox, oy],
                     "size": [pens.shape[1], pens.shape[0]]})
    if rendered:
        sheet = _grid_rows([r[1] for r in rendered], [(0, r[1].shape[0]) for r in rendered], per_row)
        gfx.to_png(os.path.join(d, sheet_name), sheet, pal)
    return meta


def extract_objects(rs, out, blocks=None):
    """Effects, projectiles, texts, portraits, credits (spectators: see extract_stages)."""
    if rs.game == "dbz2":
        from .dbz2 import extract as x2
        return x2.extract_objects(rs, out, _blocks(rs) if blocks is None else blocks)
    from .objects import TABLES, ObjectExtractor
    blocks = _blocks(rs) if blocks is None else blocks
    fr = FrameRenderer(rs.maincpu, blocks)
    ox_ = ObjectExtractor(fr)
    chars = fr.characters()
    base = _mk(os.path.join(out, "sprites", "common"))
    _clean_pngs(base)
    index = {}
    for name, table, hdr, maxn, rule in TABLES:
        rendered = ox_.render_table(table, hdr, maxn)
        if rule[0] == "player":
            # shared frames, coloured with each fighter's palette (P1 and P2)
            meta = None
            for ch in chars:
                for side in ("p1", "p2"):
                    pal = fr.palette(ch[f"variants_{side}"][0])
                    sub = os.path.join(base, name, f"{ch['index']:02d}_{ch['name']}")
                    if side == "p1":
                        meta = _dump_group(sub, rendered, pal)
                    elif rendered:
                        sheet = _grid_rows([r[1] for r in rendered],
                                           [(0, r[1].shape[0]) for r in rendered], 10)
                        gfx.to_png(os.path.join(sub, "sheet_p2.png"), sheet, pal)
        else:
            meta = _dump_group(os.path.join(base, name), rendered, ox_.palette(rule, chars))
            if name == "effects" and rendered:
                # many effects take the fighter's colour +1 / +2 (table 0xB1E0, object scripts)
                sheet = _grid_rows([r[1] for r in rendered], [(0, r[1].shape[0]) for r in rendered], 10)
                for ch in chars:
                    sub = _mk(os.path.join(base, name, "by_fighter", f"{ch['index']:02d}_{ch['name']}"))
                    for v in (1, 2):
                        gfx.to_png(os.path.join(sub, f"sheet_v{v}.png"), sheet, fr.palette(ch["variants_p1"][v]))
        index[name] = {"table": hex(table), "palette": list(map(str, rule)), "frames": meta}
        _log(f"  {name:<18} {len(rendered):4d} frames")
    # portraits (select screen), one folder per character
    pdir = os.path.join(base, "portraits")
    n = 0
    for cname, rendered, pal in ox_.portraits(chars):
        _dump_group(os.path.join(pdir, cname), rendered, pal)
        n += len(rendered)
    _log(f"  {'portraits':<18} {n:4d} frames")
    # shared palettes of every stage, for recolouring
    _swatches(os.path.join(base, "shared_palettes_by_stage.png"),
              [p for s in range(9) for p in ox_.shared_palettes(s)])
    with open(os.path.join(base, "objects.json"), "w") as fh:
        json.dump(index, fh, indent=1)


def extract_sprite_blocks(rs, out, blocks=None, per_sheet=64):
    """Raw K053247 sprite ROM, arranged in 128x128 blocks (grayscale)."""
    blocks = _blocks(rs) if blocks is None else blocks
    d = _mk(os.path.join(out, "sprites", "raw_blocks"))
    pal = gfx.gray_palette()
    used = [i for i in range(len(blocks)) if blocks[i].any() and not (blocks[i] == 15).all()]
    n = 0
    for s in range(0, len(used), per_sheet):
        idx = used[s:s + per_sheet]
        sheet = gfx.grid(blocks[idx], 8, pad=2, fill=0)
        gfx.to_png(os.path.join(d, f"blocks_{idx[0]:04d}-{idx[-1]:04d}.png"), sheet, pal)
        n += 1
    _log(f"  raw sprite blocks: {len(used)} blocks in {n} sheets -> {d}")


def extract_tiles(rs, out):
    """K056832 8x8 tiles and K053936 (PSAC) 16x16 background tiles, grayscale."""
    d = _mk(os.path.join(out, "tiles"))
    pal = gfx.gray_palette()

    def dump(tiles, prefix, cols, per_sheet):
        keep = np.array([t.any() and not (t == 15).all() for t in tiles])
        idx = np.nonzero(keep)[0]
        for s in range(0, len(idx), per_sheet):
            part = idx[s:s + per_sheet]
            gfx.to_png(os.path.join(d, f"{prefix}_{part[0]:05d}.png"),
                       gfx.grid(tiles[part], cols, pad=1), pal, transparent0=False)
        return len(idx)

    n1 = dump(gfx.decode_k056832(rs.tiles), "k056832_8x8", 64, 64 * 64)
    l0, l1 = rs.psac
    n2 = dump(gfx.decode_psac(l0), "psac0_16x16", 32, 32 * 32)
    n3 = dump(gfx.decode_psac(l1), "psac1_16x16", 32, 32 * 32)
    _log(f"  tiles: {n1} 8x8, {n2}+{n3} PSAC 16x16 -> {d}")


def extract_palettes(rs, out):
    """Every palette block referenced by the program, as a swatch image + JSON."""
    if rs.game == "dbz2":
        from .dbz2 import extract as x2
        return x2.extract_palettes(rs, out)
    d = _mk(os.path.join(out, "palettes"))
    m = rs.maincpu
    w = lambda a: int.from_bytes(m[a:a + 2], "big")
    entries = []
    # character palettes (raw 16-colour palettes 0x1F96E..0x2056E)
    for a in range(0x1F96E, 0x2056E, 32):
        entries.append(("char", a, gfx.xrgb555_to_rgb([w(a + 2 * k) for k in range(16)])))
    # counted palette blocks referenced by pointers (format: n, (n+1)*16 colours)
    seen = set()
    for i in range(0, 0x80000 - 4, 2):
        v = int.from_bytes(m[i:i + 4], "big")
        if 0x1E000 <= v < 0x24800 and v % 2 == 0 and v not in seen:
            n = w(v)
            if n < 32:
                cols = [w(v + 2 + k * 2) for k in range((n + 1) * 16)]
                if all(c < 0x8000 for c in cols) and len(set(cols)) > 4:
                    seen.add(v)
                    for p in range(n + 1):
                        entries.append((f"block_{v:05x}", v + 2 + p * 32,
                                        gfx.xrgb555_to_rgb(cols[p * 16:(p + 1) * 16])))
    sw = 12
    img = np.zeros((len(entries) * sw, 16 * sw, 3), np.uint8)
    for r, (_, _, cols) in enumerate(entries):
        for c, rgb in enumerate(cols):
            img[r * sw:(r + 1) * sw - 1, c * sw:(c + 1) * sw - 1] = rgb
    Image.fromarray(img).save(os.path.join(d, "palettes.png"))
    with open(os.path.join(d, "palettes.json"), "w") as fh:
        json.dump([{"group": g, "address": hex(a), "colors": ["#%02x%02x%02x" % c for c in cols]}
                   for g, a, cols in entries], fh, indent=0)
    _log(f"  palettes: {len(entries)} -> {d}")


def extract_stages(rs, out, blocks=None):
    """One folder per stage: both rotate/zoom layers, tile animations, spectators,
    the tiles each layer uses (coloured), and a JSON with the stage data."""
    if rs.game == "dbz2":
        from .dbz2 import extract as x2
        return x2.extract_stages(rs, out, _blocks(rs) if blocks is None else blocks)
    from .objects import ObjectExtractor
    from .stages import NUM_STAGES, STAGE_MAPS, STAGE_PALETTES, StageRenderer, save_layer
    d = _mk(os.path.join(out, "stages"))
    _clean_pngs(d)
    sr = StageRenderer(rs.maincpu, *rs.psac)
    blocks = _blocks(rs) if blocks is None else blocks
    ox_ = ObjectExtractor(FrameRenderer(rs.maincpu, blocks))
    spect = {}
    for stage, rec, colour, rendered, pal in ox_.spectators():
        spect.setdefault(stage, []).append((rec, rendered, pal))
    n_anim = 0
    for st in range(NUM_STAGES):
        sd = _mk(os.path.join(d, f"stage{st}"))
        meta = {"music_command": hex(0x01 + st),
                "maps": {"back": hex(sr.l(STAGE_MAPS + 16 * st)), "front": hex(sr.l(STAGE_MAPS + 16 * st + 4))},
                "palettes": {"back": hex(sr.l(STAGE_PALETTES + 8 * st)),
                             "front": hex(sr.l(STAGE_PALETTES + 8 * st + 4))},
                "animations": {}}
        for which, name in ((0x500000, "back"), (0x508000, "front")):
            pal = sr.layer_palette(st, which)
            save_layer(os.path.join(sd, f"{name}.png"), sr.layer(st, which), pal)
            save_layer(os.path.join(sd, f"tiles_{name}.png"), sr.tiles_sheet(st, which), pal)
        # animated tile patches: one folder per patch, frames + horizontal sheet
        for k, a in enumerate(sr.animations(st)):
            pal = sr.layer_palette(st, a["which"])
            key = f"{a['layer']}_{k}"
            adir = _mk(os.path.join(sd, "animations", key))
            for i, pens in enumerate(a["frames"]):
                save_layer(os.path.join(adir, f"{i:02d}.png"), pens, pal)
            h, w = a["frames"][0].shape
            sheet = np.zeros((h, (w + 4) * len(a["frames"]) - 4), np.uint8)
            for i, pens in enumerate(a["frames"]):
                sheet[:, i * (w + 4):i * (w + 4) + w] = pens
            save_layer(os.path.join(adir, "sheet.png"), sheet, pal)
            meta["animations"][key] = {
                "position_px": [a["x"] * 16, a["y"] * 16], "size_cells": [a["cols"], a["rows"]],
                "play_order": a["sequence"], "rom_addresses": a["addresses"]}
            n_anim += 1
        # spectators (sprites) drawn on this stage, with the stage sprite palettes
        for rec, rendered, pal in spect.get(st, []):
            _dump_group(os.path.join(sd, "spectators", str(rec)), rendered, pal)
        with open(os.path.join(sd, "stage.json"), "w") as fh:
            json.dump(meta, fh, indent=1)
    old = os.path.join(d, "animations.json")
    if os.path.exists(old):
        os.remove(old)
    _log(f"  stages: {NUM_STAGES} folders (back, front, tiles, {n_anim} animations, spectators) -> {d}")

def extract_screens(rs, out):
    """HUD, title/logos, select screen, hi-scores, endings, test mode (K056832 pages)."""
    if rs.game == "dbz2":
        from .dbz2 import extract as x2
        return x2.extract_screens(rs, out)
    from .screens import ScreenRenderer
    from .sprites import CHAR_NAMES
    from .stages import save_layer
    d = _mk(os.path.join(out, "screens"))
    _clean_pngs(d)
    td = _mk(os.path.join(d, "tiles"))
    sr = ScreenRenderer(rs.maincpu, rs.tiles)
    shots = sr.all_screens(CHAR_NAMES)
    for name, pens, pal, src in shots:
        save_layer(os.path.join(d, name + ".png"), pens, pal)
        save_layer(os.path.join(td, name + ".png"), sr.tiles_sheet(src), pal)
    # tile glyphs: select-screen faces, fonts, STAGE / FIGHT! / GAME OVER, names...
    from .screens import HUD_PALETTES, GlyphRenderer
    gr = GlyphRenderer(rs.maincpu, rs.tiles)
    glyphs = dict(gr.glyphs())
    fd = _mk(os.path.join(d, "faces"))
    face_ids = set()
    for name, g, p1, p2 in gr.faces(CHAR_NAMES):
        if g in glyphs:
            face_ids.add(g)
            gfx.to_png(os.path.join(fd, f"{name}_p1.png"), glyphs[g], p1)
            gfx.to_png(os.path.join(fd, f"{name}_p2.png"), glyphs[g], p2)
    gd = _mk(os.path.join(d, "glyphs"))
    hud = sr.palette256(HUD_PALETTES)
    cols = gr.string_colours()
    gray = [(i * 17, i * 17, i * 17) for i in range(16)] * 16
    for g, pens in glyphs.items():
        if g in face_ids:
            continue
        if g in cols:
            save_layer(os.path.join(gd, f"{g:03d}.png"), np.where(pens != 0, pens | (cols[g] << 4), 0).astype(np.uint8), hud)
        else:
            save_layer(os.path.join(gd, f"{g:03d}_nocolour.png"), pens, gray)
    _log(f"  screens: {len(shots)} pages 512x256 -> {d}")
