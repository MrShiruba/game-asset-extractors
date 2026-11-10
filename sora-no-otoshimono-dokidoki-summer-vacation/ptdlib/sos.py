"""SOS (.sos): compiled scripts.

    0x00 87 4C 74 68 (magic)
    0x08 u32 code offset (0x140)
    0x0C u32 file size
    0x10..0x24 u32 section offsets
    0x18 u32 string table offset (runs to the end of the file)
    0x40 256 substitution key

The bytecode is plain. Only the string table is encrypted, with the PETA cipher
(i counted from the start of the string table). Strings are NUL-terminated
Shift-JIS (CP932) and are referenced by their offset in the table.
"""
import os
import struct

from . import peta
from .util import write_text

MAGIC = b'\x87Lth'


def strings(b):
    """Return [(offset, raw_bytes)] from the decrypted string table."""
    if b[:4] != MAGIC:
        raise ValueError('not a SOS script')
    key = b[0x40:0x140]
    soff = struct.unpack_from('<I', b, 0x18)[0]
    plain = peta.decrypt(b[soff:], key)
    res, pos = [], 0
    for s in plain.split(b'\0'):
        res.append((pos, s))
        pos += len(s) + 1
    return res[:-1] if res and res[-1][1] == b'' else res


def convert(path, b):
    """Write <name>.txt: one 'OFFSET<TAB>text' line per string. Returns 1."""
    lines = []
    for off, s in strings(b):
        if s:
            txt = s.decode('cp932', 'replace').replace('\r', '\\r').replace('\n', '\\n')
            lines.append('%04X\t%s' % (off, txt))
    write_text(os.path.splitext(path)[0] + '.txt', '\n'.join(lines) + ('\n' if lines else ''))
    return 1
