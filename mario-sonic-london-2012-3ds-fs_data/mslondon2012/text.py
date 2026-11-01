"""Message tables (the game's text files) and their export to .txt.

Layout: u16 count, u16 flags, count x u32 offsets (from the file start),
then UTF-16LE strings, each ending with a 0x0000 character. Strings keep the
game's tags, e.g. [C3] / [C0] for colours.
"""
import struct


def is_message_table(blob):
    if len(blob) < 8:
        return False
    n, = struct.unpack_from("<H", blob, 0)
    if not n or 4 + 4 * n > len(blob):
        return False
    offs = struct.unpack_from("<%dI" % n, blob, 4)
    if offs[0] != 4 + 4 * n or any(o > len(blob) or o % 2 for o in offs):
        return False
    return list(offs) == sorted(offs)


def message_strings(blob):
    n, = struct.unpack_from("<H", blob, 0)
    offs = struct.unpack_from("<%dI" % n, blob, 4)
    out = []
    for o in offs:
        e = o
        while e + 1 < len(blob) and blob[e:e + 2] != b"\0\0":
            e += 2
        out.append(blob[o:e].decode("utf-16-le", "replace"))
    return out


def message_txt(blob):
    """Readable text: one '--- NNNN ---' header per string, then the string."""
    lines = []
    for i, s in enumerate(message_strings(blob)):
        lines.append("--- %04d ---" % i)
        lines.append(s)
    return "\n".join(lines) + "\n"
