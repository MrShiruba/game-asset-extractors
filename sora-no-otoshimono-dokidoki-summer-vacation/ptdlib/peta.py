"""PETA (.ptd) archives.

Reverse-engineered from EBOOT functions 0x62d4 / 0x66b4 / 0x67a4 / 0x78c0.

Header (0x120 bytes, little-endian)
    0x00 'PETA'
    0x04 u32  header + table size (table ends here)
    0x08 u32  total archive size
    0x0C u32  table offset (0x120)
    0x10 u32  file count
    0x14 u16  directory count
    0x16 u8   table encrypted (1/0)
    0x20 256  substitution key

Table decryption (i = position from the start of the table):
    plain[i] = key[(cipher[i] ^ -i) & 0xFF]

Directory entries: 0x50 bytes -> +0 file entries offset, +4 first file index,
                                 +8 file count, +0x10 path (64 bytes)
File entries:      0x40 bytes -> +0 offset, +4 stored size, +8 YKLZ flag (u8),
                                 +0x10 name (48 bytes)
"""
import struct

MAGIC = b'PETA'


def decrypt(data, key):
    """Substitution cipher shared by the PETA table and SOS strings."""
    return bytes(key[(c ^ -i) & 0xFF] for i, c in enumerate(data))


def read_table(f, base=0):
    """Return (dirs, files, total_size) of the archive starting at `base`.

    dirs:  [(path, first_index, count)]
    files: [(name, offset, stored_size, compressed)]
    """
    f.seek(base)
    hdr = f.read(0x120)
    if hdr[:4] != MAGIC:
        raise ValueError('PETA signature not found at 0x%X' % base)
    tsize, total, toff, nfiles = struct.unpack_from('<4I', hdr, 4)
    ndirs = struct.unpack_from('<H', hdr, 0x14)[0]
    enc = hdr[0x16]
    key = hdr[0x20:0x120]
    f.seek(base + toff)
    t = f.read(tsize - toff)
    if enc:
        t = decrypt(t, key)
    tab = bytes(toff) + t  # index by absolute offset within the archive
    dirs = []
    for d in range(ndirs):
        o = toff + d * 0x50
        _, first, count = struct.unpack_from('<3I', tab, o)
        name = tab[o + 0x10:o + 0x50].split(b'\0')[0].decode('ascii', 'replace')
        dirs.append((name, first, count & 0xFFFF))
    fbase = struct.unpack_from('<I', tab, toff)[0]
    files = []
    for i in range(nfiles):
        o = fbase + i * 0x40
        off, size = struct.unpack_from('<2I', tab, o)
        comp = tab[o + 8]
        name = tab[o + 0x10:o + 0x40].split(b'\0')[0].decode('ascii', 'replace')
        files.append((name, off, size, comp))
    return dirs, files, total


def entries(f, base=0, lower=True):
    """Yield (path, absolute_offset, stored_size, compressed) for each file."""
    dirs, files, _ = read_table(f, base)
    owner = {}
    for dname, first, count in dirs:
        for i in range(first, first + count):
            owner[i] = dname
    for i, (name, off, size, comp) in enumerate(files):
        path = (owner.get(i, '') + '/' + name).strip('/')
        yield (path.lower() if lower else path), base + off, size, comp
