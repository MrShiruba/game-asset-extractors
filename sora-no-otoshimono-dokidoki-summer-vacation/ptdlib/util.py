"""Small output helpers (standard library only)."""
import os
import struct
import zlib


def write_file(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'wb') as o:
        o.write(data)


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as o:
        o.write(text)


def write_png(path, width, height, rgba):
    """Minimal 8-bit RGBA PNG writer."""
    stride = width * 4
    raw = b''.join(b'\0' + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(height))

    def chunk(tag, body):
        c = tag + body
        return struct.pack('>I', len(body)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 6))
           + chunk(b'IEND', b''))
    write_file(path, png)
