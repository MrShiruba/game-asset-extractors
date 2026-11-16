#!/usr/bin/env python3
"""
Extract PACKFILE.BIN of Dragon Ball Z Tenkaichi Tag Team / Dragon Ball Tag VS (PSP: ULJS00311, ULUS10537, ULES01456).

Usage: python3 ttt_unpack.py PACKFILE.BIN [output_folder] [--txt] [--png] [--no-unpack]
See tttpack/ for the format notes and python3 ttt_unpack.py --help for all options.
"""
from tttpack.extract import run

if __name__ == "__main__":
    run()
