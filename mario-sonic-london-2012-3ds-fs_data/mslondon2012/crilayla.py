"""CRILAYLA decompression (CRI CPK compression)."""
import struct


def crilayla_decompress(data):
    unc_size, hdr_off = struct.unpack_from("<II", data, 8)
    out = bytearray(unc_size + 0x100)
    raw_hdr = data[0x10 + hdr_off:0x10 + hdr_off + 0x100]
    if len(raw_hdr) != 0x100:
        raise ValueError("truncated CRILAYLA header")
    out[0:0x100] = raw_hdr

    in_pos = 0x10 + hdr_off - 1
    pool = 0
    left = 0

    def bits(n):
        nonlocal in_pos, pool, left
        v = 0
        while n:
            if left == 0:
                if in_pos < 0x10:
                    raise ValueError("CRILAYLA stream overrun")
                pool = data[in_pos]
                in_pos -= 1
                left = 8
            take = left if left < n else n
            left -= take
            v = (v << take) | ((pool >> left) & ((1 << take) - 1))
            n -= take
        return v

    out_end = 0x100 + unc_size - 1
    written = 0
    while written < unc_size:
        if bits(1):
            ref = out_end - written + bits(13) + 3
            length = 3
            for nb in (2, 3, 5, 8):
                lvl = bits(nb)
                length += lvl
                if lvl != (1 << nb) - 1:
                    break
            else:
                while True:
                    lvl = bits(8)
                    length += lvl
                    if lvl != 0xFF:
                        break
            if ref > out_end:
                raise ValueError("invalid CRILAYLA back-reference")
            for _ in range(min(length, unc_size - written)):
                out[out_end - written] = out[ref]
                ref -= 1
                written += 1
        else:
            out[out_end - written] = bits(8)
            written += 1
    return bytes(out)
