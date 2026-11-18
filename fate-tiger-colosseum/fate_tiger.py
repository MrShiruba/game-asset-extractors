#!/usr/bin/env python3
"""Fate/tiger colosseum (PSP, ULJM05266) extraction toolkit.

Commands:
  list     List the files inside a BND archive
  extract  Extract a BND archive (nested BNDs included by default)
  text     Dump dialogue from the .pac scripts to .txt / .csv
  disasm   Disassemble the .pac scripts to readable .asm listings
  all      extract + text + disasm in one go

Examples:
  python3 fate_tiger.py all PSP_GAME/USRDIR/BUILDED.BND
  python3 fate_tiger.py extract PSP_GAME/USRDIR/BUILDED.BND -o extracted
  python3 fate_tiger.py text extracted/prj/tiger/data/builded/script -o script_text
  python3 fate_tiger.py disasm extracted/prj/tiger/data/builded/script -o script_asm
"""
import argparse
import os
import sys

from tools import bnd, pac_disasm, pac_text

SCRIPT_DIR = os.path.join("prj", "tiger", "data", "builded", "script")


def cmd_list(a):
    bnd.list_files(a.bnd, recursive=not a.no_recursive)


def cmd_extract(a):
    n = bnd.extract(a.bnd, a.output, recursive=not a.no_recursive,
                    keep_nested=not a.drop_nested)
    print("%d files extracted to %s" % (n, a.output))


def cmd_text(a):
    results, voices = pac_text.dump(a.source, a.output)
    print("voiceidtable: %d voices" % voices)
    for name, count in results.items():
        print("  %-28s %5d lines" % (name, count))
    print("%d script(s) written to %s" % (len(results), a.output))


def cmd_disasm(a):
    done = pac_disasm.dump(a.source, a.output)
    for name, count in done.items():
        print("  %-28s %6d instructions" % (name, count))
    print("%d script(s) written to %s" % (len(done), a.output))


def cmd_all(a):
    cmd_extract(argparse.Namespace(bnd=a.bnd, output=a.output,
                                   no_recursive=False, drop_nested=a.drop_nested))
    script = os.path.join(a.output, SCRIPT_DIR)
    if os.path.isdir(script):
        cmd_text(argparse.Namespace(source=script, output=a.text_output))
        cmd_disasm(argparse.Namespace(source=script, output=a.asm_output))
    else:
        print("script folder not found: %s" % script, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list the files inside a BND archive")
    p.add_argument("bnd")
    p.add_argument("--no-recursive", action="store_true", help="do not descend into nested BNDs")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("extract", help="extract a BND archive")
    p.add_argument("bnd")
    p.add_argument("-o", "--output", default="extracted")
    p.add_argument("--no-recursive", action="store_true", help="do not extract nested BNDs")
    p.add_argument("--drop-nested", action="store_true",
                   help="do not keep the nested .bnd files themselves, only their contents")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("text", help="dump dialogue from .pac scripts")
    p.add_argument("source", help="a .pac file or the script/ folder")
    p.add_argument("-o", "--output", default="script_text")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("disasm", help="disassemble .pac scripts")
    p.add_argument("source", help="a .pac file or the script/ folder")
    p.add_argument("-o", "--output", default="script_asm")
    p.set_defaults(func=cmd_disasm)

    p = sub.add_parser("all", help="extract everything, then dump the dialogue")
    p.add_argument("bnd")
    p.add_argument("-o", "--output", default="extracted")
    p.add_argument("--text-output", default="script_text")
    p.add_argument("--asm-output", default="script_asm")
    p.add_argument("--drop-nested", action="store_true")
    p.set_defaults(func=cmd_all)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
