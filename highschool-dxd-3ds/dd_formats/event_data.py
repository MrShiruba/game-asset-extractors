"""data/event/flag.dat and data/event/tutorial.dat -> readable text."""
import struct


def _sjis(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')


def flag_dat_to_txt(d):
    """flag.dat: 74-byte records = flag name (17 bytes, ASCII) + comment (57 bytes, Shift-JIS)."""
    R = 74
    if len(d) % R:
        raise ValueError('size %d is not a multiple of %d' % (len(d), R))
    lines = []
    for i in range(len(d) // R):
        r = d[i * R:(i + 1) * R]
        lines.append('%d\t%s\t%s' % (i, _sjis(r[:17]), _sjis(r[17:])))
    return '\n'.join(lines) + '\n'


def _page_lines(p):
    """A page = an index of u16 line offsets, then null-terminated Shift-JIS lines.
    The text starts at the first clean, printable string; every line after it is kept."""
    chunks, pos = [], 0
    while pos < len(p):
        e = p.find(b'\0', pos)
        e = len(p) if e < 0 else e
        chunks.append(p[pos:e]); pos = e + 1
    def clean(b):
        try:
            s = b.decode('cp932')
        except UnicodeDecodeError:
            return None
        return s if len(s) >= 2 and all(ch.isprintable() for ch in s) else None

    lines, started = [], False
    for c in chunks:
        if not started:
            # the last index entry has no 0 byte before the first line: strip its bytes
            for j in range(len(c)):
                s = clean(c[j:])
                if s is not None:
                    lines.append(s); started = True
                    break
            continue
        try:
            lines.append(c.decode('cp932'))
        except UnicodeDecodeError:
            lines.append(c.decode('cp932', 'replace'))
    while lines and not lines[-1]:
        lines.pop()
    return lines


def tutorial_dat_to_txt(d):
    """tutorial.dat: u32 page count, u32 page offsets, then the pages."""
    n = struct.unpack_from('<I', d, 0)[0]
    if not 0 < n < 1000 or 4 + 4 * n > len(d):
        raise ValueError('invalid header')
    offs = list(struct.unpack_from('<%dI' % n, d, 4)) + [len(d)]
    out = []
    for i in range(n):
        out.append('==== page %d ====' % i)
        out += _page_lines(d[offs[i]:offs[i + 1]])
        out.append('')
    return '\n'.join(out)
