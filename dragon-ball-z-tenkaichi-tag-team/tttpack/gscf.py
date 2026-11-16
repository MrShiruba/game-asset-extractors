"""
GSCF event scripts (PACKFILE entries 13401..13568), run by the event VM of the EBOOT
(native function table at 0x08A7E458, interpreter at 0x089C7F28).

File layout: chunks of (tag, u32 header size, u32 data size, u32 id):
    GSCF / GSHD / GSCD (containers), GSAC (one program, id = program number),
    GSDT (constant pool, int32), EOFC (end of container).

Instructions are little-endian u32 words; the low nibble is the type:
    1 = call native:  byte 1 = number of positional args, high u16 = native id,
        followed by the positional arg words, then tagged groups:
        word with low nibble 8: byte 1 = tag letter, byte 2 = value count, then values.
    Argument values with low nibble 0xA are references to the constant pool
    (index = word >> 8).

Natives used here (handlers in the EBOOT):
    2  (0x089CB9B8)  chapter / Dragon Walker episode number (0..30)
    7  (0x089CC1F0)  'v' groups (?, line id, condition, speaker): lines that may be
                     spoken; speaker = story character number (audio_map.
                     STORY_CHARACTER_IDS), also given for lines with no fighter slot
    19 (0x089CD7D0)  'v' groups (line id, speaker slot): who says each line;
                     slot = 0x8000 for the enemy team, low bits = team member.
                     Lines with no slot are off-screen (narrator...).
"""
import struct

NATIVE_CHAPTER = 2
NATIVE_SPEAKERS = 19
ENEMY = 0x8000


def chunks(data):
    pos = 0
    while pos + 16 <= len(data):
        tag = data[pos:pos + 4]
        header, size, ident = struct.unpack_from("<III", data, pos + 4)
        if header < 16:
            return
        yield pos, tag, header, size, ident
        pos += header if tag in (b"GSCF", b"GSCD") else header + size


def parse(data):
    """Return (constant pool bytes, [(program id, code bytes)])."""
    pool, programs = b"", []
    for pos, tag, header, size, ident in chunks(data):
        body = data[pos + header:pos + header + size]
        if tag == b"GSDT":
            pool = body
        elif tag == b"GSAC":
            programs.append((ident - (1 << 32) if ident >= 1 << 31 else ident, body))
    return pool, programs


def _value(pool, word):
    if word & 0xF == 0xA:
        k = word >> 8
        if 4 * k + 4 <= len(pool):
            return struct.unpack_from("<i", pool, 4 * k)[0]
    return None


def native_calls(code, pool):
    """Yield (native id, positional args, {tag: [[values], ...]})."""
    words = [struct.unpack_from("<I", code, i)[0] for i in range(0, len(code) - 3, 4)]
    i = 0
    while i < len(words):
        w = words[i]
        if w & 0xF != 1:
            i += 1
            continue
        count, native = (w >> 8) & 0xFF, w >> 16
        args = [_value(pool, x) for x in words[i + 1:i + 1 + count]]
        j = i + 1 + count
        groups = {}
        while j < len(words) and words[j] & 0xF == 8:
            tag, n = chr((words[j] >> 8) & 0xFF), (words[j] >> 16) & 0xFF
            groups.setdefault(tag, []).append([_value(pool, x) for x in words[j + 1:j + 1 + n]])
            j += 1 + n
        yield native, args, groups
        i = j


NATIVE_LINES = 7


def battle_info(data, spoken=None, voiced=None):
    """Return (chapter or None, {line id: speaker slot}) for one GSCF file.

    spoken: optional set, filled with every line id declared by native 7.
    voiced: optional list, filled with (line id, story character number) from native 7.
    """
    pool, programs = parse(data)
    chapter, speakers = None, {}
    for _, code in programs:
        for native, args, groups in native_calls(code, pool):
            if native == NATIVE_CHAPTER and chapter is None and args and args[0] is not None:
                chapter = args[0]
            elif native == NATIVE_LINES and (spoken is not None or voiced is not None):
                spoken = set() if spoken is None else spoken
                for group in groups.get("v", []):
                    if len(group) >= 2 and group[1] is not None:
                        spoken.add(group[1])
                        if voiced is not None and len(group) >= 4 and group[3] is not None:
                            voiced.append((group[1], group[3]))
            elif native == NATIVE_SPEAKERS:
                for group in groups.get("v", []):
                    if len(group) >= 2 and None not in group[:2]:
                        speakers[group[0]] = group[1]
    return chapter, speakers
