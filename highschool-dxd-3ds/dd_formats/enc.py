""".enc archives (LZO1X-compressed entries)."""
import struct

from .lzo import lzo1x_decompress


def read_enc(d):
    """.enc archive: u32 count, then (stored size | 0x80000000 if LZO1X, final size, offset)."""
    n = struct.unpack_from('<I', d, 0)[0]
    if n == 0 or 4 + 12 * n > len(d):
        raise ValueError('invalid header')
    out = []
    for i in range(n):
        c, r, o = struct.unpack_from('<3I', d, 4 + 12 * i)
        size = c & 0x7FFFFFFF
        if o + size > len(d):
            raise ValueError('entry %d out of file bounds' % i)
        blob = d[o:o + size]
        out.append(lzo1x_decompress(blob, r) if c & 0x80000000 else blob)
    return out


def guess_ext(b):
    if b[:4] == b'CTX ':
        return '.ctx'
    if b[:4] == b'CWAV':
        return '.bcwav'
    return '.bin'
