"""text/*.bin string tables."""
import struct


def strings_bin_to_txt(d):
    """text/*.bin: u32 count, then one 16-byte entry per string (absolute offset, Shift-JIS)."""
    n = struct.unpack_from('<I', d, 0)[0]
    lines = []
    for i in range(n):
        o = struct.unpack_from('<I', d, 16 * (i + 1))[0]
        s = d[o:d.index(b'\0', o)].decode('cp932', 'replace').replace('\r', '').replace('\n', '\\n')
        lines.append('%d\t%s' % (i, s))
    return '\n'.join(lines) + '\n'
