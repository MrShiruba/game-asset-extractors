#!/usr/bin/env python3
"""
PETA (.ptd) extractor - Sora no Otoshimono DokiDoki Summer Vacation (PSP, ULJM05639)

Extracts every file with its original name and path, in its original format.
Nested .ptd archives are kept as-is AND their contents are extracted too.

Game-specific formats are also unpacked next to the original file
(the original is kept):

  .fab / .fsb -> <name>_tex/*.gim   embedded GIM textures
  .vgp        -> <name>_vag/*.vag   sound bank split into standard VAG files
  .tfp        -> .png + .txt        font glyph atlas + character map
  .sos        -> .txt               script string table (UTF-8)

Format details are documented in the ptdlib/ modules and in README.md.
"""
import argparse
import io
import os
import sys

from ptdlib import peta, yklz
from ptdlib.convert import convert
from ptdlib.util import write_file


def safe_join(root, path):
    """Join an archive path to the output folder, never escaping it."""
    parts = [p for p in path.replace('\\', '/').split('/') if p not in ('', '.', '..')]
    return os.path.join(root, *parts)


def read_entry(f, off, size, comp, path, head_only=False):
    """Read one file, undoing YKLZ. With head_only, uncompressed files are
    only read far enough to check for a nested archive."""
    f.seek(off)
    if head_only and not comp:
        return f.read(4)
    data = f.read(size)
    if comp:
        try:
            data = yklz.decompress(data)
        except Exception as e:
            print('  ! %s: decompression failed (%s), raw data kept' % (path, e), file=sys.stderr)
    return data


def nested(f, off, data, comp):
    """Return (file, base) to read a nested PETA archive from."""
    if comp:                       # decompressed copy lives in memory
        return io.BytesIO(data), 0
    return f, off                  # stored as-is: read in place


def extract(f, base, args, depth=0, label=''):
    n = 0
    count = 0
    for path, off, size, comp in peta.entries(f, base, lower=not args.keep_case):
        count += 1
        data = read_entry(f, off, size, comp, path, head_only=args.list)
        if args.list:
            print('%s%-60s off=0x%08X size=%-9d %s' % ('  ' * depth, path, off, size, 'LZ' if comp else ''))
            n += 1
            if data[:4] == peta.MAGIC:
                n += extract(*nested(f, off, data, comp), args, depth + 1, path)
            continue
        dst = safe_join(args.out, path)
        write_file(dst, data)
        n += 1
        if data[:4] == peta.MAGIC:
            n += extract(*nested(f, off, data, comp), args, depth + 1, path)
        else:
            n += convert(dst, data, not args.keep_case)
    if not args.list:
        print('%s%s: %d files' % ('  ' * depth, label or getattr(f, 'name', '?'), count))
    return n


def main():
    ap = argparse.ArgumentParser(description='PETA (.ptd) extractor for Sora no Otoshimono (PSP)')
    ap.add_argument('ptd', nargs='+', help='archive(s) to extract, e.g. path/to/res.ptd')
    ap.add_argument('-o', '--out', default='out', help='output directory (default: out)')
    ap.add_argument('-l', '--list', action='store_true', help='list contents without extracting')
    ap.add_argument('--keep-case', action='store_true', help='keep UPPERCASE names as stored in the archive')
    args = ap.parse_args()

    total = 0
    for p in args.ptd:
        with open(p, 'rb') as f:
            total += extract(f, 0, args, label=p)
    if not args.list:
        print('Done: %d files written to %s/' % (total, args.out))


if __name__ == '__main__':
    main()
