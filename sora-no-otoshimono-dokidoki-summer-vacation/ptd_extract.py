#!/usr/bin/env python3
"""
PETA (.ptd) extractor - Sora no Otoshimono DokiDoki Summer Vacation (PSP, ULJM05639)

Extracts every file with its original name and path, in its original format
(ADX stays ADX, GIM stays GIM, ...). Nested .ptd archives (res/__pack__/*.ptd)
are kept as-is AND their contents are extracted too.

Format (reverse-engineered from EBOOT functions 0x62d4 / 0x66b4 / 0x67a4 / 0x78c0):

  Header (0x120 bytes)
    0x00  'PETA'
    0x04  u32  header + table size (table ends here)
    0x08  u32  total archive size
    0x0C  u32  table offset (0x120)
    0x10  u32  file count
    0x14  u16  directory count
    0x16  u8   table encrypted (1/0)
    0x20  256  substitution key

  Table decryption (i = position from 0x120):
    plain[i] = key[(cipher[i] ^ -i) & 0xFF]

  Table
    directories: 0x50-byte entries -> +0 file entries offset, +4 first file index,
                                      +8 file count, +0x10 name (64 bytes)
    files:       0x40-byte entries -> +0 offset, +4 size, +8 compressed (u8),
                                      +0x10 name (48 bytes)

  'YKLZ' compression (LZSS), used by the game itself (not an audio/image codec):
    0x00 'YKLZ', 0x06 u8 compressed, 0x07 u8 bits (length = b0 >> (bits-8)),
    0x08 u32 decompressed size, data at 0x10.
    Flag byte read MSB first: 0 = literal,
    1 = reference: b0,b1 -> len = (b0 >> s) + 3 ; dist = ((b0 & ((1<<s)-1)) << 8 | b1) + 1
"""
import argparse
import os
import struct
import sys


def yklz_decompress(buf):
    if buf[:4] != b'YKLZ':
        raise ValueError('not a YKLZ block')
    compressed = buf[6]
    shift = buf[7] - 8
    size = struct.unpack_from('<I', buf, 8)[0]
    src = 0x10
    if not compressed:
        return bytes(buf[src:src + size])
    mask = (1 << shift) - 1
    out = bytearray()
    while len(out) < size:
        flags = buf[src]; src += 1
        for _ in range(8):
            if len(out) >= size:
                break
            if flags & 0x80:
                b0 = buf[src]; b1 = buf[src + 1]; src += 2
                length = (b0 >> shift) + 3
                dist = ((b0 & mask) << 8 | b1) + 1
                start = len(out) - dist
                if start < 0:
                    raise ValueError('LZ reference out of bounds')
                for k in range(length):
                    out.append(out[start + k])
            else:
                out.append(buf[src]); src += 1
            flags = (flags << 1) & 0xFF
    return bytes(out[:size])


def read_table(f, base):
    f.seek(base)
    hdr = f.read(0x120)
    if hdr[:4] != b'PETA':
        raise ValueError('PETA signature not found at 0x%X' % base)
    tsize, total, toff, nfiles = struct.unpack_from('<4I', hdr, 4)
    ndirs = struct.unpack_from('<H', hdr, 0x14)[0]
    enc = hdr[0x16]
    key = hdr[0x20:0x120]
    f.seek(base + toff)
    t = bytearray(f.read(tsize - toff))
    if enc:
        for i in range(len(t)):
            t[i] = key[(t[i] ^ (-i)) & 0xFF]
    tab = bytearray(toff) + t  # index by absolute offset within the archive
    dirs = []
    for d in range(ndirs):
        o = toff + d * 0x50
        foff, first, count = struct.unpack_from('<3I', tab, o)
        name = bytes(tab[o + 0x10:o + 0x50]).split(b'\0')[0].decode('ascii', 'replace')
        dirs.append((name, first, count & 0xFFFF))
    fbase = struct.unpack_from('<I', tab, toff)[0]
    files = []
    for i in range(nfiles):
        o = fbase + i * 0x40
        off, size = struct.unpack_from('<2I', tab, o)
        comp = tab[o + 8]
        name = bytes(tab[o + 0x10:o + 0x40]).split(b'\0')[0].decode('ascii', 'replace')
        files.append((name, off, size, comp))
    return dirs, files, total


def extract(f, base, outdir, args, depth=0, label=''):
    dirs, files, total = read_table(f, base)
    owner = {}
    for dname, first, count in dirs:
        for i in range(first, first + count):
            owner[i] = dname
    n = 0
    for i, (name, off, size, comp) in enumerate(files):
        path = (owner.get(i, '') + '/' + name).strip('/')
        if not args.keep_case:
            path = path.lower()
        f.seek(base + off)
        if args.list:
            data = f.read(4)
            print('%s%-60s off=0x%08X size=%-9d %s' % ('  ' * depth, path, base + off, size, 'LZ' if comp else ''))
            n += 1
            if data == b'PETA' and not comp:
                n += extract(f, base + off, outdir, args, depth + 1, path)
            continue
        data = f.read(size)
        if comp:
            try:
                data = yklz_decompress(data)
            except Exception as e:
                print('  ! %s: decompression failed (%s), raw data kept' % (path, e), file=sys.stderr)
        dst = os.path.join(outdir, path)
        os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
        with open(dst, 'wb') as o:
            o.write(data)
        n += 1
        if data[:4] == b'PETA' and not comp:
            n += extract(f, base + off, outdir, args, depth + 1, path)
    if not args.list:
        print('%s%s: %d files' % ('  ' * depth, label or f.name, len(files)))
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
            total += extract(f, 0, args.out, args, label=p)
    if not args.list:
        print('Done: %d files written to %s/' % (total, args.out))


if __name__ == '__main__':
    main()
