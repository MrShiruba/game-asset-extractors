"""
Text tables and nested archives found in PACKFILE entries.

Text table (e.g. entries 1193..1223, one per Dragon Walker chapter; entry 0 / part 2
for the interface):
    u16 100, u16 id base (10000 for story chapters, 0 for the interface), u32 last id,
    u32 id count (last - base + 1; in the US / EU releases a value outside the file),
    then (14 + count) u32 byte offsets from 0x10: 14 reserved slots, then one slot per
    id from the base (slot 14 + id - base). Each offset points to a NUL-terminated
    UTF-16LE string; ids without text hold an offset inside the table.
    The .txt files give the text id of each line (the ids used by scripts and params).

Nested archive (e.g. entry 0, entries 13734..13765), big-endian:
    u32 count, (count + 1) u32 offsets, data. Empty sub-entries have equal offsets.
"""
import struct

TEXT_VERSION = 100


TABLE_START = 0x0C


def is_text_table(data):
    if len(data) < 0x14 or struct.unpack_from("<H", data, 0)[0] != TEXT_VERSION:
        return False
    first, second = struct.unpack_from("<II", data, TABLE_START)
    if any(TABLE_START < o < len(data) for o in (first, second)):
        return True
    # otherwise look at the text slots only: small tables whose reserved slots all point
    # at one empty string (main menu 17, part 26: ids 20000..20007), and the European
    # chapter texts (1255..1378), whose first reserved slots hold other values
    base, last = struct.unpack_from("<HI", data, 2)
    start = SLOTS_START + 4 * RESERVED_SLOTS
    end = start + 4 * (last - base + 1)
    if not (base <= last < base + 8192 and end <= len(data)):
        return False
    slots = struct.unpack_from("<%dI" % (last - base + 1), data, start)
    return all(o < len(data) for o in slots) and any(o >= end for o in slots)


class Texts(list):
    """List of strings (None for ids without text), index = id - base."""
    base = 0


def read_text_table(data):
    """Return a Texts list (index = id - base, .base = first id)."""
    texts = _read_text_table(data)
    result = Texts(texts if texts is not None else _read_text_table_scan(data))
    result.base = struct.unpack_from("<H", data, 2)[0] if texts is not None else 0
    return result


RESERVED_SLOTS = 14
SLOTS_START = 0x10


def _read_text_table(data):
    base, last = struct.unpack_from("<HI", data, 2)
    count = last - base + 1
    table_end = SLOTS_START + 4 * (RESERVED_SLOTS + count)
    if 0 < count and table_end <= len(data):
        texts = []
        for o in struct.unpack_from("<%dI" % count, data, SLOTS_START + 4 * RESERVED_SLOTS):
            if o < table_end or o >= len(data):
                texts.append(None)
                continue
            end = o
            while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
                end += 2
            texts.append(data[o:end].decode("utf-16-le", "replace"))
        if any(t is not None for t in texts):
            return texts
    return None


def _read_text_table_scan(data):
    """Fallback for tables whose header does not give the id range."""
    offsets, pos, first_text = [], TABLE_START, len(data)
    while pos + 4 <= len(data) and pos < first_text:
        o = struct.unpack_from("<I", data, pos)[0]
        offsets.append(o)
        if TABLE_START <= o < first_text:
            first_text = o
        pos += 4
    table_end = pos
    # Unused ids all point to the same place, at or just before the end of the table.
    lowest = min(o for o in offsets if o < len(data))
    null = {o for o in offsets if o < table_end or o >= len(data)}
    if offsets.count(lowest) > 1:
        null.add(lowest)
    texts = []
    for o in offsets:
        if o in null or o >= len(data):
            texts.append(None)
            continue
        end = o
        while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
            end += 2
        texts.append(data[o:end].decode("utf-16-le", "replace"))
    return texts


# The game font draws button icons for the half-width katakana U+FF67.. (in this order,
# the icons of entry 0 / part 6). They are written as [names] in the .txt files.
BUTTONS = ("+", "[START]", "[SELECT]", "[○]", "[□]", "[△]", "[×]", "[L]", "[R]", "[Stick]",
           "[Stick↑]", "[Stick↓]", "[Stick→]", "[Stick←]", "[○ mash]", "[□ mash]", "[△ mash]",
           "[× mash]", "[□ hold]", "[△ hold]", "[D-pad↑]", "[D-pad↓]", "[D-pad→]", "[D-pad←]",
           "×", "™", "(", ")", "/", "®", "→")
_BUTTON_MAP = {0xFF67 + k: v for k, v in enumerate(BUTTONS)}


def readable(text):
    """Text with the button icons written as [names]."""
    return text.translate(_BUTTON_MAP)


def format_text_table(texts):
    """One line per id: 'id<TAB>text', newlines shown as \\n, button icons as [names]."""
    base = getattr(texts, "base", 0)
    return "".join("%d\t%s\n" % (base + i, readable(t).replace("\n", "\\n"))
                   for i, t in enumerate(texts) if t is not None)


def split_archive(data):
    """Return the sub-entries of a big-endian nested archive, or None."""
    if len(data) < 8:
        return None
    count = struct.unpack_from(">I", data, 0)[0]
    if not 1 <= count <= 4096 or 4 + 4 * (count + 1) > len(data):
        return None
    offsets = struct.unpack_from(">%dI" % (count + 1), data, 4)
    if offsets[0] < 4 + 4 * (count + 1) or offsets[-1] > len(data):
        return None
    if any(b < a for a, b in zip(offsets, offsets[1:])):
        return None
    return [data[a:b] for a, b in zip(offsets, offsets[1:])]


def looks_like_text(texts):
    """Reject tables that only happen to start with the right header."""
    real = [t for t in texts if t]
    if len(real) < 5:
        return False
    chars = "".join(real)
    good = sum(1 for c in chars if c in "\n\t" or 0x20 <= ord(c) < 0x7F or 0xA0 <= ord(c) < 0x250
               or 0x3000 <= ord(c) <= 0x9FFF
               or 0xFF00 <= ord(c) <= 0xFFEF or 0x2000 <= ord(c) <= 0x26FF)
    return good >= 0.95 * len(chars)


def find_text_tables(data, depth=2):
    """Yield (path, texts) for every text table in data, looking into nested archives.

    path is a tuple of sub-entry numbers, () for the entry itself.
    """
    if is_text_table(data):
        texts = read_text_table(data)
        if looks_like_text(texts):
            yield (), texts
            return
    if depth <= 0:
        return
    parts = split_archive(data)
    if parts is None:
        return
    for k, part in enumerate(parts):
        for sub, texts in find_text_tables(part, depth - 1):
            yield (k,) + sub, texts
