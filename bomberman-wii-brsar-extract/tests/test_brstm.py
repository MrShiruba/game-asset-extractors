import struct

import numpy as np

from brsar_sfx import dsp, writers


def test_brstm_layout():
    x = (np.sin(np.arange(40000) / 10) * 5000).astype(np.int16)
    enc = dsp.encode_many([x, x // 2])
    b = writers.build_brstm(32000, adpcm=enc)
    assert b[:4] == b"RSTM"
    assert struct.unpack(">I", b[8:12])[0] == len(b)
    head = struct.unpack(">I", b[0x10:0x14])[0]
    assert b[head:head + 4] == b"HEAD"
    info = head + 0x20
    codec, loop, nch = b[info], b[info + 1], b[info + 2]
    rate, = struct.unpack(">H", b[info + 4:info + 6])
    total, = struct.unpack(">I", b[info + 12:info + 16])
    assert (codec, loop, nch, rate, total) == (2, 0, 2, 32000, 40000)
    data = struct.unpack(">I", b[0x20:0x24])[0]
    assert b[data:data + 4] == b"DATA"


def test_brstm_pcm16_is_lossless():
    x = (np.sin(np.arange(9000) / 7) * 9000).astype(np.int16)
    pcm = np.stack([x, -x])
    b = writers.build_brstm(32000, pcm16=pcm)
    head = struct.unpack(">I", b[0x10:0x14])[0]
    assert b[head + 0x20] == 1  # codec PCM16
    data = struct.unpack(">I", b[0x20:0x24])[0]
    audio = b[data + 0x20:]
    # 9000 samples = 2 full blocks of 4096 + a last block of 808 samples per channel
    blocks = []
    pos = 0
    for size in (0x2000, 0x2000, (808 * 2 + 0x1F) & ~0x1F):
        chans = []
        for _ in range(2):
            chans.append(np.frombuffer(audio[pos:pos + size], ">i2"))
            pos += size
        blocks.append(chans)
    rebuilt = np.stack([np.concatenate([bl[c] for bl in blocks])[:9000] for c in range(2)])
    assert np.array_equal(rebuilt, pcm)
