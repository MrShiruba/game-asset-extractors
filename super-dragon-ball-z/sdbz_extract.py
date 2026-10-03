#!/usr/bin/env python3
"""
GAME.DAT / INFO.DAT Extractor - Super Dragon Ball Z (PS2, SLPS_256.42, Arika engine)

Format reverse-engineered from disassembling ARKD_DVD.IRX:
  INFO.DAT = table of 48-byte entries.
    - Entry 0: bytes 0x00-0x0F = key (plaintext, "`www.arika.co.jp")
               +0x2C = file count
    - Bytes 0x10..: obfuscated. For each byte:
          b = swap_nibbles(b); b = ~b; b = b - key[(pos-16) % 16]
    - Entry i (1..n): +0x00 name (ASCIIZ, e.g. "sqm/gameover.ams")
                      +0x24 sector (LBA, 2048 bytes) relative to start of GAME.DAT
                      +0x28 size in sectors (rounded)
                      +0x2C size in bytes

Usage:
  python3 sdbz_extract.py INFO.DAT GAME.DAT --list        # list files only
  python3 sdbz_extract.py INFO.DAT GAME.DAT -o out        # extract everything
"""
import argparse, os, struct, sys

SECTOR = 2048
ENTRY = 0x30


def decode_toc(raw):
    d = bytearray(raw)
    key = d[:16]
    if d[0] != 0:  # the driver only decodes if the first byte is non-zero
        for p in range(16, len(d)):
            b = d[p]
            b = ((b >> 4) | (b << 4)) & 0xFF
            b = (~b) & 0xFF
            d[p] = (b - key[(p - 16) & 15]) & 0xFF
    return d


def parse(toc):
    count = struct.unpack_from('<I', toc, 0x2C)[0]
    if count == 0 or (count + 1) * ENTRY > len(toc):
        sys.exit(f"Inconsistent entry count ({count}): corrupted INFO.DAT?")
    out = []
    for i in range(1, count + 1):
        e = toc[i * ENTRY:(i + 1) * ENTRY]
        name = e[:0x24].split(b'\0', 1)[0].decode('ascii', 'replace')
        lba, unk, size = struct.unpack_from('<3I', e, 0x24)
        out.append((name, lba, unk, size))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('info')
    ap.add_argument('game')
    ap.add_argument('-o', '--out', default='out', help='output directory (default: out)')
    ap.add_argument('--list', action='store_true', help='list archive contents without extracting')
    ap.add_argument('--dump-toc', help='write decoded INFO.DAT to this file')
    a = ap.parse_args()

    toc = decode_toc(open(a.info, 'rb').read())
    if a.dump_toc:
        open(a.dump_toc, 'wb').write(toc)
    entries = parse(toc)
    gsize = os.path.getsize(a.game)

    if a.list:
        for name, lba, unk, size in entries:
            print(f"{lba * SECTOR:#010x} {size:10d} {name}")
        print(f"{len(entries)} files")
        return

    bad = 0
    with open(a.game, 'rb') as g:
        for name, lba, unk, size in entries:
            off = lba * SECTOR
            if off + size > gsize or not name:
                print(f"!! skipping {name!r} (offset {off:#x}, size {size})")
                bad += 1
                continue
            path = os.path.normpath(os.path.join(a.out, name.lstrip('/\\')))
            if not path.startswith(os.path.normpath(a.out)):
                print(f"!! suspicious path skipped: {name!r}"); bad += 1; continue
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            g.seek(off)
            with open(path, 'wb') as f:
                f.write(g.read(size))
    print(f"{len(entries) - bad} files extracted to {a.out}/ ({bad} skipped)")


if __name__ == '__main__':
    main()
    