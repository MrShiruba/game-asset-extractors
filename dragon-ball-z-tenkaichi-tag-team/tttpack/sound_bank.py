"""
Sound effect banks (libsndp "PPHD"): every sample is written as a .vag (split_vags).

A bank is two consecutive parts of a big-endian nested archive (see text.split_archive):
    part i     sample data: PSX ADPCM (16-byte frames), every sample starts with a
               zero frame and ends with a frame whose flag byte has bit 0 set
               (flags 7 = end, 3 = loop back to the frame flagged 6)
    part i+1   header, little-endian:
        "PPHD", u32 header size (0x38), u32 version (0x10000), -1,
        u32 offsets (from the PPHD start) of the PPPG, PPTN and PPVA sections, -1.
        PPPG = programs, PPTN = tones (key ranges, volume, envelope -> sample),
        PPVA = samples: "PPVA", u32 size, u32 0x10, -1, u32 0, u32 count, -1, -1,
               then count + 1 x (u32 offset in the data part, u32 sample rate,
                             u32 size, -1); size >= 0x80000000 = empty slot.
               (the field is the last slot number: 96 for the 97 slots of a
               character's bank, as the section size, 0x18 + 16 x 97, shows)

Where the banks are:
    1427 + 5 x block + 4   one bank per battle character (same blocks as the voices)
    13267                  battle (hits, explosions...)
    13938                  Dragon Walker (story map)
    0, sub-entries 0/1     another bank inside the first entry
"""
import functools
import os
import re
import struct

from .text import split_archive

FRAME = 16
EMPTY = 0x80000000


def read_samples(header):
    """PPHD header bytes -> [(slot, offset, rate, size)] for the non-empty slots, or None."""
    if header[:4] != b"PPHD" or len(header) < 0x20:
        return None
    va = struct.unpack_from("<I", header, 0x18)[0]
    if va + 0x20 > len(header) or header[va:va + 4] != b"PPVA":
        return None
    count = struct.unpack_from("<I", header, va + 0x14)[0] + 1
    if va + 0x20 + 16 * count > len(header):
        return None
    samples = []
    for slot in range(count):
        offset, rate, size, _ = struct.unpack_from("<4I", header, va + 0x20 + 16 * slot)
        if size < EMPTY and size:
            samples.append((slot, offset, rate, size))
    return samples


def find_banks(data, depth=2, path=()):
    """Yield (sub-entry path of the data part, data part, PPHD part) found in an entry."""
    parts = split_archive(data)
    if not parts:
        return
    for k, part in enumerate(parts):
        if k and part[:4] == b"PPHD" and read_samples(part):
            yield path + (k - 1,), parts[k - 1], part
        elif depth > 1 and part[:4] != b"PPHD":
            yield from find_banks(part, depth - 1, path + (k,))


def sound_bank_pair(data):
    """(sample data, PPHD header) when an entry is just one sound bank, else None."""
    parts = split_archive(data)
    if parts and len(parts) == 2 and parts[1][:4] == b"PPHD" and read_samples(parts[1]):
        return parts[0], parts[1]
    return None


def vag(data, rate, name=b""):
    """A .vag file (Sony "VAGp", mono): a 48-byte header in front of the same ADPCM bytes,
    nothing re-encoded. Header (big-endian): "VAGp", version 0x20, 0, data size, sample
    rate, 12 zero bytes, 16-byte name."""
    return (b"VAGp" + struct.pack(">4I", 0x20, 0, len(data), rate) + bytes(12)
            + name[:16].ljust(16, b"\0") + data)


def slot_count(header):
    va = struct.unpack_from("<I", header, 0x18)[0]
    return struct.unpack_from("<I", header, va + 0x14)[0] + 1


@functools.lru_cache(maxsize=None)
def _sample_names(list_name):
    """{slot: name} from a list of kastomd's Editor_indice_Py ("97-61: 096_skill_005_8.vag",
    numbered from 1, over every slot of the bank's table)."""
    names = {}
    path = os.path.join(os.path.dirname(__file__), "data", "editor_indice_py", list_name)
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = re.match(r"\s*(\d+)-[0-9A-Fa-f]+:\s*\d+_(.+?)\.vag\s*$", line)
            if m:
                names[int(m.group(1)) - 1] = re.sub(r"[^a-z0-9]+", "_", m.group(2).lower()).strip("_")
    return names


# banks told apart by their slot count, as kastomd's tool does: 97 = a battle
# character's bank (hurt, melee, special states, skills...), 85 = the battle bank 13267
SAMPLE_NAMES = {97: "sfx_ch.txt", 85: "sfx_bt.txt"}


def split_vags(body, header):
    """[(slot, name or None, .vag bytes)] for the samples of a bank (.pbd data, .phd
    header)."""
    out = []
    count = slot_count(header) if read_samples(header) is not None else 0
    names = _sample_names(SAMPLE_NAMES[count]) if count in SAMPLE_NAMES else {}
    for slot, offset, rate, size in read_samples(header) or ():
        if offset + size <= len(body):
            out.append((slot, names.get(slot), vag(body[offset:offset + size], rate, b"%03d" % slot)))
    return out
