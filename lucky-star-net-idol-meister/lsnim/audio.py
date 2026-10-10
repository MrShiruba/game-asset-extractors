"""File type detection and CRI ACX (list of ADX/AHX streams)."""
import struct


SIGNATURES = [
    (b'@UTF', 'utf', '.utf'), (b'CPK ', 'cpk', '.cpk'), (b'AFS\0', 'afs', '.afs'),
    (b'AFS2', 'awb', '.awb'), (b'MIG.00.1PSP', 'gim', '.gim'), (b'TIM2', 'tm2', '.tm2'),
    (b'\x89PNG', 'png', '.png'), (b'\xff\xd8\xff', 'jpg', '.jpg'), (b'RIFF', 'at3', '.at3'),
    (b'PSMF', 'pmf', '.pmf'), (b'\0\0\1\xba', 'mpg', '.mpg'), (b'OggS', 'ogg', '.ogg'),
    (b'GXT', 'gxt', '.gxt'),
]


def detect_type(header):
    """Return (folder_name, extension) from the first bytes of a file."""
    if header[:2] == b'\x80\x00' and len(header) >= 0x14:   # CRI ADX / AHX
        kind = 'ahx' if header[4] in (0x10, 0x11) else 'adx'
        encrypted = header[0x13] in (8, 9)
        return kind + ('_encrypted' if encrypted else ''), '.' + kind
    if len(header) >= 16 and header[:4] == b'\0\0\0\0':     # CRI ACX: list of ADX/AHX
        count, first = struct.unpack_from('>II', header, 4)
        if 0 < count < 4096 and first == 8 + 8 * count and header[first:first + 2] == b'\x80\x00':
            return 'acx', '.acx'
    for signature, folder, extension in SIGNATURES:
        if header.startswith(signature):
            return folder, extension
    return 'bin', '.bin'                         # raw game data (scripts, textures...)


def split_acx(data):
    """CRI ACX: u32 0, u32 count, then count x (u32 offset, u32 size), big endian.
    Returns the ADX/AHX streams it holds."""
    count = struct.unpack_from('>I', data, 4)[0]
    streams = []
    for k in range(count):
        offset, size = struct.unpack_from('>II', data, 8 + 8 * k)
        streams.append(data[offset:offset + size])
    return streams
