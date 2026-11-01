"""Table 6 dialogues: when the fight code sends each command, who says each line, and the README of
the table6-dialogues folder."""
import os, re, struct
from collections import defaultdict
from .pcm import write_json


# When the game sends the table 6 commands (V60 program, sound queue at 0xB6A74, value 0x86nn):
#   0x82A43: fight intro, code from the table at 0x830ED indexed by 6 * (player 1 character) + opponent
#   0x99436: after the match, code from 0x99535 (player 1 won) or 0x9957D (player 2 won), same index
#            (winner decided at 0x98C5E)
FIGHTER_NAMES = ("Goku", "Gohan", "Trunks", "Vegeta", "Piccolo", "Ozotto")
DIALOGUE_TABLES = ((0x830ED, "intro"), (0x99535, "p1 wins"), (0x9957D, "p2 wins"))


def dialogue_situations(prog):
    """{table 6 code: [situations]} from the tables the fight code reads."""
    out = defaultdict(list)
    for addr, kind in DIALOGUE_TABLES:
        for k in range(36):
            code = struct.unpack_from("<H", prog, addr + 2 * k)[0] & 0xFF
            a, b = FIGHTER_NAMES[k // 6], FIGHTER_NAMES[k % 6]
            if a == b == "Ozotto":                  # boss: never on both sides
                continue
            text = {"intro": "intro, %s (1P) vs %s (2P)" % (a, b), "p1 wins": "%s beats %s" % (a, b),
                    "p2 wins": "%s beats %s" % (b, a)}[kind]
            if text not in out[code]:
                out[code].append(text)
    return out


def line_speakers(tmeta6):
    """Who says each table 6 line. Order of the two lines in a command: intro = 1P's character first, except
    against Ozotto, who always speaks first (seen in the game); end of match = winner first, except when Ozotto
    wins (loser first). Checked: every line gets the same speaker in all the commands that play it."""
    by = {e["command"]: e for e in tmeta6}
    sp, clash = {}, False
    for e in tmeta6:
        files = (by[e["same_as"]] if "same_as" in e else e).get("files", [])
        for s in e.get("situation", []):
            m = re.match(r"intro, (\w+) \(1P\) vs (\w+) \(2P\)", s)
            if m:
                a, b = m.groups()
                order = ["Ozotto", a if b == "Ozotto" else b] if "Ozotto" in (a, b) else [a, b]
            else:
                m = re.match(r"(\w+) beats (\w+)", s)
                if not m:
                    continue
                w, l = m.groups()
                order = [l, w] if w == "Ozotto" else [w, l]
            if len(files) == 1:
                order = ["Ozotto"] if "Ozotto" in order else order[:1]
            for f, p in zip(files, order):
                clash |= sp.setdefault(f, p) != p
    return {} if clash else sp


def write_table6_info(outdir, folder, tmeta6, line_names, prog):
    """Adds when each command is sent ("situation") and who says its lines ("speakers") to table6.json,
    and writes README.txt in the folder: what the line names mean, every line (who says it, when it is
    played) and every command."""
    sit = dialogue_situations(prog)
    for e in tmeta6:
        e["situation"] = sit.get(int(e["command"][3:]), ["not sent by the fight code"])
    # plain-text index: a line's name is the game's numbers of the samples it is made of
    users = defaultdict(list)
    for e in tmeta6:
        for f in e.get("files", []):
            users[f].append(e["command"])
    with open(os.path.join(outdir, folder, "README.txt"), "w", newline="\n") as f:
        f.write("# Each file is one character's line, as the game builds it: the game stores no line, only voice\n"
                "# samples, and plays them one after the other. A file name lists those samples by their number in\n"
                "# the sound driver's sample table (0x7E51 in epr-16541): t6_line_073-041 = sample 073 then sample\n"
                "# 041. Each sample is in ../table6-voice-samples/sample_NNN.raw (ROM offsets in ../samples.json).\n"
                "# After the name: who says it. Under it: when the game plays it (fight intro of 1P vs 2P, or end\n"
                "# of the match). A table 6 command chains two lines (MIDI channels 10 and 11): at the intro the\n"
                "# 1P character speaks first (Ozotto always first), at the end the winner (the loser when Ozotto wins).\n\n")
        byname = {e["command"]: e for e in tmeta6}
        who = line_speakers(tmeta6)
        for e in tmeta6:
            if e.get("files") and all(x in who for x in e["files"]):
                e["speakers"] = [who[x] for x in e["files"]]
        write_json(os.path.join(outdir, folder, "table6.json"), tmeta6)
        for name in line_names:
            path = "%s/%s.raw" % (folder, name)
            smp = name[len("t6_line_"):].replace("-", " ")
            cmds = sorted({c for c in users[path]} |
                          {e["command"] for e in tmeta6 if e.get("same_as") in users[path]})
            where = []
            for c in cmds:
                for x in byname[c]["situation"]:
                    if x not in where and not x.startswith("not sent"):
                        where.append(x)
            if path not in who and name.startswith("t6_line_070"):
                who[path] = "Ozotto"            # end of his line 068-069-070
            f.write("%s  (samples %s)  %s\n    %s\n" % (name + ".raw", smp, who.get(path, "?"),
                                                    "\n    ".join(where) or "never sent by the fight code"))
        f.write("\n# Commands of table 6 (t6_NNN = command NNN, the number the game sends to the sound board),\n"
                "# when the game sends them, and the lines they play in order:\n\n")
        for e in tmeta6:
            what = "same sequence as " + e["same_as"] if "same_as" in e else \
                "  then  ".join(x.split("/")[-1] for x in e.get("files", []))
            f.write("%-7s %-42s %s\n" % (e["command"], "; ".join(e["situation"]), what))
