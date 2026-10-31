"""Extraction routines for Dragon Ball Z 2 (called by dbz_arcade_rip.extract when the romset is dbz2)."""
import json
import os
from collections import OrderedDict

import numpy as np

from ..sprites import compose_on_baseline
from ..stages import save_layer
from .maps import COUNTS, K056832_NAMES, KIND_NAMES, Maps
from .objects import scripts as object_scripts
from .objpal import CONTEXT, OBSERVED
from .sprites import (CHAR_NAMES, COMMON_PALETTES, SHARED_BANK, STAGE_SPRITE_PALETTES,
                      FrameRenderer2, palette128)
from .stages import LAYOUTS, NUM_STAGES, StageInfo

GRAY = [(i * 17, i * 17, i * 17) for i in range(16)] * 16


def _mk(path):
    os.makedirs(path, exist_ok=True)
    return path


def _log(msg):
    print(msg, flush=True)


def _clean_pngs(d):
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(".png"):
                os.remove(os.path.join(root, f))


def _pad256(pal):
    pal = list(pal[:256])
    return pal + [(0, 0, 0)] * (256 - len(pal))


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


def _swatches(path, palettes, size=16):
    from PIL import Image
    img = np.zeros((len(palettes) * size, 16 * size, 3), np.uint8)
    for r, pal in enumerate(palettes):
        for c, rgb in enumerate(pal[:16]):
            img[r * size:(r + 1) * size - 1, c * size:(c + 1) * size - 1] = rgb
    Image.fromarray(img).save(path, optimize=True)


# ------------------------------------------------------------- characters ----
def extract_characters(rs, out, blocks, frames=True, **_):
    """Fighters: one sheet per colour set (128-colour indexed PNG: 8 palettes,
    index = colour offset * 16 + pen, every pen 0 transparent)."""
    fr = FrameRenderer2(rs.maincpu, blocks)
    base = _mk(os.path.join(out, "sprites", "characters"))
    for ch in fr.characters():
        cdir = _mk(os.path.join(base, f"{ch['index']:02d}_{ch['name']}"))
        _clean_pngs(cdir)
        sets = [fr.palettes(a, 8) for a in ch["colour_sets"]]
        _swatches(os.path.join(cdir, "palettes.png"), [p for s in sets for p in s])
        rendered, meta = [], []
        for slot, n, addr in fr.frame_table(ch["bank"]):
            pens, ox, oy, used = fr.render(addr, n)
            rendered.append((slot, pens, ox, oy))
            meta.append({"slot": slot, "address": hex(addr), "pieces": n, "anchor": [ox, oy],
                         "size": [pens.shape[1], pens.shape[0]], "colour_offsets": used})
        if frames:
            fdir = _mk(os.path.join(cdir, "frames"))
            for slot, pens, _, _ in rendered:
                save_layer(os.path.join(fdir, f"{slot:03d}.png"), pens, _pad256(palette128(sets[0])))
        sheet = _grid_rows([p for _, p, _, _ in rendered], [(ox, oy) for _, _, ox, oy in rendered])
        for k, s in enumerate(sets):
            save_layer(os.path.join(cdir, f"sheet_colour{k + 1}.png"), sheet, _pad256(palette128(s)))
        with open(os.path.join(cdir, "frames.json"), "w") as fh:
            json.dump({"bank": hex(ch["bank"]),
                       "colour_sets": [hex(a) for a in ch["colour_sets"]],
                       "palettes_png": "4 colour sets x 8 palettes (rows 0-7 = colour 1, 8-15 = colour 2...)",
                       "png_index": "colour offset * 16 + pen (0-127); pen 0 of every palette is transparent",
                       "frames": meta}, fh, indent=1)
        _log(f"  {ch['name']:<12} {len(rendered):4d} frames")


# ---------------------------------------------------------------- objects ----
class _ObjColours:
    """Palette of a shared-bank frame:
    1. as seen in palette RAM while the running game drew it (objpal.OBSERVED);
    2. stage objects: the stage sprite palettes given by the stage object table;
    3. otherwise unknown (grayscale)."""

    def __init__(self, fr):
        m = fr.m
        si = StageInfo(m)
        scr = {sid: frames for sid, _, frames, _, _ in object_scripts(m)}
        self.stage_rule = {}
        self.stage_of = {}
        for st in range(NUM_STAGES):
            spal = int.from_bytes(m[STAGE_SPRITE_PALETTES + 4 * st:STAGE_SPRITE_PALETTES + 4 * st + 4], "big")
            for ob in si.objects(st):
                c = ob["colour"] & 0x1F
                if not 22 <= c <= 24:
                    continue
                rule = {k: spal + 32 * (c - 22 + k) for k in range(8) if c + k <= 24}
                for f in scr.get(ob["script"], []):
                    self.stage_rule.setdefault(f, rule)
                    self.stage_of.setdefault(f, st)

    def rule(self, frame):
        """-> (rule, source); rule = ("fighter", owners) / {offset: palette address} / None"""
        if frame in OBSERVED:
            return OBSERVED[frame], "game"
        if frame in self.stage_rule:
            return self.stage_rule[frame], "stage table"
        return None, "unknown"


def _remap(pens, offsets_to_slot):
    out = np.zeros_like(pens)
    for coff, slot in offsets_to_slot.items():
        sel = (pens >> 4) == coff
        out[sel] = (pens[sel] & 15) | (slot << 4)
    out[(pens & 15) == 0] = 0
    return out


def _sheets_fixed(frames, fr, gdir, prefix="sheet"):
    """frames: list of (f, pens, rule dict, used). One 256-colour sheet per 16 ROM palettes."""
    chunks, cur, slots = [], [], OrderedDict()
    for item in frames:
        need = [item[2][c] for c in item[3] if c in item[2]]
        new = [a for a in dict.fromkeys(need) if a not in slots]
        if len(slots) + len(new) > 16 and cur:
            chunks.append((cur, slots))
            cur, slots = [], OrderedDict()
        for a in need:
            slots.setdefault(a, len(slots))
        cur.append(item)
    if cur:
        chunks.append((cur, slots))
    for k, (items, slots) in enumerate(chunks):
        flat = [c for a in slots for c in fr.palettes(a, 1)[0]]
        imgs = [_remap(p, {c: slots[r[c]] for c in u if c in r}) for _, p, r, u in items]
        name = f"{prefix}.png" if len(chunks) == 1 else f"{prefix}_{k + 1}.png"
        save_layer(os.path.join(gdir, name), _grid_rows(imgs, [(0, i.shape[0]) for i in imgs]), _pad256(flat))


def extract_objects(rs, out, blocks, **_):
    """Shared sprite bank 0x8E900 (effects, fight texts, select screen, stage props,
    ending props), one folder per place where the game shows the frames."""
    fr = FrameRenderer2(rs.maincpu, blocks)
    col = _ObjColours(fr)
    chars = fr.characters()
    base = _mk(os.path.join(out, "sprites", "common"))
    _clean_pngs(base)
    bank = fr.frame_table(SHARED_BANK, 832)
    folders = OrderedDict()
    sources = {}
    for f, n, a in bank:
        r, src = col.rule(f)
        sources[f] = src
        folder = CONTEXT.get(f)
        if folder is None and src == "stage table":
            folder = "stage%02d" % col.stage_of[f]
        folder = folder or "unknown"
        folders.setdefault(folder, []).append((f, n, a, r, src))
    index = {}
    for folder in sorted(folders):
        gdir = _mk(os.path.join(base, folder))
        fighter, fixed, gray, meta = [], [], [], []
        for f, n, a, r, src in folders[folder]:
            pens, ox, oy, used = fr.render(a, n)
            if isinstance(r, tuple):
                owner = chars[r[1][0]] if r[1] else chars[0]
                save_layer(os.path.join(gdir, f"{f:03d}.png"), pens,
                           _pad256(palette128(fr.palettes(owner["colour_sets"][0], 8))))
                fighter.append((f, pens, r[1]))
                colour = {"fighter": [CHAR_NAMES[i] for i in r[1]]}
            elif isinstance(r, dict):
                slots = OrderedDict((r[c], None) for c in used if c in r)
                slot = {addr: i for i, addr in enumerate(slots)}
                img = _remap(pens, {c: slot[r[c]] for c in used if c in r})
                flat = [c for addr in slots for c in fr.palettes(addr, 1)[0]]
                save_layer(os.path.join(gdir, f"{f:03d}.png"), img, _pad256(flat))
                fixed.append((f, pens, r, used))
                colour = {str(c): hex(x) for c, x in r.items()}
            else:
                save_layer(os.path.join(gdir, f"{f:03d}_nocolour.png"), pens & 15, GRAY)
                gray.append((f, pens & 15))
                colour = None
            meta.append({"frame": f, "address": hex(a), "anchor": [ox, oy],
                         "colour": colour, "colour_source": src})
        if fighter:
            owners = sorted({i for *_, o in fighter for i in o}) or list(range(len(chars)))
            if not folder.startswith("effects_shared") and folder.startswith("effects_"):
                owners = [CHAR_NAMES.index(folder[len("effects_"):])]
            sheet = _grid_rows([p for _, p, _ in fighter], [(0, p.shape[0]) for _, p, _ in fighter])
            for i in owners:
                ch = chars[i]
                name = "sheet.png" if len(owners) == 1 else f"sheet_{ch['index']:02d}_{ch['name']}.png"
                save_layer(os.path.join(gdir, name), sheet, _pad256(palette128(fr.palettes(ch["colour_sets"][0], 8))))
        if fixed:
            _sheets_fixed(fixed, fr, gdir, "sheet" if not fighter else "sheet_fixed")
        if gray:
            # grayscale: one sheet per run of consecutive frames
            runs, cur = [], []
            for f, p in gray:
                if cur and f != cur[-1][0] + 1:
                    runs.append(cur)
                    cur = []
                cur.append((f, p))
            runs.append(cur)
            for run in runs:
                save_layer(os.path.join(gdir, f"sheet_{run[0][0]:03d}-{run[-1][0]:03d}_nocolour.png"),
                           _grid_rows([p for _, p in run], [(0, p.shape[0]) for _, p in run]), GRAY)
        index[folder] = meta
    with open(os.path.join(base, "common.json"), "w") as fh:
        json.dump({"bank": hex(SHARED_BANK),
                   "folders": {
                       "effects_<fighter>": "effects seen thrown by that fighter only (its colours)",
                       "effects_shared": "effects seen with several fighters: one sheet per fighter",
                       "fight": "fight texts (ROUND, FIGHT!, WIN...) and other fixed-colour fight sprites",
                       "select_screen": "names, faces, logo and cursors of the select screen",
                       "stageNN": "props placed on the stage (stage sprite palettes)",
                       "ending_<fighter>": "sprites seen during that fighter's ending",
                       "unknown": "never seen drawn while emulating the game: grayscale"},
                   "colour_source": {"game": "palette held by palette RAM when the running game drew the frame "
                                             "(68000 emulation: attract mode, fights, select screen, endings)",
                                     "stage table": "stage object: stage sprite palettes (table 0x10CD4)",
                                     "unknown": "never seen drawn: grayscale *_nocolour.png"},
                   "frames": index}, fh, indent=1)
    n = {k: sum(1 for v in sources.values() if v == k) for k in ("game", "stage table", "unknown")}
    _log(f"  common sprites: {len(bank)} frames in {len(folders)} folders (colour seen in the game: {n['game']}, "
         f"stage table: {n['stage table']}, grayscale: {n['unknown']}) -> {base}")


# ----------------------------------------------------------------- stages ----
def _sheet_h(frames, pad=4):
    h = max(f.shape[0] for f in frames)
    out = np.zeros((h, sum(f.shape[1] + pad for f in frames) - pad), np.uint8)
    x = 0
    for f in frames:
        out[:f.shape[0], x:x + f.shape[1]] = f
        x += f.shape[1] + pad
    return out


def stage_codes_used(m):
    si = StageInfo(m)
    used = set()
    for st in range(NUM_STAGES):
        for lay in LAYOUTS:
            used.update(si.codes(st, lay))
            for ch in si.animations(st, lay):
                used.update(c for _, c in ch["steps"])
    return used


def extract_stages(rs, out, blocks, **_):
    """One folder per stage (22): ground and sky layouts, both PSAC layers,
    animated patches, sprite objects, tiles used, stage.json."""
    m = rs.maincpu
    mp = Maps(m, psac=rs.psac)
    si = StageInfo(m)
    fr = FrameRenderer2(m, blocks)
    scripts = {sid: frames for sid, _, frames, _, _ in object_scripts(m)}
    frame_at = {s: (n, a) for s, n, a in fr.frame_table(SHARED_BANK, 832)}
    d = _mk(os.path.join(out, "stages"))
    _clean_pngs(d)
    rounds = si.rounds()
    n_anim = 0
    for st in range(NUM_STAGES):
        sd = _mk(os.path.join(d, f"stage{st:02d}"))
        used_by = [{"base_stage": b, "round": r + 1, "layout": "ground" if r % 2 == 0 else "sky"}
                   for b, r in rounds.get(st, [])]
        meta = {"used_by": used_by,
                "music_command": sorted({hex(0x01 + b) for b, _ in rounds.get(st, [])}),
                "layouts": {}}
        for lay, lname in LAYOUTS.items():
            back, front = si.codes(st, lay)
            lm = {"rule": "variable 0x487768 = %d: set at round start, %s" % (
                      lay, "rounds 2 and 4" if lay == 0 else "rounds 1 and 3"),
                  "back": {"map_code": hex(back), "map": hex(mp.address(back)), "palette": hex(mp.palette_address(back))},
                  "front": {"map_code": hex(front), "map": hex(mp.address(front)), "palette": hex(mp.palette_address(front))},
                  "animations": {}}
            layers = {}
            for code, which in ((back, "back"), (front, "front")):
                kind = (code >> 14) & 3
                mapd = mp.load(code)
                pal = mp.palette256(code)
                layers[kind] = (pal, [mapd["cells"]])
                save_layer(os.path.join(sd, f"{lname}_{which}.png"), mp.render(kind, mapd["cells"]), pal)
            for k, chan in enumerate(si.animations(st, lay)):
                codes = list(dict.fromkeys(c for _, c in chan["steps"]))
                if not codes:
                    continue
                kind = (codes[0] >> 14) & 3
                pal = layers.get(kind, (mp.palette256(codes[0]), []))[0]
                key = f"{lname}_{k}"
                adir = _mk(os.path.join(sd, "animations", key))
                pats = [mp.load(c) for c in codes]
                imgs = [mp.render(kind, p["cells"]) for p in pats]
                for i, img in enumerate(imgs):
                    save_layer(os.path.join(adir, f"{i:02d}.png"), img, pal)
                save_layer(os.path.join(adir, "sheet.png"), _sheet_h(imgs), pal)
                if kind in layers:
                    layers[kind][1].extend(p["cells"] for p in pats)
                lm["animations"][key] = {
                    "layer": KIND_NAMES[kind], "position_cells": [pats[0]["x"], pats[0]["y"]],
                    "start_delay": chan["start_delay"],
                    "steps": [{"frame": codes.index(c), "frames_shown": dl} for dl, c in chan["steps"]],
                    "loop_to_step": chan["loop_to"],
                    "map_codes": [hex(c) for c in codes]}
                n_anim += 1
            for kind, (pal, cell_lists) in layers.items():
                which = "back" if kind == 1 else "front"
                save_layer(os.path.join(sd, f"tiles_{lname}_{which}.png"), mp.tiles_sheet(kind, cell_lists), pal)
            meta["layouts"][lname] = lm
        # sprite objects placed on the stage (stage sprite palettes 22-24)
        spal = int.from_bytes(m[STAGE_SPRITE_PALETTES + 4 * st:STAGE_SPRITE_PALETTES + 4 * st + 4], "big")
        objs = []
        for i, ob in enumerate(si.objects(st)):
            frames = [f for f in scripts.get(ob["script"], []) if f in frame_at]
            c = ob["colour"] & 0x1F
            pals = [fr.palettes(spal + 32 * (c - 22 + k), 1)[0] if 22 <= c + k <= 24 else
                    fr.palettes(COMMON_PALETTES + 32 * (c + k - 16), 1)[0] if 16 <= c + k <= 21 else
                    [(0, 0, 0)] * 16 for k in range(8)]
            odir = _mk(os.path.join(sd, "sprites", f"{LAYOUTS.get(ob['layout'], ob['layout'])}_{i}"))
            imgs = []
            for f in frames:
                n, a = frame_at[f]
                pens, ox, oy, _ = fr.render(a, n)
                save_layer(os.path.join(odir, f"{f:03d}.png"), pens, _pad256(palette128(pals)))
                imgs.append(pens)
            if imgs:
                save_layer(os.path.join(odir, "sheet.png"),
                           _grid_rows(imgs, [(0, i.shape[0]) for i in imgs]), _pad256(palette128(pals)))
            objs.append(dict(ob, folder=os.path.basename(odir), frames=frames,
                             colour=hex(ob["colour"]), script=ob["script"]))
        meta["sprites"] = objs
        meta["sprite_palettes"] = hex(spal)
        with open(os.path.join(sd, "stage.json"), "w") as fh:
            json.dump(meta, fh, indent=1)
    _log(f"  stages: {NUM_STAGES} folders ({n_anim} animations) -> {d}")


# ---------------------------------------------------------------- screens ----
def extract_screens(rs, out, **_):
    """Every tilemap of the map directory not used by a stage: K056832 pages (title,
    test mode, hi-scores, cut-scene pictures...) and PSAC pages (cut-scenes, endings).
    Whole pages are 512x256 (K056832) / 1024x512 (PSAC); patches are cut to their size."""
    m = rs.maincpu
    mp = Maps(m, tile_region=rs.tiles, psac=rs.psac)
    stage_used = stage_codes_used(m)
    from .names import screen_names
    names = screen_names(m)
    for i, n in K056832_NAMES.items():
        names[i] = n
    d = _mk(os.path.join(out, "screens"))
    _clean_pngs(d)
    index = {}
    total = 0
    for kind in (0, 1, 2):
        kd = _mk(os.path.join(d, KIND_NAMES[kind]))
        td = _mk(os.path.join(kd, "tiles"))
        entries = []
        for i in range(COUNTS[kind]):
            code = kind << 14 | i
            if code in stage_used:
                continue
            a = mp.address(code)
            if a < 0x400 or a >= len(m) or a & 1:
                continue
            mapd = mp.load(code)
            if not mapd["full"] and (mapd["x"] >= 64 or mapd["y"] >= 64):
                continue
            pal = mp.palette256(code)
            name = f"{i:03d}" + (f"_{names[code]}" if code in names else "")
            if names.get(code) == "blank":
                continue
            save_layer(os.path.join(kd, name + ".png"), mp.render(kind, mapd["cells"]), pal)
            save_layer(os.path.join(td, name + ".png"), mp.tiles_sheet(kind, [mapd["cells"]]), pal)
            entries.append({"file": name + ".png", "name": names.get(code), "map_code": hex(code), "map": hex(a),
                            "palette": hex(mp.palette_address(code)),
                            "whole_page": mapd["full"],
                            "position_cells": [mapd["x"], mapd["y"]], "size_cells": [mapd["cols"], mapd["rows"]]})
        index[KIND_NAMES[kind]] = entries
        total += len(entries)
    with open(os.path.join(d, "screens.json"), "w") as fh:
        json.dump(index, fh, indent=1)
    _log(f"  screens: {total} maps -> {d}")


# --------------------------------------------------------------- palettes ----
def extract_palettes(rs, out):
    """Fighter colour sets, common/stage sprite palettes and every map palette block."""
    from PIL import Image
    m = rs.maincpu
    fr = FrameRenderer2(m, None)
    mp = Maps(m)
    d = _mk(os.path.join(out, "palettes"))
    entries = []
    for ch in fr.characters():
        for k, a in enumerate(ch["colour_sets"]):
            for p, pal in enumerate(fr.palettes(a, 8)):
                entries.append((f"{ch['name']}_colour{k + 1}", a + 32 * p, pal))
    for p, pal in enumerate(fr.palettes(COMMON_PALETTES, 6)):
        entries.append(("sprites_common", COMMON_PALETTES + 32 * p, pal))
    for st in range(NUM_STAGES):
        a = int.from_bytes(m[STAGE_SPRITE_PALETTES + 4 * st:STAGE_SPRITE_PALETTES + 4 * st + 4], "big")
        for p, pal in enumerate(fr.palettes(a, 3)):
            entries.append((f"stage{st:02d}_sprites", a + 32 * p, pal))
    seen = set()
    for kind in (0, 1, 2):
        for i in range(COUNTS[kind]):
            a = mp.palette_address(kind << 14 | i)
            if a in seen or a < 0x400 or a >= len(m):
                continue
            seen.add(a)
            n = mp.w(a) + 1
            if n > 16:
                continue
            for p, pal in enumerate(fr.palettes(a + 2, n)):
                entries.append((f"{KIND_NAMES[kind]}_{i:03d}", a + 2 + 32 * p, pal))
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
