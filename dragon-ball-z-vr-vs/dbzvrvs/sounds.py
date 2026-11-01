"""Music and sound commands, exported following the tables of the game's sound driver:
  table 1 = music (VGM), tables 2/4/6 = sound effects / voice lines / dialogues (raw PCM, one file per
  command or line), plus the samples only the music plays and the PCM data nothing plays."""
import os
from collections import Counter, defaultdict
from .soundboard import run_emu, finish_vgm, read_wav
from .pcm import (SEQ_TICK, pcm_samples, rate_of, write_raw_folder, write_json, note_channels, build_line)
from .dialogues import write_table6_info

MUSIC_COUNT = 27                   # table 1, codes 0..26
SOUND_TABLES = (2, 4, 6)          # sound-command tables of the driver (voices / SFX)
# tables 3/5/7 are the same commands as 2/4/6 for player 2 (checked: they play exactly the same)
TABLE_FOLDERS = {2: "table2-sfx", 4: "table4-voices", 6: "table6-dialogues"}
TABLE_WHAT = {2: "sound effects: each file is what one table 2 command plays",
              4: "voice lines: each file is what one table 4 command plays (pieces joined with the game's pauses, silence = 0x80)",
              6: "dialogue lines: t6_line_NNN-NNN = the samples the line is made of; each table 6 command chains two lines "
                 "(pieces joined with the game's pauses, silence = 0x80)"}


def export_music(exe, rpath, work, outdir, log):
    md = os.path.join(outdir, "table1-music")
    os.makedirs(md, exist_ok=True)
    tracks = []
    for code in range(MUSIC_COUNT):
        raw = os.path.join(work, "m.vgm")
        info, _ = run_emu(exe, rpath, 1, code, raw)
        title = "Track %02d" % (code + 1)
        fn = "t1_%03d.vgz" % code
        finish_vgm(raw, os.path.join(md, fn), title)
        n = int(info["samples"]); ls = int(info["loop_len"])
        tracks.append({"command": "t1_%03d" % code, "file": fn, "title": title, "length_s": round(n / 44100, 2),
                       "loop_s": round(ls / 44100, 2) if ls else None, "end": info["end"]})
        log("music t1_%03d: %6.1f s  %s" % (code, n / 44100, ("loop %.1f s" % (ls / 44100)) if ls else "no loop"))
    write_json(os.path.join(md, "table1.json"), tracks)


def ticks(part):
    """pauses between the pieces of a line, in 64-MIDI-tick steps"""
    return tuple(round((x[2] - part[0][2]) / SEQ_TICK) for x in part)


def run_commands(exe, rpath, region, work):
    """Runs every command of tables 2/4/6 once and logs the samples it starts:
    events = (sample, FD step, start time in 1/44100 s, RF5C68 channel)."""
    cmds, seen_hdr = [], {}
    for table in SOUND_TABLES:
        tptr = region[0x4757 + 2 * table] | region[0x4758 + 2 * table] << 8
        for code in range(region[tptr] + 1):
            c = {"table": table, "code": code, "name": "t%d_%03d" % (table, code)}
            cmds.append(c)
            hdr = region[tptr + 1 + 2 * code] | region[tptr + 2 + 2 * code] << 8
            if hdr in seen_hdr:
                c["same_as"] = seen_hdr[hdr]; continue
            seen_hdr[hdr] = c["name"]
            c["hdr"] = hdr
            w = os.path.join(work, "s.wav")
            _, st = run_emu(exe, rpath, table, code, w, 30, 0.2, logsamples=True, center=True)
            a = read_wav(w)
            if not len(a) or not a.any():
                c["silent"] = True; continue
            c["events"] = [tuple(x[:4]) for x in st]
    return cmds


def split_lines(region, cmds):
    """Cuts each command into lines (table 6: one line per MIDI channel, as the sequence stores them).
    A dialogue line comes back in several commands, sometimes with a pause 64 MIDI ticks longer or
    shorter (set by hand per command): returns, for each line, the version most commands use."""
    usage, first_part = defaultdict(Counter), {}
    aliases = Counter(c["same_as"] for c in cmds if "same_as" in c)   # commands sharing one sequence
    for c in cmds:
        if not c.get("events"):
            continue
        ev = c["events"]
        chans = note_channels(region, c["hdr"]) if c["table"] == 6 else None
        if chans and len(chans) == len(ev):
            c["parts"] = [[x for x, ch in zip(ev, chans) if ch == k] for k in sorted(set(chans), key=chans.index)]
        else:
            c["parts"] = [ev]
        if c["table"] == 6:
            for p in c["parts"]:
                k = tuple(x[0] for x in p)
                usage[k][ticks(p)] += 1 + aliases[c["name"]]
                first_part.setdefault((k, ticks(p)), p)
    return {k: first_part[(k, u.most_common(1)[0][0])] for k, u in usage.items()}


class Output:
    """Files of tables 2/4/6, written once per distinct sound."""
    def __init__(self):
        self.written = {}                     # (samples, step, pauses) -> "folder/name.raw"
        self.items = defaultdict(list)        # folder -> [(name, data, rate)]
        self.contained = defaultdict(set)     # sample -> files whose audio contains it
        self.names = set()

    def emit(self, folder, name, data, step, part):
        key = (tuple(x[0] for x in part), step, ticks(part))
        if key not in self.written:
            n, v = name, 1
            while (folder, n) in self.names:          # same name, other sound: never happens in this game
                v += 1
                n = "%s_v%d" % (name, v)
            self.names.add((folder, n))
            self.written[key] = "%s/%s.raw" % (folder, n)
            self.items[folder].append((n, data, rate_of(step)))
        for x in part:
            self.contained[x[0]].add(self.written[key])
        return self.written[key]


def write_commands(exe, rpath, region, work, outdir, cmds, line_ref, out, played):
    """One file per command (table 6: one per line). Returns the JSON of each table and the VGM count."""
    tmeta, n_vgm = defaultdict(list), 0
    for c in cmds:
        folder = TABLE_FOLDERS[c["table"]]
        e = {"command": c["name"]}
        tmeta[c["table"]].append(e)
        if "same_as" in c:
            e["same_as"] = c["same_as"]; continue     # the table points to the same sound data
        if c.get("silent"):
            e["silent"] = True; continue
        ev = c["events"]
        e["samples"] = [x[0] for x in ev]
        for x in ev:
            played[x[0]].add(c["name"])
        parts = c["parts"]
        if c["table"] == 6:
            ref = [line_ref[tuple(x[0] for x in p)] for p in parts]
            if any(ticks(p) != ticks(q) for p, q in zip(parts, ref)):
                e["pause_differs_from_file"] = True       # see starts_s for this command's own timing
            parts = ref
        built = [build_line(region, p) for p in parts]
        if all(built):
            e["files"] = []
            for p, (data, step) in zip(parts, built):
                # a dialogue line is shared by several commands: named after its samples
                name = "t6_line_" + "-".join("%03d" % x[0] for x in p) if c["table"] == 6 else c["name"]
                e["files"].append(out.emit(folder, name, data, step, p))
            e["sample_rate"] = [rate_of(b[1]) for b in built]
            e["starts_s"] = [round((x[2] - ev[0][2]) / 44100, 3) for x in ev]   # when each sample starts
            continue
        # pieces at different rates or mixed on several channels: logged as VGM (none in this game)
        d = os.path.join(outdir, folder)
        os.makedirs(d, exist_ok=True)
        raw = os.path.join(work, "s.vgm")
        run_emu(exe, rpath, c["table"], c["code"], raw, 30, 0.2, center=True)
        finish_vgm(raw, os.path.join(d, c["name"] + ".vgz"), "Sound %d-%03d" % (c["table"], c["code"]))
        e["files"] = ["%s/%s.vgz" % (folder, c["name"])]
        for s in e["samples"]:
            out.contained[s].add(e["files"][0])
        n_vgm += 1
    return tmeta, n_vgm


def write_samples(outdir, samples, unused, played, out, log):
    """Every PCM sample: its role, where its audio is; instruments, voice samples, unused data."""
    inst, mvoice, unused_items, smeta = [], [], [], []
    for s in samples:
        i = s["index"]
        users = sorted(played.get(i, []))
        mus = any(u.startswith("t1_") for u in users)
        cmd = any(not u.startswith("t1_") for u in users)
        alone = out.written.get(((i,), s["fd_step"], (0,)))
        m = {k: v for k, v in s.items() if k != "data"}
        m["played_by"] = users
        if not users:
            m["role"] = "never played"
            m["file"] = "unused/%s.raw" % s["name"]
            unused_items.append((s["name"], s["data"], s["sample_rate"]))
        elif mus and not cmd:
            m["role"] = "instrument"
            m["file"] = "table1-instruments/%s.raw" % s["name"]
            inst.append((s["name"], s["data"], s["sample_rate"]))
        else:
            m["role"] = "sfx" if any(u.startswith("t2_") for u in users) else "voice"
            if alone:
                m["file"] = alone                     # some command plays exactly this sample
            elif mus:
                # the music plays it on its own (credits, track 27), no command does
                m["file"] = "table1-voice-samples/%s.raw" % s["name"]
                mvoice.append((s["name"], s["data"], s["sample_rate"]))
        if out.contained.get(i):
            m["heard_in"] = sorted(out.contained[i])
        smeta.append(m)
    for u in unused:
        m = {k: v for k, v in u.items() if k != "data"}
        m["role"] = "unreferenced data"
        m["file"] = "unused/%s.raw" % u["name"]
        unused_items.append((u["name"], u["data"], u["sample_rate"]))
        smeta.append(m)
    write_raw_folder(outdir, "table1-instruments", inst,
                     "instrument samples (only the music, table 1, plays them), as stored in the sound ROMs")
    write_raw_folder(outdir, "table1-voice-samples", mvoice,
                     "voice samples the music (track 27, credits) plays on their own, as stored in the sound ROMs")
    if mvoice:
        with open(os.path.join(outdir, "table1-voice-samples", "README.txt"), "w", newline="\n") as f:
            f.write("# Voice samples that music command t1_026 (Track 27, the credits) plays on their own over the music.\n"
                    "# No sound command plays them alone: elsewhere they are only pieces of longer lines (listed below).\n"
                    "# The numbers are the samples' numbers in the sound driver's sample table (0x7E51 in epr-16541).\n\n")
            for m in smeta:
                if m.get("file", "").startswith("table1-voice-samples/"):
                    f.write("%s.raw  also heard in: %s\n" % (m["name"], ", ".join(x.split("/")[-1] for x in m.get("heard_in", []))))
    write_raw_folder(outdir, "unused", unused_items,
                     "PCM data nothing plays (in the sample table but never started, or pointed to by no table), "
                     "as stored in the sound ROMs")
    # the samples the table 6 lines are made of, each on its own, so the numbers in the line names point to files
    t6s = sorted({int(x) for n, _, _ in out.items["table6-dialogues"] for x in n[len("t6_line_"):].split("-")})
    write_raw_folder(outdir, "table6-voice-samples", [(samples[i]["name"], samples[i]["data"], samples[i]["sample_rate"])
                                                      for i in t6s],
                     "the voice samples the table 6 lines (../table6-dialogues) are made of, as stored in the sound ROMs")
    for m in smeta:
        if m.get("index") in t6s:
            m["sample_file"] = "table6-voice-samples/%s.raw" % m["name"]
    write_json(os.path.join(outdir, "samples.json"), smeta)
    log("table6-voice-samples: %d samples the dialogue lines are made of" % len(t6s))
    log("table1-instruments: %d samples, table1-voice-samples: %d samples, unused: %d"
        % (len(inst), len(mvoice), len(unused_items)))


def export_sounds(exe, rpath, region, work, outdir, log, prog):
    """Output follows the sound driver's tables: one file per command of tables 2 and 4, one per line
    of table 6, samples only the music (table 1) plays, and data nothing plays. Identical audio is
    written once; the JSON of each table says which file every command uses."""
    samples, unused = pcm_samples(region)
    cmds = run_commands(exe, rpath, region, work)
    line_ref = split_lines(region, cmds)
    out, played = Output(), defaultdict(set)      # played: sample -> commands / tracks that start it
    tmeta, n_vgm = write_commands(exe, rpath, region, work, outdir, cmds, line_ref, out, played)
    for table, folder in TABLE_FOLDERS.items():
        write_raw_folder(outdir, folder, out.items[folder], TABLE_WHAT[table])
        os.makedirs(os.path.join(outdir, folder), exist_ok=True)
        write_json(os.path.join(outdir, folder, "table%d.json" % table), tmeta[table])
        if table == 6:
            write_table6_info(outdir, folder, tmeta[6], [n for n, _, _ in out.items[folder]], prog)
        log("%s: %d commands, %d files" % (folder, len(tmeta[table]), len(out.items[folder])))
    if n_vgm:
        log("%d commands logged as VGM (pieces that had to be mixed)" % n_vgm)
    for code in range(MUSIC_COUNT):                # samples the music starts
        _, st = run_emu(exe, rpath, 1, code, os.path.join(work, "x.wav"), 400, 0.5, logsamples=True)
        for x in st:
            played[x[0]].add("t1_%03d" % code)
    write_samples(outdir, samples, unused, played, out, log)
