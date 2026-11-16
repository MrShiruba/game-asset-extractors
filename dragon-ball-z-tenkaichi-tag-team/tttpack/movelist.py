"""
Character move lists (part 43 of the character archives, "move_list_name").

Records of 32 bytes (8 little-endian s32), ended by a record whose first value is -1:
    +0x00 section (0 = special moves, 1 = character moves, 2 = common moves,
          3 = transformations and fusions)
    +0x04 name: text id in the interface text table (entry 0..5, part 2)
    +0x08 input: text id of the button sequence in the same table
    +0x0C variant (1, 2 for the two versions of a move), +0x10 cost in Ki bars,
    +0x14 cost in Blast stock / order of the transformations, +0x18 and +0x1C flags.
"""
import struct

TEXT_BASE = 0
SECTIONS = ("Special moves", "Character moves", "Common moves", "Transformations")


def read_move_list(data):
    """[(section, name_id, input_id, variant, ki, blast, flag1, flag2)] or None."""
    if len(data) < 32 or len(data) % 32:
        return None
    moves = []
    for pos in range(0, len(data), 32):
        record = struct.unpack_from("<8i", data, pos)
        if record[0] == -1:
            return moves
        if not 0 <= record[0] < len(SECTIONS):
            return None
        moves.append(record)
    return moves


def format_move_list(moves, texts):
    """Text listing of the moves, with names and inputs from the interface table."""
    def text(k):
        k += TEXT_BASE
        return (texts[k] if 0 <= k < len(texts) and texts[k] is not None else "#%d" % (k - TEXT_BASE))

    from .text import readable
    lines, section = [], None
    for kind, name, keys, variant, ki, blast, _, _ in moves:
        if kind != section:
            if lines:
                lines.append("")
            lines.append("== %s ==" % SECTIONS[kind])
            section = kind
        cost = []
        if ki:
            cost.append("Ki %d" % ki)
        if blast and kind != 3:
            cost.append("Blast %d" % blast)
        lines.append("%s\t%s%s" % (readable(text(name)), readable(text(keys)).replace("\n", " "),
                                   "\t(%s)" % ", ".join(cost) if cost else ""))
    return "\n".join(lines) + "\n"
