"""
Raw ATRAC3 handling.

Voices/sounds are headerless ATRAC3, mono, 0x98-byte frames, played at 22050 Hz.
Music uses the same codec in stereo: 0x130-byte frames (2 x 0x98, left then right), 44100 Hz.
make_at3() wraps raw frames in a standard RIFF .at3 header (readable by vgmstream / ffmpeg).
"""
import struct

FRAME_MONO = 0x98
FRAME_STEREO = 2 * FRAME_MONO
SAMPLES_PER_FRAME = 1024


def is_atrac3_mono(b):
    """True if every 0x98-byte frame starts with an ATRAC3 sound unit header (0xA0-0xA3)."""
    if len(b) < FRAME_MONO or len(b) % FRAME_MONO:
        return False
    return all(b[i] & 0xFC == 0xA0 for i in range(0, len(b), FRAME_MONO))


def make_at3(data, channels, rate):
    block = FRAME_MONO * channels
    ext = struct.pack("<HIHHHH", 1, 0x800 * channels, 0, 0, 1, 0)
    fmt = struct.pack("<HHIIHHH", 0x270, channels, rate, rate * block // SAMPLES_PER_FRAME,
                      block, 0, len(ext)) + ext
    fact = struct.pack("<II", len(data) // block * SAMPLES_PER_FRAME, SAMPLES_PER_FRAME)
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"fact" + struct.pack("<I", len(fact)) + fact
            + b"data" + struct.pack("<I", len(data)) + data)
    return b"RIFF" + struct.pack("<I", len(body)) + body
