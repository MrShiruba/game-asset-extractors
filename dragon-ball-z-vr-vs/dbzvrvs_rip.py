#!/usr/bin/env python3
"""
dbzvrvs_rip.py - rip Dragon Ball Z: V.R.V.S. (Sega System 32, 1994) from the MAME zip.

    python3 dbzvrvs_rip.py dbzvrvs.zip output_folder [sprites] [backgrounds] [music] [sounds]

Output (audio folders follow the tables of the game's sound driver: tableN-<content>):
  sprites/<group>/NNNN_<devname>.png   every sprite, RGBA, game palette applied
  sprites/_sheets/<group>.png          one sheet per group
  sprites/sprites.json                 index, name, size, bpp, colour bank
  sprites/<group>_alt/NNNN_<devname>.png   fighter sprites in the alternate (mirror-match) palette
  backgrounds/screen_SSSSS_pageNN.png  tile-layer screens (stage backgrounds, cut-scenes, ROUND,
                                       GAME OVER, speech bubbles), one image per video RAM page
  table1-music/t1_NNN.vgz              the 27 music commands, VGM 1.71 (2x YM3438 + RF5C68), looped
  table1-instruments/sample_NNN.raw    samples only the music plays (drum kit, instruments)
  table1-voice-samples/sample_NNN.raw         voice samples the music (credits) plays alone, no command does
  table2-sfx/t2_NNN.raw                sound effects, one file per command
  table4-voices/t4_NNN.raw             voice lines, one complete line per command
  table6-dialogues/t6_line_NNN-NNN.raw dialogue lines (fight intros, wins): a command chains two of them;
                                       named after the samples that make the line
  unused/                              PCM data nothing plays
  tableN-*/tableN.json                 every command of the table -> its file(s) and samples
  samples.json                         every PCM sample: ROM offset, rate, role, what plays it, files it is in
  .raw files: RF5C68 PCM bytes from the ROM, read by vgmstream through .raw.txth + .names.txt

Needs: Python 3.8+, numpy, Pillow. Music and sound commands also need a C compiler
(cc/gcc/clang) for the sound-board emulator s32snd.c, compiled automatically.
Without one, sprites, backgrounds and the PCM samples (unsorted) are still extracted.
"""
import os, sys, shutil, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbzvrvs import sprites, tilemaps, audit  # noqa: E402
from dbzvrvs.romset import load_zip, sound_region, program  # noqa: E402
from dbzvrvs.soundboard import build_emulator  # noqa: E402
from dbzvrvs.pcm import pcm_table, export_samples_unsorted  # noqa: E402
from dbzvrvs.sounds import export_music, export_sounds  # noqa: E402


def log(*a):
    print(*a, flush=True)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    zpath, outdir = sys.argv[1], sys.argv[2]
    only = set(sys.argv[3:])  # optional: sprites backgrounds music sounds
    os.makedirs(outdir, exist_ok=True)
    files = load_zip(zpath)
    log("ROMs OK")

    if not only or "sprites" in only:
        sprites.export(files, outdir, log)
    if not only or "backgrounds" in only:
        tilemaps.export(files, outdir, log)

    region = sound_region(files)
    if not only or only & {"music", "sounds"}:
        work = tempfile.mkdtemp(prefix="dbzvrvs_")
        try:
            rpath = os.path.join(work, "sound.bin")
            open(rpath, "wb").write(region)
            exe = build_emulator(work)
            if exe is None:
                log("no C compiler found (gcc/clang): music and sound commands skipped, samples written\n"
                    "unsorted. Install one (Linux: build-essential, macOS: xcode-select --install,\n"
                    "Windows: MSYS2/MinGW or WSL) and run again.")
                export_samples_unsorted(region, outdir, log)
            else:
                if not only or "music" in only:
                    export_music(exe, rpath, work, outdir, log)
                if not only or "sounds" in only:
                    export_sounds(exe, rpath, region, work, outdir, log, program(files))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    audit.report(files, region, pcm_table(region), outdir, log)
    log("done ->", outdir)


if __name__ == "__main__":
    main()
