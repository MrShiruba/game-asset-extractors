#!/usr/bin/env python3
"""
dump_eboot_tables.py - Check the audio tables of audio_map.py against a decrypted
EBOOT.BIN of Dragon Ball Z Tenkaichi Tag Team (JP ULJS00311, US ULUS10537, EU ULES01456).

The tables are searched by content, so any release works; the script prints where each
one is. Known positions (file offsets): JP / US / EU
    character blocks         0x265680 / 0x2666F8 / 0x2668C0   161 bytes, internal id -> block
    story episodes           0x26C708 / 0x26D810 / 0x26D9D0   31 x (start, end) u32
    story character numbers  0x26C458 / 0x26D560 / 0x26D720   85 u32, script number -> id

Usage: python3 tools/dump_eboot_tables.py EBOOT.BIN
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tttpack import audio_map  # noqa: E402

KNOWN = {   # table -> file offset in the Japanese EBOOT, used when the search fails
    "character blocks": 0x265680,
    "story episodes": 0x26C708,
    "story character numbers": 0x26C458,
}


def expected_tables():
    blocks = bytearray([0xFF] * 161)
    for block, (cid, _) in enumerate(audio_map.CHARACTERS):
        blocks[cid] = block
    story = b"".join(struct.pack("<II", a, b) for a, b in audio_map.STORY_EPISODES)
    chars = struct.pack("<%dI" % len(audio_map.STORY_CHARACTER_IDS), *audio_map.STORY_CHARACTER_IDS)
    return {"character blocks": bytes(blocks), "story episodes": story,
            "story character numbers": chars}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip())
    data = open(sys.argv[1], "rb").read()
    if data[:4] != b"\x7fELF":
        print("warning: not an ELF file - is the EBOOT decrypted?")
    for name, table in expected_tables().items():
        pos = data.find(table)
        if pos >= 0:
            print("%-24s OK at 0x%06X" % (name, pos))
            continue
        known = KNOWN[name]
        same = sum(a == b for a, b in zip(table, data[known:known + len(table)]))
        print("%-24s NOT FOUND (at the Japanese position 0x%06X: %d of %d bytes match)"
              % (name, known, same, len(table)))


if __name__ == "__main__":
    main()
