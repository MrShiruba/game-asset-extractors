"""Command line interface: ``python -m brsar_sfx``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .disasm import disassemble
from .extract import Options, dump_raw, extract, select_sounds
from .formats import Rseq
from .rsar import SOUND_TYPE_SEQ, Rsar


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brsar-sfx",
        description="Extract the sound effects of a Wii NW4R sound archive (.brsar) by playing "
                    "its sequences with a re-implementation of the NW4R sound engine.",
    )
    p.add_argument("brsar", help="input .brsar file")
    p.add_argument("-o", "--output", default="sfx_out", help="output directory (default: sfx_out)")
    p.add_argument("-c", "--codec", default="pcm16", choices=["pcm16", "adpcm"],
                   help="audio codec inside the .brstm files: pcm16 = 16-bit PCM, lossless (default); "
                        "adpcm = Nintendo DSP-ADPCM, 4 bits/sample, ~3.5x smaller but lossy")
    sel = p.add_argument_group("sound selection")
    sel.add_argument("--include", metavar="REGEX", help="only sounds whose name matches REGEX")
    sel.add_argument("--exclude", metavar="REGEX", help="skip sounds whose name matches REGEX")
    ren = p.add_argument_group("rendering")
    ren.add_argument("--loops", type=int, default=2,
                     help="stop looping sequences after this many passes (default: 2, 0 = never)")
    ren.add_argument("--loop-min-seconds", type=float, default=5.0,
                     help="but keep looping sounds at least this long (default: 5)")
    ren.add_argument("--max-seconds", type=float, default=20.0,
                     help="how long to keep a sound that holds a note forever (e.g. an ambience), "
                          "after which it is faded out (default: 20)")
    ren.add_argument("--fade-seconds", type=float, default=2.0,
                     help="fade-out applied when the hard limit is hit (default: 2)")
    ren.add_argument("--no-normalize", action="store_true",
                     help="clip instead of lowering the volume of sounds that would exceed 0 dBFS")
    ren.add_argument("--stereo", action="store_true",
                     help="always write stereo (by default identical L/R channels are written as mono)")
    ren.add_argument("--seed", type=lambda v: int(v, 0), default=0x12345678,
                     help="seed of the engine's random generator (sequences with random parameters)")
    out = p.add_argument_group("output layout")
    out.add_argument("--flat", action="store_true", help="no category sub-folders")
    out.add_argument("-j", "--jobs", type=int, default=0, help="worker processes (default: CPU count, max 8)")
    tools = p.add_argument_group("inspection tools (no audio is rendered)")
    tools.add_argument("--list", action="store_true", help="list the sounds of the archive")
    tools.add_argument("--disasm", metavar="SOUND", help="print the sequence code of a sound")
    tools.add_argument("--dump-raw", metavar="DIR",
                       help="write every sub-file in its native format (RSEQ/RBNK/RWSD/RWAR) + index.json")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    with open(args.brsar, "rb") as f:
        rsar = Rsar(f.read())

    if args.list:
        for s in rsar.sounds:
            extra = ""
            if s.sound_type == SOUND_TYPE_SEQ and s.bank_id < len(rsar.banks):
                extra = rsar.banks[s.bank_id].name
            player = rsar.players[s.player_id] if s.player_id < len(rsar.players) else ""
            print(f"{s.index:4d}  {s.type_name:4s}  vol {s.volume:3d}  {player:16s} {extra:16s} {s.name}")
        return 0

    if args.disasm:
        match = [s for s in rsar.sounds if s.name.lower() == args.disasm.lower()]
        if not match:
            print(f"no sound named {args.disasm}", file=sys.stderr)
            return 1
        s = match[0]
        if s.sound_type != SOUND_TYPE_SEQ:
            print(f"{s.name} is a {s.type_name} sound, not a sequence", file=sys.stderr)
            return 1
        data, _ = rsar.get_file(s.file_id)
        bank = rsar.banks[s.bank_id].name if s.bank_id < len(rsar.banks) else s.bank_id
        print(f"; {s.name}  bank={bank}  volume={s.volume}  start=0x{s.seq_offset:X}")
        print("\n".join(disassemble(Rseq(data).seq, s.seq_offset)))
        return 0

    if args.dump_raw:
        dump_raw(rsar, args.dump_raw)
        return 0

    sounds = select_sounds(rsar, args.include, args.exclude)
    if not sounds:
        print("no sound selected", file=sys.stderr)
        return 1
    opts = Options(codec=args.codec, loops=args.loops, loop_min_seconds=args.loop_min_seconds,
                   max_seconds=args.max_seconds, fade_seconds=args.fade_seconds,
                   normalize=not args.no_normalize, force_stereo=args.stereo, flat=args.flat,
                   seed=args.seed, jobs=args.jobs)
    results = extract(args.brsar, args.output, sounds, rsar, opts)
    return 0 if all(r.error is None for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
