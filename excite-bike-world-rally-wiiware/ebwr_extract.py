#!/usr/bin/env python3
"""
Excitebike: World Rally (WiiWare) - extractor for .res/.trk/.car archives (0TSR + QuickLZ)

Usage:
    python3 ebwr_extract.py <00000002_app_OUT_directory> [output_directory]

- Reads tocres.res (compressed with QuickLZ level 3) to retrieve the .toc for each archive
- Extracts all files from each .res / .trk / .car (compressed or uncompressed)
"""
import os
import struct
import sys

# ---------------------------------------------------------------- QuickLZ L3
def qlz_decompress(src):
    flags = src[0]
    if flags & 2:
        _zsize, size = struct.unpack_from('<II', src, 1)
        s = 9
    else:
        size = src[2]
        s = 3
    if not flags & 1:
        return bytes(src[s:s + size])
    dst = bytearray()
    last = size - 1
    cw = struct.unpack_from('<I', src, s)[0]
    s += 4
    while True:
        if cw == 1:
            cw = struct.unpack_from('<I', src, s)[0]
            s += 4
        fetch = int.from_bytes(src[s:s + 4].ljust(4, b'\0'), 'little')
        if cw & 1:
            cw >>= 1
            if fetch & 3 == 0:
                off = (fetch & 0xff) >> 2; ml = 3; s += 1
            elif fetch & 2 == 0:
                off = (fetch & 0xffff) >> 2; ml = 3; s += 2
            elif fetch & 1 == 0:
                off = (fetch & 0xffff) >> 6; ml = ((fetch >> 2) & 15) + 3; s += 2
            elif fetch & 127 != 3:
                off = (fetch >> 7) & 0x1ffff; ml = ((fetch >> 2) & 0x1f) + 2; s += 3
            else:
                off = fetch >> 15; ml = ((fetch >> 7) & 255) + 3; s += 4
            p = len(dst) - off
            for i in range(ml):
                dst.append(dst[p + i])
        elif len(dst) < last - 10:
            dst.append(src[s]); s += 1; cw >>= 1
        else:
            while len(dst) <= last:
                if cw == 1:
                    s += 4; cw = 1 << 31
                dst.append(src[s]); s += 1; cw >>= 1
            return bytes(dst)


# ---------------------------------------------------------------- Archives
def load_res(path):
    """Returns (file_count, decompressed_data)."""
    d = open(path, 'rb').read()
    if d[:4] != b'0TSR':
        raise ValueError('not a 0TSR archive')
    count, size, zsize, offset = struct.unpack_from('<4I', d, 0x20)
    if size == zsize:                     # uncompressed
        return count, d[0x80:]
    pos = 0x80  # the field at 0x2c is not the data offset (0xc80 in UICommon)
    out = bytearray()
    while len(out) < size:
        nxt = d.find(b'PMCr', pos)
        if nxt < 0:
            raise ValueError('PMCr block not found after 0x%x (%d/%d bytes) : %s'
                             % (pos, len(out), size, d[pos:pos + 32].hex(' ')))
        pos = nxt
        csz = struct.unpack_from('<I', d, pos + 8)[0]
        out += qlz_decompress(d[pos + 0x10:pos + 0x10 + csz])
        pos += 0x10 + csz
    return count, bytes(out)


def parse_toc(toc, count, base):
    """Entries of 0x28 bytes: name_off, type, ?, size, offset, hash, 0*4."""
    names = base + 0x28 * count
    files = []
    for i in range(count):
        no, typ, _u, size, off = struct.unpack_from('<I4sIII', toc, base + i * 0x28)
        name = toc[names + no:].split(b'\0', 1)[0].decode('latin-1')
        files.append((name, typ[::-1].decode('latin-1', 'replace'), off, size))
    return files


# ---------------------------------------------------------------- Main
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(src, '_extracted')
    tcount, tdata = load_res(os.path.join(src, 'tocres.res'))
    tocs = {}
    for name, _t, off, size in parse_toc(tdata, tcount, 0):
        tocs[name.lower()] = tdata[off:off + size]

    for fn in sorted(os.listdir(src)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in ('.res', '.trk', '.car') or fn.lower() == 'tocres.res':
            continue
        toc = tocs.get(stem.lower() + '.toc')
        if toc is None:
            print('[!] no toc found for', fn)
            continue
        try:
            count, data = load_res(os.path.join(src, fn))
        except Exception as e:
            print('[!]', fn, e)
            continue
        outdir = os.path.join(dst, fn)
        for name, typ, off, size in parse_toc(toc, count, 0x20):
            p = os.path.join(outdir, typ.strip('\0 ') or 'misc', name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            blob = data[off:off + size]
            with open(p, 'wb') as f:
                f.write(blob)
        print('[+] %-28s %d files' % (fn, count))
    print('Done ->', dst)


if __name__ == '__main__':
    main()
