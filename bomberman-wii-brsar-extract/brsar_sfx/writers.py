"""BRSTM writer (Wii audio stream, the format NW4R games use for streamed audio).

A BRSTM can carry two kinds of audio, selected with ``codec``:

* ``"pcm16"`` - 16-bit big-endian PCM: lossless, bit-exact copy of the render.
* ``"adpcm"`` - Nintendo DSP-ADPCM (4 bits/sample): about 3.5x smaller, lossy.

Converting a BRSTM to another format (WAV, FLAC...) is left to existing tools
such as vgmstream or ffmpeg.
"""

from __future__ import annotations

import struct
from typing import List, Optional, Sequence

import numpy as np

from .dsp import EncodedStream

CODEC_PCM16 = 1
CODEC_ADPCM = 2

ADPCM_BLOCK_SAMPLES = 0x3800   # 14336 samples = 0x2000 bytes per channel per block
PCM16_BLOCK_SAMPLES = 0x1000   # 4096 samples  = 0x2000 bytes per channel per block
BLOCK_BYTES = 0x2000


def _pad(b: bytes, align: int = 0x20) -> bytes:
    return b + b"\0" * ((-len(b)) % align)


def build_brstm(sample_rate: int, *, adpcm: Optional[Sequence[EncodedStream]] = None,
                pcm16: Optional[np.ndarray] = None, loop_start: int = -1) -> bytes:
    """Build a BRSTM from either encoded DSP-ADPCM channels or int16 PCM (channels, n).

    ``loop_start`` >= 0 sets a loop from that sample to the end.
    """
    if (adpcm is None) == (pcm16 is None):
        raise ValueError("give exactly one of adpcm= or pcm16=")
    if adpcm is not None:
        codec = CODEC_ADPCM
        nch = len(adpcm)
        total = adpcm[0].num_samples
        block_samples = ADPCM_BLOCK_SAMPLES
        channel_data = [s.data for s in adpcm]
        bytes_for = lambda n: (n + 13) // 14 * 8
    else:
        codec = CODEC_PCM16
        pcm16 = np.asarray(pcm16, dtype=np.int16)
        nch, total = pcm16.shape
        block_samples = PCM16_BLOCK_SAMPLES
        channel_data = [pcm16[c].astype(">i2").tobytes() for c in range(nch)]
        bytes_for = lambda n: n * 2

    nblocks = max(1, (total + block_samples - 1) // block_samples)
    last_samples = total - (nblocks - 1) * block_samples
    last_bytes = bytes_for(last_samples)
    last_bytes_padded = (last_bytes + 0x1F) & ~0x1F

    # ---- HEAD (offsets inside are relative to HEAD+8) ---------------------
    chunk1 = 0x18
    chunk2 = chunk1 + 0x34
    track_entry = chunk2 + 4 + 8          # one track
    chunk3 = track_entry + 4
    ch_refs = chunk3 + 4
    ch_info = ch_refs + 8 * nch           # each: ref (8) + adpcm info (0x30)
    head_len = (8 + ch_info + nch * (8 + 0x30) + 0x1F) & ~0x1F

    adpc = b""
    if codec == CODEC_ADPCM:
        body = bytearray()
        for b in range(nblocks):
            for s in adpcm:
                h1, h2 = s.block_history[b] if b < len(s.block_history) else (0, 0)
                body += struct.pack(">hh", h1, h2)
        adpc_len = (8 + len(body) + 0x1F) & ~0x1F
        adpc = _pad(b"ADPC" + struct.pack(">I", adpc_len) + bytes(body))

    head_off = 0x40
    adpc_off = head_off + head_len if adpc else 0
    data_off = head_off + head_len + len(adpc)
    audio_off = data_off + 0x20
    loop = loop_start >= 0

    h = bytearray()
    for off in (chunk1, chunk2, chunk3):
        h += struct.pack(">II", 0x01000000, off)
    h += struct.pack(">BBBBHHIIIIIIIIIII",
                     codec, 1 if loop else 0, nch, 0,
                     sample_rate, 0,
                     max(loop_start, 0), total,
                     audio_off, nblocks,
                     BLOCK_BYTES, block_samples,
                     last_bytes, last_samples, last_bytes_padded,
                     block_samples if codec == CODEC_ADPCM else 0,
                     4 if codec == CODEC_ADPCM else 0)
    assert len(h) == chunk2
    h += struct.pack(">BBH", 1, 0, 0)
    h += struct.pack(">II", 0x01000000, track_entry)
    h += struct.pack(">BBBB", nch, 0, 1 if nch > 1 else 0, 0)
    assert len(h) == chunk3
    h += struct.pack(">BBH", nch, 0, 0)
    for c in range(nch):
        h += struct.pack(">II", 0x01000000, ch_info + c * (8 + 0x30))
    for c in range(nch):
        here = ch_info + c * (8 + 0x30)
        h += struct.pack(">II", 0x01000000, here + 8)
        if codec == CODEC_ADPCM:
            s = adpcm[c]
            h += struct.pack(">16h", *[int(v) for v in s.coefs])
            h += struct.pack(">HHhhHhhH", 0, s.initial_ps, 0, 0, s.initial_ps if loop else 0, 0, 0, 0)
        else:
            h += b"\0" * 0x30
    head = _pad(b"HEAD" + struct.pack(">I", head_len) + bytes(h))
    assert len(head) == head_len

    audio = bytearray()
    for b in range(nblocks):
        a = b * BLOCK_BYTES
        for d in channel_data:
            if b < nblocks - 1:
                audio += d[a:a + BLOCK_BYTES].ljust(BLOCK_BYTES, b"\0")
            else:
                audio += d[a:a + last_bytes].ljust(last_bytes_padded, b"\0")
    data_len = 0x20 + len(audio)
    data = b"DATA" + struct.pack(">II", data_len, 0x18) + b"\0" * 0x14 + bytes(audio)

    total_len = data_off + data_len
    header = bytearray(b"RSTM" + struct.pack(">HHIHH", 0xFEFF, 0x0100, total_len, 0x40, 2))
    header += struct.pack(">6I", head_off, head_len, adpc_off, len(adpc), data_off, data_len)
    return _pad(bytes(header), 0x40) + head + adpc + data


def write_brstm(path: str, sample_rate: int, **kwargs) -> None:
    with open(path, "wb") as f:
        f.write(build_brstm(sample_rate, **kwargs))
