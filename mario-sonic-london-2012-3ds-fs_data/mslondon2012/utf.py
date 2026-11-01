"""CRI @UTF tables (used by CPK, ACB and ACF files)."""
import struct


def unmask_utf(b):
    out = bytearray(b)
    m = 0x655F
    for i in range(len(out)):
        out[i] ^= m & 0xFF
        m = (m * 0x4115) & 0xFFFFFFFF
    return bytes(out)


_UTF_FMT = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i",
            6: ">Q", 7: ">q", 8: ">f"}


def parse_utf(b):
    """Returns (table_name, [columns], [row dicts])."""
    if b[:4] != b"@UTF":
        u = unmask_utf(b)
        if u[:4] != b"@UTF":
            raise ValueError("no @UTF table")
        b = u
    tsize, = struct.unpack(">I", b[4:8])
    d = b[8:8 + tsize]
    rows_off, str_off, data_off, name_off, ncol, rowlen, nrows = \
        struct.unpack(">IIIIHHI", d[:24])

    def s(o):
        o += str_off
        return d[o:d.index(b"\0", o)].decode("utf-8", "replace")

    def rd(t, p):
        f = _UTF_FMT.get(t)
        if f:
            n = struct.calcsize(f)
            return struct.unpack(f, d[p:p + n])[0], p + n
        if t == 0xA:
            o, = struct.unpack(">I", d[p:p + 4])
            return s(o), p + 4
        if t == 0xB:
            o, l = struct.unpack(">II", d[p:p + 8])
            return d[data_off + o:data_off + o + l], p + 8
        raise ValueError("unknown @UTF column type %x" % t)

    p = 24
    cols = []
    for _ in range(ncol):
        flag = d[p]
        p += 1
        no, = struct.unpack(">I", d[p:p + 4])
        p += 4
        st, t, const = flag & 0xF0, flag & 0x0F, None
        if st == 0x30:
            const, p = rd(t, p)
        cols.append((s(no), st, t, const))
    rows = []
    for r in range(nrows):
        p = rows_off + r * rowlen
        row = {}
        for name, st, t, const in cols:
            if st == 0x50:
                row[name], p = rd(t, p)
            elif st == 0x30:
                row[name] = const
            else:
                row[name] = None
        rows.append(row)
    return s(name_off), [c[0] for c in cols], rows


def utf_rows(blob):
    return parse_utf(blob)[2] if blob else []
