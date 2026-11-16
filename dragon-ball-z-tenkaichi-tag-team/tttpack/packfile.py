"""
PACKFILE.BIN container (format worked out by analysis).

  0x00 'PacK' | 0x04 entry count | ... | 0x10 table of count x 16 bytes:
     +0 position in 0x800-byte sectors   XOR 'PacK'
     +4 size                             XOR entry index
     +8 compressed size (0 = stored)     XOR 'PacK'
     +C unknown                          XOR entry index
  Data starts at the end of the table aligned to 0x1000; compressed entries are gzip.
  There are no file names: entries are only referred to by index.
"""
import os
import struct
import zlib
from collections import namedtuple

MAGIC = b"PacK"
KEY = 0x4B636150          # 'PacK' as a little-endian u32
SECTOR = 0x800

Entry = namedtuple("Entry", "index sector size packed_size unknown")


def align(x, a):
    return (x + a - 1) // a * a


class PackFile:
    def __init__(self, path):
        self.path = path
        self.file_size = os.path.getsize(path)
        self.f = open(path, "rb")
        header = self.f.read(0x10)
        if header[:4] != MAGIC:
            raise ValueError("not a PACKFILE (missing 'PacK' signature)")
        count = struct.unpack_from("<I", header, 4)[0]
        table = self.f.read(count * 16)
        self.entries = []
        for i in range(count):
            a, b, c, d = struct.unpack_from("<4I", table, i * 16)
            self.entries.append(Entry(i, a ^ KEY, b ^ i, c ^ KEY, d ^ i))
        self.data_start = align(0x10 + count * 16, 0x1000)

    def offset(self, entry):
        return self.data_start + entry.sector * SECTOR

    def read(self, entry):
        """Return the entry's data (decompressed), or raise ValueError / zlib.error."""
        stored = entry.packed_size or entry.size
        pos = self.offset(entry)
        if pos + stored > self.file_size:
            raise ValueError("entry %d goes past the end of the file" % entry.index)
        self.f.seek(pos)
        raw = self.f.read(stored)
        if not entry.packed_size:
            return raw
        data = zlib.decompress(raw, 31)
        if len(data) != entry.size:
            print("Entry %d: unpacked %d bytes instead of %d" % (entry.index, len(data), entry.size))
        return data

    def close(self):
        self.f.close()
