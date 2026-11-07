"""LZO1X decompression, used by the .enc archives."""


def lzo1x_decompress(src, out_len=None):
    """LZO1X decompressor (compatible with lzo1x_decompress / minilzo)."""
    out = bytearray()
    ip = 0
    n = len(src)

    def copy_match(dist, length):
        mp = len(out) - dist
        if mp < 0:
            raise ValueError('lookbehind overrun')
        for _ in range(length):
            out.append(out[mp]); mp += 1

    state = 0  # literals copied by the previous token (0..3), or 4 = after a long literal run
    t = src[ip]
    if t > 17:
        ip += 1
        t -= 17
        out += src[ip:ip+t]; ip += t
        state = 4 if t >= 4 else t
        if t < 4:
            # a match token follows directly
            pass
    while True:
        t = src[ip]; ip += 1
        if t < 16:
            if state == 0:
                # literal run
                if t == 0:
                    while src[ip] == 0:
                        t += 255; ip += 1
                    t += 15 + src[ip]; ip += 1
                t += 3
                out += src[ip:ip+t]; ip += t
                state = 4
                continue
            elif state == 4:
                # M1 after a long literal run: distance 0x801..0xC00, length 3
                dist = 1 + 0x800 + (t >> 2) + (src[ip] << 2); ip += 1
                copy_match(dist, 3)
            else:
                # M1: distance 1..0x400, length 2
                dist = 1 + (t >> 2) + (src[ip] << 2); ip += 1
                copy_match(dist, 2)
        elif t >= 64:
            dist = 1 + ((t >> 2) & 7) + (src[ip] << 3); ip += 1
            copy_match(dist, (t >> 5) + 1)
        elif t >= 32:
            length = t & 31
            if length == 0:
                while src[ip] == 0:
                    length += 255; ip += 1
                length += 31 + src[ip]; ip += 1
            length += 2
            dist = 1 + ((src[ip] >> 2) + (src[ip+1] << 6)); ip += 2
            copy_match(dist, length)
        else:  # 16..31: M4
            dist = (t & 8) << 11
            length = t & 7
            if length == 0:
                while src[ip] == 0:
                    length += 255; ip += 1
                length += 7 + src[ip]; ip += 1
            length += 2
            dist += (src[ip] >> 2) + (src[ip+1] << 6); ip += 2
            if dist == 0:
                break  # end of stream
            dist += 0x4000
            copy_match(dist, length)
        # trailing literals (low 2 bits of the second-to-last byte read)
        t = src[ip-2] & 3
        if t:
            out += src[ip:ip+t]; ip += t
        state = t
    if out_len is not None and len(out) != out_len:
        raise ValueError('size %d != %d' % (len(out), out_len))
    return bytes(out)
