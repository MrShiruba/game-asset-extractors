#!/usr/bin/env python3
"""
mslondon2012extract.py - All-in-one extractor for "Mario & Sonic at the
London 2012 Olympic Games" (Nintendo 3DS), file fs_data.cpk.

Usage:
    python mslondon2012extract.py fs_data.cpk [-o OUTPUT_DIR] [options]

What it does, in a single command:
  1. Extracts fs_data.cpk (ITOC or TOC table) and decompresses CRILAYLA data.
  2. Recursively extracts every nested CPK (each NNNN.cpk becomes a folder
     NNNN/ holding its contents).
  3. Detects file types from their contents (bcres, bcfnt, acb, acf, adx...).
     Each .swif (Sega wrapper) is kept, and the standard .bcres it contains
     is written next to it, bytes unchanged, so 3DS tools can open it.
     Each text file (UTF-16 message table) is kept, and a readable UTF-8
     .txt copy is written next to it.
  4. Sound banks. ACB files (CRI ADX2, early 3DS version 0.81) hold the cue
     names; their waveforms are stored once, in an AWB that is itself a
     CPK: inside the ACB (BCWAV) or in a following CPK (streamed ADX, e.g.
     1427.acb + 1428.cpk; the pairs are matched by sample rate, channels
     and length). Sorted mode writes each bank as <name>.acb (+ <name>.awb,
     the game's CPK renamed): open the .awb (or a memory .acb) with
     vgmstream to play every cue under its real name. The report lists
     every cue and its waveforms.
  5. Sorted mode (default): moves everything into categories with readable
     names (names.csv for sound banks, internal names for .bcres files).
     Nothing is dropped; index.csv maps each file back to its raw path.
  6. Writes a report (report.txt): file types, sound list, problems.

Output, sorted mode (default):
    <output>/sound/              1427_bgm_swim_back.acb + .awb, the .acf...
                                 (open the .awb / memory .acb with vgmstream)
    <output>/models/  textures/  animations/  scenes/  fonts/  text/  data/
    <output>/collision/  other/
    <output>/index.csv           sorted path -> raw path
Output, raw mode (--mode raw):
    <output>/files/    full extracted tree, numbered as in fs_data.cpk

Options:
    --mode MODE    sorted (default) or raw
    --names FILE   names list to use instead of mslondon2012/names.csv
    -o DIR         output folder (default: <cpk name>_extracted)
    -j N           number of worker processes (default: all CPU cores)
    --keep-cpk     also keep the raw nested .cpk files
    --no-sound     skip the sound bank step (ACB/AWB pairing, cue list)
    --no-unwrap    do not write the extra files (.bcres inside each .swif,
                   .txt copy of each text file)

No dependencies: standard Python 3.8+ only. The code lives in the
mslondon2012/ folder, which must stay next to this script.
"""
import argparse
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from mslondon2012.cpk import list_cpk
from mslondon2012.extract import job_extract
from mslondon2012.filetypes import safe
from mslondon2012.names import DEFAULT as DEFAULT_NAMES, load_names
from mslondon2012.sort import Sorter
from mslondon2012.sound import job_acb


def main():
    ap = argparse.ArgumentParser(
        description="All-in-one fs_data.cpk extractor for Mario & Sonic at the "
                    "London 2012 Olympic Games (3DS).")
    ap.add_argument("cpk", help="path to fs_data.cpk")
    ap.add_argument("--mode", choices=("sorted", "raw"), default="sorted",
                    help="sorted: categories and readable names (default); "
                         "raw: numbered tree as stored in fs_data.cpk")
    ap.add_argument("--names", default=DEFAULT_NAMES, help="names list (CSV)")
    ap.add_argument("-o", "--output", help="output folder (default: <cpk name>_extracted)")
    ap.add_argument("-j", "--jobs", type=int, default=None, help="worker processes")
    ap.add_argument("--keep-cpk", action="store_true", help="also keep raw nested .cpk files")
    ap.add_argument("--no-sound", action="store_true", help="skip the sound bank step (ACB/AWB pairing, cue list)")
    ap.add_argument("--no-unwrap", action="store_true",
                    help="do not write the extra files (.bcres inside .swif, .txt of texts)")
    a = ap.parse_args()

    t0 = time.time()
    out = a.output or os.path.splitext(os.path.basename(a.cpk))[0] + "_extracted"
    raw_root = os.path.join(out, "files")
    sorted_mode = a.mode == "sorted"
    if sorted_mode and os.path.isdir(out) and os.listdir(out):
        sys.exit("Output folder %s is not empty, remove it first (or use -o)." % out)
    os.makedirs(raw_root, exist_ok=True)
    problems = []
    stream_folders = {}
    acb_names = {}

    # --- 1. extraction
    with open(a.cpk, "rb") as f:
        if f.read(4) != b"CPK ":
            sys.exit("Not a CPK file.")

        def rd(off, size):
            f.seek(off)
            return f.read(size)
        entries = list_cpk(rd)

    jobs = []
    for name, _, off, size, ext_size in entries:
        dest = os.path.join(raw_root, *[safe(x) for x in name.split("/")])
        if "." in os.path.basename(name):
            dest = os.path.splitext(dest)[0]
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        keep = True if a.keep_cpk else ("awb" if sorted_mode else False)
        jobs.append((a.cpk, dest, off, size, ext_size, keep, not a.no_unwrap))
    print("[1/4] %d files in %s (%d compressed), extracting..."
          % (len(jobs), a.cpk, sum(1 for j in jobs if j[3] != j[4])))
    total = 0
    with ProcessPoolExecutor(a.jobs) as pool:
        for k, (n, probs) in enumerate(pool.map(job_extract, jobs, chunksize=4), 1):
            total += n
            problems += [p.replace(raw_root + os.sep, "") for p in probs]
            if k % 200 == 0 or k == len(jobs):
                print("      %d / %d" % (k, len(jobs)))
    print("      -> %d files written" % total)

    counts = Counter()
    all_files = []
    for dp, _, fns in os.walk(raw_root):
        for fn in fns:
            all_files.append(os.path.join(dp, fn))
            counts[os.path.splitext(fn)[1].lower()] += 1

    # --- 2. sound banks
    n_snd = 0
    index = []
    if not a.no_sound:
        acbs = sorted(p for p in all_files if p.lower().endswith(".acb"))
        print("[2/4] %d ACB, reading cues..." % len(acbs))
        claims = {}
        with ProcessPoolExecutor(a.jobs) as pool:
            jobs = [(p, raw_root) for p in acbs]
            for k, (n, idx, probs, folder, wnames) in enumerate(pool.map(job_acb, jobs), 1):
                acb_rel = os.path.relpath(jobs[k - 1][0], raw_root)
                m = re.match(r"^(\d+)\.acb$", acb_rel)
                if m:
                    acb_names[int(m.group(1))] = wnames
                if folder:
                    claims.setdefault(folder, []).append(acb_rel)
                    stream_folders[acb_rel] = os.path.relpath(folder, raw_root)
                n_snd += n
                index += idx
                problems += probs
                if k % 25 == 0 or k == len(acbs):
                    print("      %d / %d" % (k, len(acbs)))
        for folder, owners in sorted(claims.items()):
            if len(owners) > 1:
                problems.append("%s claimed by several ACB: %s (names may be wrong)"
                                % (os.path.relpath(folder, raw_root), ", ".join(owners)))
        print("      -> %d cues listed" % n_snd)

    # --- 3. sorting
    if sorted_mode:
        print("[3/4] sorting into categories...")
        sorter = Sorter(out, raw_root, load_names(a.names))
        n = sorter.run(stream_folders, acb_names)
        problems += sorter.problems
        cats = Counter()
        for dp, _, fns in os.walk(out):
            top = os.path.relpath(dp, out).split(os.sep)[0]
            if top != ".":
                cats[top] += len(fns)
        print("      -> %d files sorted (%s), see index.csv"
              % (n, ", ".join("%s %d" % kv for kv in sorted(cats.items()))))

    # --- 4. report
    print("[4/4] report")
    report = os.path.join(out, "report.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("Extraction of %s\n\nFile types:\n" % a.cpk)
        for ext, n in counts.most_common():
            f.write("  %-24s %d\n" % (ext or "(none)", n))
        f.write("\n%d cues listed\n\nSounds (cue -> waveform):\n" % n_snd)
        for line in index:
            f.write("  " + line + "\n")
        f.write("\nProblems (%d):\n" % len(problems))
        for p in problems:
            f.write("  " + p + "\n")

    print("\nFile types:")
    for ext, n in counts.most_common():
        print("  %-24s %d" % (ext or "(none)", n))
    if problems:
        print("\n%d problem(s), see %s" % (len(problems), report))
        for p in problems[:15]:
            print("  " + p)
    print("\nDone in %.0f s -> %s" % (time.time() - t0, out))


if __name__ == "__main__":
    main()
