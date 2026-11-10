"""YKLZ: the game's LZSS container compression.

    0x00 char[4] 'YKLZ'
    0x06 u8      1 = compressed, 0 = stored
    0x07 u8      bit split b (length uses the top b - 8 bits of b0)
    0x08 u32     decompressed size
    0x10 ...     data

Flag byte read MSB first: 0 = literal byte,
1 = reference b0, b1 with s = b - 8:
    length   = (b0 >> s) + 3
    distance = ((b0 & ((1 << s) - 1)) << 8 | b1) + 1
"""
import struct

MAGIC = b'YKLZ'


def decompress(buf):
    if buf[:4] != MAGIC:
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
