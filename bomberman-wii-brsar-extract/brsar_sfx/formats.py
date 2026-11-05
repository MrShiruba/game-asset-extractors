"""Parsers for the NW4R sub-files stored inside a BRSAR.

* RSEQ - sequence (MML byte code, like a MIDI file)
* RBNK - instrument bank (program -> key split -> velocity split -> wave)
* RWAR - wave archive (a list of RWAV files)
* RWAV - one wave (PCM8 / PCM16 / DSP-ADPCM, mono or stereo)
* RWSD - "wave sound" data (a sound that directly plays one wave)

Layouts follow the NW4R runtime (see the ``doldecomp/ogws`` decompilation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from . import dsp
from .rsar import FormatError, Reader

FORMAT_PCM8, FORMAT_PCM16, FORMAT_ADPCM = 0, 1, 2

DATATYPE_NONE, DATATYPE_INSTPARAM, DATATYPE_RANGETABLE, DATATYPE_INDEXTABLE = 0, 1, 2, 3


def _blocks(r: Reader, magic: bytes) -> Dict[bytes, int]:
    """Return {block_magic: absolute offset} for a standard NW4R file header."""
    if r.magic(0) != magic:
        raise FormatError(f"expected {magic!r}, got {r.magic(0)!r}")
    n = r.u16(0x0E)
    out = {}
    for i in range(n):
        off = r.u32(0x10 + 8 * i)
        if off and off + 4 <= len(r.data):
            out[r.magic(off)] = off
    return out


# ---------------------------------------------------------------------------
# RSEQ
# ---------------------------------------------------------------------------

class Rseq:
    def __init__(self, data: bytes):
        r = Reader(data)
        blocks = _blocks(r, b"RSEQ")
        if b"DATA" not in blocks:
            raise FormatError("RSEQ without DATA block")
        d = blocks[b"DATA"]
        self.seq = bytes(data[d + r.u32(d + 8):d + r.u32(d + 4)])
        self.labels: Dict[str, int] = {}
        if b"LABL" in blocks:
            lb = blocks[b"LABL"]
            for i in range(r.u32(lb + 8)):
                lo = lb + 8 + r.u32(lb + 12 + 4 * i)
                off = r.u32(lo)
                ln = r.u32(lo + 4)
                self.labels[bytes(data[lo + 8:lo + 8 + ln]).decode("ascii", "replace")] = off


# ---------------------------------------------------------------------------
# Waves
# ---------------------------------------------------------------------------

@dataclass
class Wave:
    format: int
    loop: bool
    channels: int
    sample_rate: int
    loop_start: int          # in samples
    loop_end: int            # in samples (exclusive end of playback)
    _raw: List[tuple] = field(default_factory=list, repr=False)  # per channel: (data, offset, coefs, yn1, yn2)
    _pcm: Optional[List[np.ndarray]] = field(default=None, repr=False)

    def pcm(self) -> List[np.ndarray]:
        """Decoded samples, one float32 array (-1..1) per channel (cached)."""
        if self._pcm is None:
            out = []
            n = self.loop_end
            for data, off, coefs, yn1, yn2 in self._raw:
                if self.format == FORMAT_ADPCM:
                    s = dsp.decode(data, off, n, coefs, yn1, yn2).astype(np.float32) / 32768.0
                elif self.format == FORMAT_PCM16:
                    s = np.frombuffer(data, dtype=">i2", count=n, offset=off).astype(np.float32) / 32768.0
                else:
                    s = np.frombuffer(data, dtype=np.int8, count=n, offset=off).astype(np.float32) / 128.0
                if len(s) < n:
                    s = np.pad(s, (0, n - len(s)))
                out.append(s)
            self._pcm = out
        return self._pcm


def _sample_from_address(addr: int, fmt: int) -> int:
    if fmt == FORMAT_ADPCM:
        return dsp.nibble_to_sample(addr)
    return addr


def parse_rwav(data: bytes, base: int = 0) -> Wave:
    """Parse an RWAV located at ``base`` inside ``data``."""
    r = Reader(data)
    if r.magic(base) != b"RWAV":
        raise FormatError("expected RWAV")
    info = base + r.u32(base + 0x10)
    data_block = base + r.u32(base + 0x18)
    wi = info + 8
    fmt = r.u8(wi)
    loop = bool(r.u8(wi + 1))
    nch = r.u8(wi + 2)
    rate = (r.u8(wi + 3) << 16) | r.u16(wi + 4)
    loop_start = _sample_from_address(r.u32(wi + 8), fmt)
    loop_end = _sample_from_address(r.u32(wi + 0x0C), fmt) + 1
    table = wi + r.u32(wi + 0x10)
    sample_base = data_block + 8  # samples start right after the DATA block header
    w = Wave(fmt, loop, nch, rate, max(loop_start, 0), loop_end)
    for c in range(nch):
        ci = wi + r.u32(table + 4 * c)
        ch_off = r.u32(ci)
        adpcm_off = r.u32(ci + 4)
        coefs, yn1, yn2 = [0] * 16, 0, 0
        if fmt == FORMAT_ADPCM and adpcm_off:
            ai = wi + adpcm_off
            coefs = [r.s16(ai + 2 * k) for k in range(16)]
            yn1 = r.s16(ai + 0x24)
            yn2 = r.s16(ai + 0x26)
        w._raw.append((data, sample_base + ch_off, coefs, yn1, yn2))
    return w


class Rwar:
    """Wave archive: a table of embedded RWAV files."""

    def __init__(self, data: bytes):
        self.waves: List[Optional[Wave]] = []
        if not data:
            return
        r = Reader(data)
        blocks = _blocks(r, b"RWAR")
        tabl = blocks[b"TABL"]
        dat = blocks[b"DATA"]
        for i in range(r.u32(tabl + 8)):
            e = tabl + 12 + 12 * i
            off = r.u32(e + 4)
            try:
                self.waves.append(parse_rwav(data, dat + off))
            except FormatError:
                self.waves.append(None)

    def get(self, index: int) -> Optional[Wave]:
        if 0 <= index < len(self.waves):
            return self.waves[index]
        return None


# ---------------------------------------------------------------------------
# RBNK
# ---------------------------------------------------------------------------

@dataclass
class InstParam:
    wave_index: int
    attack: int
    decay: int
    sustain: int
    release: int
    hold: int
    original_key: int
    volume: int
    pan: int
    tune: float


class Rbnk:
    def __init__(self, data: bytes, rwar: Rwar):
        self.r = r = Reader(data)
        blocks = _blocks(r, b"RBNK")
        self.version = r.u16(6)
        self.table = blocks[b"DATA"] + 8           # instrument table (offsets are relative to it)
        self.count = r.u32(self.table)
        self.rwar = rwar

    def _sub(self, ref_off: int, split: int) -> Optional[int]:
        """Resolve a range/index table for ``split`` (key or velocity)."""
        r = self.r
        _, dtype, val = r.ref(ref_off)
        if dtype == DATATYPE_INSTPARAM:
            return ref_off
        if dtype == DATATYPE_RANGETABLE:
            t = self.table + val
            size = r.u8(t)
            i = 0
            while split > r.u8(t + 1 + i):
                i += 1
                if i >= size:
                    return None
            return t + ((size + 1 + 3) & ~3) + 8 * i
        if dtype == DATATYPE_INDEXTABLE:
            t = self.table + val
            lo, hi = r.u8(t), r.u8(t + 1)
            if split < lo or split > hi:
                return None
            return t + 4 + 8 * (split - lo)
        return None

    def inst(self, prg: int, key: int, velocity: int) -> Optional[InstParam]:
        r = self.r
        if prg < 0 or prg >= self.count:
            return None
        ref: Optional[int] = self.table + 4 + 8 * prg
        for split in (key, velocity):
            dtype = r.ref(ref)[1]
            if dtype == DATATYPE_NONE:
                return None
            if dtype != DATATYPE_INSTPARAM:
                ref = self._sub(ref, split)
                if ref is None:
                    return None
        if r.ref(ref)[1] != DATATYPE_INSTPARAM:
            return None
        p = self.table + r.ref(ref)[2]
        wave_index = r.s32(p)
        if wave_index < 0:
            return None
        newer = self.version >= 0x0101
        return InstParam(
            wave_index=wave_index,
            attack=r.u8(p + 4), decay=r.u8(p + 5), sustain=r.u8(p + 6), release=r.u8(p + 7),
            hold=r.u8(p + 8),
            original_key=r.u8(p + 0x0C),
            volume=r.u8(p + 0x0D) if newer else 127,
            pan=r.u8(p + 0x0E),
            tune=r.f32(p + 0x10) if newer else 1.0,
        )

    def wave(self, index: int) -> Optional[Wave]:
        return self.rwar.get(index)


# ---------------------------------------------------------------------------
# RWSD
# ---------------------------------------------------------------------------

@dataclass
class WsdNote:
    wave_index: int
    attack: int
    decay: int
    sustain: int
    release: int
    hold: int
    original_key: int
    volume: int
    pan: int
    pitch: float


@dataclass
class WsdEvent:
    position: float
    length: float
    note_index: int


@dataclass
class WsdSound:
    pitch: float
    pan: int
    main_send: int
    events: List[WsdEvent]
    notes: List[WsdNote]


class Rwsd:
    def __init__(self, data: bytes, rwar: Rwar):
        r = Reader(data)
        blocks = _blocks(r, b"RWSD")
        self.version = r.u16(6)
        self.rwar = rwar
        base = blocks[b"DATA"] + 8
        self.sounds: List[WsdSound] = []
        for i in range(r.u32(base)):
            w = base + r.ref(base + 4 + 8 * i)[2]
            info = base + r.ref(w)[2]
            tracks = base + r.ref(w + 8)[2]
            notes_t = base + r.ref(w + 16)[2]
            snd = WsdSound(pitch=r.f32(info), pan=r.u8(info + 4), main_send=r.u8(info + 9), events=[], notes=[])
            for t in range(r.u32(tracks)):
                tr = base + r.ref(tracks + 4 + 8 * t)[2]
                ev_t = base + r.ref(tr)[2]
                for e in range(r.u32(ev_t)):
                    eo = base + r.ref(ev_t + 4 + 8 * e)[2]
                    snd.events.append(WsdEvent(r.f32(eo), r.f32(eo + 4), r.u32(eo + 8)))
            for n in range(r.u32(notes_t)):
                no = base + r.ref(notes_t + 4 + 8 * n)[2]
                snd.notes.append(WsdNote(
                    wave_index=r.s32(no), attack=r.u8(no + 4), decay=r.u8(no + 5), sustain=r.u8(no + 6),
                    release=r.u8(no + 7), hold=r.u8(no + 8), original_key=r.u8(no + 0x0C),
                    volume=r.u8(no + 0x0D), pan=r.u8(no + 0x0E), pitch=r.f32(no + 0x10)))
            self.sounds.append(snd)
