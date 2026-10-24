#!/usr/bin/env python3
"""Audio extraction for Dragon Ball Z: Shinbutouden (Sega Saturn).

Takes game files and/or folders (walked recursively), with the output folder
last:
  - TON banks (*_V.BIN, *V.BIN, WV_*.BIN, HAI_*V.BIN) -> one .raw per sample
  - compressed .PCM voices (KOJIN/, YBT/, END/, BOOG_1.PCM) -> decompressed .raw
Each output folder gets a .txth (+ .names.txt when needed) for vgmstream.
Files that are neither are skipped.

Examples:
  python3 dbzsb.py iso/ sounds/
  python3 dbzsb.py iso/GK_V.BIN iso/KOJIN sounds/
"""
import argparse
import sys

from dbz_shinbutouden import audio


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help="game files and/or folders")
    ap.add_argument('out', help="output folder")
    a = ap.parse_args()
    audio.extract_all(a.inputs, a.out)


if __name__ == '__main__':
    sys.exit(main())
