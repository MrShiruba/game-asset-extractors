"""LZSS decompressor for Dragon Ball Z: Shinbutouden (Saturn).

Header: big-endian u32.
  bit 31     : 0 = byte mode, 1 = word (16-bit) mode
  bits 0..30 : number of decompressed units - 1 (bytes or words)

Byte mode (bit 31 = 0):
  flags    : 1 byte, read from bit 0 to bit 7; 1 = literal (1 byte)
  reference: little-endian u16; distance = w >> 4, length = (w & 15) + 3
Word mode (bit 31 = 1):
  flags    : big-endian u16, read from bit 15 to bit 0; 1 = literal (u16)
  reference: big-endian u16; distance = w >> 4, length = (w & 15) + 3 (in words)
The copy starts at (output position - distance), one unit at a time;
anything before the start of the buffer reads as zero.
"""
import struct


def unpacked_size(data, off=0):
    hdr = struct.unpack_from('>I', data, off)[0]
    n = (hdr & 0x7FFFFFFF) + 1
    return n * 2 if hdr >> 31 else n


def decompress(data, off=0):
    """Return (decompressed_data, bytes_consumed)."""
    hdr = struct.unpack_from('>I', data, off)[0]
    n = (hdr & 0x7FFFFFFF) + 1
    i = off + 4
    if hdr >> 31 == 0:
        out = bytearray()
        while len(out) < n:
            flags = data[i]; i += 1
            for bit in range(8):
                if len(out) >= n:
                    break
                if flags >> bit & 1:
                    out.append(data[i]); i += 1
                else:
                    w = data[i] | data[i + 1] << 8; i += 2
                    src = len(out) - (w >> 4)
                    for _ in range((w & 15) + 3):
                        out.append(out[src] if 0 <= src < len(out) else 0)
                        src += 1
        return bytes(out[:n]), i - off
    words = []
    while len(words) < n:
        flags = data[i] << 8 | data[i + 1]; i += 2
        for bit in range(15, -1, -1):
            if len(words) >= n:
                break
            if flags >> bit & 1:
                words.append(data[i] << 8 | data[i + 1]); i += 2
            else:
                w = data[i] << 8 | data[i + 1]; i += 2
                src = len(words) - (w >> 4)
                for _ in range((w & 15) + 3):
                    words.append(words[src] if 0 <= src < len(words) else 0)
                    src += 1
    return struct.pack('>%dH' % n, *words[:n]), i - off


MAX_UNITS = 0x400000  # sanity limit: no block in the game exceeds a few hundred KB


def try_decompress(data, off=0, end=None, max_slack=16):
    """Decompress only if the stream ends exactly at `end` (end of file by default).

    The stream is accepted if it ends between end - max_slack and end (the game
    sometimes pads with a few bytes). Return the data, or None.
    """
    end = len(data) if end is None else end
    if end - off < 6:
        return None
    hdr = struct.unpack_from('>I', data, off)[0]
    if (hdr & 0x7FFFFFFF) >= MAX_UNITS:
        return None
    try:
        out, used = decompress(data[:end], off)
    except IndexError:
        return None
    if end - max_slack <= off + used <= end:
        return out
    return None
