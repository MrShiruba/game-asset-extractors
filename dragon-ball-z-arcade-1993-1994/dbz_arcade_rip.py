#!/usr/bin/env python3
"""Dragon Ball Z arcade ripper (Banpresto / Konami hardware):
Dragon Ball Z (1993, MAME dbz / dbza) and Dragon Ball Z 2 Super Battle (1994, MAME dbz2).
The game is detected from the ROM files.

Usage:
    python dbz_arcade_rip.py dbz.zip                 # everything -> ./dbz_rip
    python dbz_arcade_rip.py dbz2.zip                # everything -> ./dbz2_rip
    python dbz_arcade_rip.py dbz.zip samples sprites # pick what you want
    python dbz_arcade_rip.py roms/dbz/ -o out music

Targets: samples (voices + sound effects), music, sprites, stages, screens, rawsprites, tiles, palettes, all
"""
import argparse
import sys
import time

from dbz_arcade_rip.romset import RomError, RomSet

TARGETS = ["samples", "music", "sprites", "stages", "screens", "rawsprites", "tiles", "palettes"]
ALIASES = {"hud": "screens", "voices": "samples", "sfx": "samples", "sounds": "music", "sprite": "sprites"}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract voices, sound effects, music and graphics from the Dragon Ball Z "
                    "arcade romsets: Dragon Ball Z (MAME 'dbz', 'dbza') and Dragon Ball Z 2 "
                    "Super Battle (MAME 'dbz2'). The game is detected automatically.")
    ap.add_argument("rom", help="dbz.zip / dbz2.zip or a folder containing the ROM files")
    ap.add_argument("targets", nargs="*", default=["all"],
                    help="what to extract: " + ", ".join(TARGETS + ["all"]) + " (default: all)")
    ap.add_argument("-o", "--out", default=None, help="output folder (default: dbz_rip or dbz2_rip)")
    ap.add_argument("--strict", action="store_true", help="refuse ROMs with a bad CRC")
    g = ap.add_argument_group("samples (OKI M6295: voices and sound effects)")
    g.add_argument("--keep-blank", action="store_true", help="also write the tiny silent slots")
    g = ap.add_argument_group("music (Z80 + YM2151 + OKI emulation)")
    g.add_argument("--music-seconds", type=float, default=300.0,
                   help="max time to search for a track's loop point (default 300 s)")
    g.add_argument("--commands", default=None,
                   help="sound command numbers to record (default 0x01-0x10), e.g. '0x01-0x05,0x12'")
    g.add_argument("--seconds", type=float, default=6.0,
                   help="max length for non-music commands given with --commands (default 6)")
    g = ap.add_argument_group("sprites")
    g.add_argument("--no-frames", action="store_true", help="only sheets, no individual frame PNGs")
    g.add_argument("--no-p2", action="store_true", help="skip player-2 colour sheets (dbz)")
    args = ap.parse_args(argv)

    targets = {ALIASES.get(t.lower(), t.lower()) for t in args.targets}
    if "all" in targets:
        targets = set(TARGETS)
    bad = targets - set(TARGETS)
    if bad:
        ap.error("unknown target(s): " + ", ".join(sorted(bad)))

    try:
        rs = RomSet(args.rom, strict=args.strict)
    except RomError as e:
        print("error:", e, file=sys.stderr)
        return 1
    for w in rs.warnings:
        print("warning:", w, file=sys.stderr)
    if args.out is None:
        args.out = f"{rs.game}_rip"
    print(f"{rs.title} - romset: {rs.set_name or 'unknown (68000 program ROMs missing)'} -> {args.out}")

    from dbz_arcade_rip import extract
    t0 = time.time()
    blocks = None
    try:
        if "samples" in targets:
            print("[samples] OKI M6295 ADPCM: voices + sound effects")
            extract.extract_voices(rs, args.out, keep_blank=args.keep_blank)
        if targets & {"sprites", "rawsprites"}:
            blocks = extract._blocks(rs)
        if "sprites" in targets:
            print("[sprites] rebuilding fighter frames")
            extract.extract_characters(rs, args.out, blocks, frames=not args.no_frames,
                                       p2=not args.no_p2)
            print("[sprites] effects, projectiles, texts, portraits, credits")
            extract.extract_objects(rs, args.out, blocks)
        if "stages" in targets:
            print("[stages] background layers")
            if blocks is None:
                blocks = extract._blocks(rs)
            extract.extract_stages(rs, args.out, blocks)
        if "screens" in targets:
            print("[screens] HUD, title, select, endings, test mode")
            extract.extract_screens(rs, args.out)
        if "rawsprites" in targets:
            print("[rawsprites] raw sprite ROM sheets")
            extract.extract_sprite_blocks(rs, args.out, blocks)
        if "tiles" in targets:
            print("[tiles] background/foreground tiles")
            extract.extract_tiles(rs, args.out)
        if "palettes" in targets:
            print("[palettes]")
            extract.extract_palettes(rs, args.out)
        if "music" in targets:
            print("[music] emulating the Z80 sound program (a few minutes)")
            from dbz_arcade_rip import sound
            sound.extract_sounds(rs, args.out, seconds=args.seconds,
                                 music_seconds=args.music_seconds,
                                 commands=args.commands)
    except RomError as e:
        print("error:", e, file=sys.stderr)
        return 1
    print(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
