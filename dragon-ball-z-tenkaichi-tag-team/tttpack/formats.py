"""File type detection for PACKFILE entries."""
import struct
import zlib

from .atrac3 import is_atrac3_mono

MAGICS = [  # (signature, offset, extension)
    (b"RIFF", 0, "riff"), (b"VAGp", 0, "vag"), (b"SSCF", 0, "sscf"), (b"SShd", 0, "sshd"),
    (b"SSbd", 0, "ssbd"), (b"IECS", 0, "scei"), (b"MSF", 0, "msf"), (b"PSMF", 0, "pmf"),
    (b"@UTF", 0, "utf"), (b"AFS\0", 0, "afs"), (b"\x7fELF", 0, "elf"), (b"\0PGD", 0, "pgd"),
    (b"OggS", 0, "ogg"), (b"MIG.", 0, "gim"), (b".BBQ", 0, "bbq"),
    (b"\x89PNG", 0, "png"), (b"PK\x03\x04", 0, "zip"),
]

AUDIO_TYPES = {"at3", "atrac3_unknown", "wav", "riff", "vag", "sscf", "sshd", "ssbd",
               "scei", "msf", "adx", "ogg", "afs", "utf"}


def is_text(b):
    from .text import is_text_table, looks_like_text, read_text_table
    if not is_text_table(b):
        return False
    try:
        return looks_like_text(read_text_table(b))
    except (struct.error, ValueError):
        return False


SCREEN = 480 * 272 * 4


def screens(b):
    """Raw 480x272 RGBA8888 screens (entry 8: boot logos), stored bottom-up -> count or 0."""
    n = len(b) // SCREEN
    return n if b and len(b) == n * SCREEN and n <= 8 else 0


def is_motion(b):
    """Animation data: u8 0x61, u8 variant, u16 frame count, u16 0, u16 track count, u16 0."""
    if len(b) < 12 or b[0] != 0x61:
        return False
    frames, zero1, tracks, zero2 = struct.unpack_from("<HHHH", b, 2)
    return not zero1 and not zero2 and frames and 1 <= tracks <= 512 and 10 + 2 * tracks <= len(b)


def unwrap_zlib(b):
    """Parts stored as u32 BE size, u32 BE packed size, zlib stream, padding -> data or None."""
    if len(b) < 10 or b[8] != 0x78:
        return None
    size, packed = struct.unpack_from(">II", b, 0)
    if 8 + packed > len(b) or len(b) - 8 - packed >= 64:
        return None
    try:
        data = zlib.decompress(b[8:8 + packed])
    except zlib.error:
        return None
    return data if len(data) == size else None


def guess_ext(b):
    if is_atrac3_mono(b):
        return "at3"
    if b[:1] and b[0] & 0xFC == 0xA0:
        return "atrac3_unknown"          # looks like ATRAC3 but with another frame size
    if b[:2] == b"BM" and len(b) >= 6 and 0 <= len(b) - struct.unpack("<I", b[2:6])[0] < 64:
        return "bmp"          # some are padded to 64 bytes inside archives
    if b[:4] == b"\x60\x0b\x9a\x7e":
        return "map"          # map / stage geometry (Dragon Walker maps, battle stages)
    if is_text(b):
        return "tbl"          # text table, also written decoded to text/
    if b[:2] == b"\x80\x00" and len(b) >= 4:
        copyright_at = struct.unpack(">H", b[2:4])[0] - 2
        if b[copyright_at:copyright_at + 6] == b"(c)CRI":
            return "adx"
    for sig, off, ext in MAGICS:
        if b[off:off + len(sig)] == sig:
            if ext == "riff" and b[8:12] == b"WAVE":
                return "at3" if b[20:22] in (b"\xfe\xff", b"\x70\x02") else "wav"
            return ext
    if is_motion(b):
        return "mot"
    head = b[:4]
    if len(head) == 4 and head[3] == 0 and all(0x41 <= c <= 0x5A for c in head[:3]):
        return head[:3].decode("ascii").lower()      # AGS\0, RHG\0 ...
    if len(head) == 4 and all(32 <= c < 127 for c in head):
        return head.decode("ascii").strip(". /\\").lower() or "bin"
    return "bin"
