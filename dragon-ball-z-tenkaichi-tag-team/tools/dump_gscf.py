#!/usr/bin/env python3
"""
dump_gscf.py - Print the native calls of GSCF event scripts in readable form.

Usage: python3 tools/dump_gscf.py packfile_out/gscf/13404.gscf [more files...]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tttpack import gscf  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    for path in sys.argv[1:]:
        data = open(path, "rb").read()
        pool, programs = gscf.parse(data)
        chapter, speakers = gscf.battle_info(data)
        print("== %s  chapter %s  %d lines with a speaker slot" % (path, chapter, len(speakers)))
        for ident, code in programs:
            print("  program %d" % ident)
            for native, args, groups in gscf.native_calls(code, pool):
                tags = " ".join("%s%s" % (t, v) for t, vs in groups.items() for v in vs)
                print("    native %-5d %s %s" % (native, args, tags))


if __name__ == "__main__":
    main()
