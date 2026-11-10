"""VGP (.vgp): headerless bank of PSP-ADPCM (VAG) sounds.

Sounds are stored back to back as 16-byte ADPCM frames. Each sound ends with
a frame flagged 1, then an end-marker frame 00 07 77 77 ...; zero frames pad
between sounds. The sample rate is not stored; it is always 44100 Hz.

Each sound is written as a standard 'VAGp' file (big-endian header, mono).
"""
import os
import struct

from .util import write_file

RATE = 44100
END_FRAME = b'\x00\x07' + b'\x77' * 14


def split(b):
    """Split the bank into lists of 16-byte frames (end markers removed)."""
    sounds, cur = [], []
    zero = bytes(16)
    for o in range(0, len(b) - 15, 16):
        f = b[o:o + 16]
        if f[1] == 7:                  # end marker frame
            if cur:
                sounds.append(cur)
            cur = []
            continue
        if not cur and f == zero:      # padding between sounds
            continue
        cur.append(f)
    if cur:
        sounds.append(cur)
    return sounds


def make_vag(frames, name, rate=RATE):
    """Wrap frames in a VAGp header, with a leading zero frame and an end marker."""
    body = bytes(16) + b''.join(frames) + END_FRAME
    hdr = (b'VAGp' + struct.pack('>IIII', 0x20, 0, len(body), rate)
           + bytes(12) + name.encode('ascii', 'replace')[:16].ljust(16, b'\0'))
    return hdr + body


def convert(path, data):
    """Write <name>_vag/<name>_NNN.vag. Returns the file count."""
    base = os.path.splitext(path)[0]
    name = os.path.basename(base)
    sounds = split(data)
    for k, frames in enumerate(sounds):
        sname = '%s_%03d' % (name, k)
        write_file(os.path.join(base + '_vag', sname + '.vag'), make_vag(frames, sname))
    return len(sounds)
