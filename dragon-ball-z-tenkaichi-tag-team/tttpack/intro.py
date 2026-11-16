"""
Pre-battle dialogue (voices 853..1003).

When two given characters are on the same team (tag partners, checked in game), the
battle intro code (EBOOT 0x089057xx, voice played by
0x08907498 as index 853 + n) looks them up in a table of character pairs:

    PACKFILE entry 13261 (Japanese) or the first non-empty of 13262..13266 (US / EU),
    sub-entry 1:
        u16 count, u16 padding, then count records of 16 bytes:
        u16 line A, u16 character A (internal id), u16 priority A, u16 pad,
        u16 line B, u16 character B (internal id), u16 priority B, u16 pad
    -> character A says voice 853 + line A, its partner B answers with 853 + line B.

A line can be shared by several forms of one character (e.g. Goku / SSJ / SSJ2).
"""
import struct

from . import audio_map
from .text import split_archive

INTRO_TABLE_ENTRY = 13261
# battle_ui archives: 13261 = Japanese; the US / EU releases leave it empty and have
# one copy per language in 13262..13266 (en, es, fr, de, it).
INTRO_TABLE_ENTRIES = range(13261, 13267)
INTRO_TABLE_PART = 1
INTRO_BASE = 853


def read_pairs(data):
    """Return {voice index: (speaker name, partner name)} from entry 13261, or {}."""
    parts = split_archive(data)
    if not parts or len(parts) <= INTRO_TABLE_PART:
        return {}
    table = parts[INTRO_TABLE_PART]
    if len(table) < 4:
        return {}
    count = struct.unpack_from("<H", table, 0)[0]
    if 4 + 16 * count > len(table):
        return {}
    order = {cid: k for k, (cid, _) in enumerate(audio_map.CHARACTERS)}
    names = dict(audio_map.CHARACTERS)
    speakers, partners = {}, {}
    for k in range(count):
        line_a, char_a, _, _, line_b, char_b, _, _ = struct.unpack_from("<8H", table, 4 + 16 * k)
        if char_a not in names or char_b not in names:
            return {}          # not the expected table
        for line, me, other in ((line_a, char_a, char_b), (line_b, char_b, char_a)):
            speakers.setdefault(INTRO_BASE + line, set()).add(me)
            partners.setdefault(INTRO_BASE + line, set()).add(other)
    first = lambda ids: names[min(ids, key=order.get)]   # earliest form in roster order
    return {index: (first(speakers[index]), first(partners[index])) for index in speakers}
