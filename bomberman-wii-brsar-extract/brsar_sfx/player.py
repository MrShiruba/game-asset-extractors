"""Offline re-implementation of the NW4R (Wii) sound engine.

Almost every sound effect of a NW4R game is a *sequence*: a small MML program
(RSEQ) that plays notes on an instrument bank (RBNK) whose samples live in a
wave archive (RWAR).  There is no audio file to copy out - the sound only exists
once the engine plays it.  This module plays sequences (and RWSD wave sounds)
the way the Wii runtime does and mixes the result to stereo PCM.

Timing and maths follow the NW4R runtime as documented by the ``doldecomp/ogws``
decompilation (SeqPlayer / SeqTrack / MmlParser / Channel / EnvGenerator / Lfo /
Voice / Util):

* the engine runs in 3 ms frames (96 samples at 32 kHz);
* sequence ticks are advanced with the same tick-fraction logic;
* ADSR, LFO, sweep / portamento, pitch bend, pan curve, volume laws and the
  one-pole low-pass filter use the runtime's formulas and tables.

Not reproduced: the AUX effect sends (reverb / echo set by the game at run
time), Dolby Pro Logic II / surround, the Wii Remote speaker filter and
voice-stealing between sounds.  Sequence variables that the game sets from
code keep their default value (-1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

try:  # optional, only used for the low-pass filter
    from scipy.signal import lfilter as _lfilter
except Exception:  # pragma: no cover
    _lfilter = None

from .formats import Rbnk, Rwsd, Wave

OUTPUT_RATE = 32000
FRAME_MS = 3
FRAME_SAMPLES = OUTPUT_RATE * FRAME_MS // 1000  # 96

VOLUME_MIN_DB = -90.4
VOLUME_MAX_DB = 6.0

# ---------------------------------------------------------------------------
# Tables from the runtime
# ---------------------------------------------------------------------------

DECIBEL_SQUARE_TABLE = [
    -723, -722, -721, -651, -601, -562, -530, -503, -480, -460, -442, -425,
    -410, -396, -383, -371, -360, -349, -339, -330, -321, -313, -305, -297,
    -289, -282, -276, -269, -263, -257, -251, -245, -239, -234, -229, -224,
    -219, -214, -210, -205, -201, -196, -192, -188, -184, -180, -176, -173,
    -169, -165, -162, -158, -155, -152, -149, -145, -142, -139, -136, -133,
    -130, -127, -125, -122, -119, -116, -114, -111, -109, -106, -103, -101,
    -99, -96, -94, -91, -89, -87, -85, -82, -80, -78, -76, -74,
    -72, -70, -68, -66, -64, -62, -60, -58, -56, -54, -52, -50,
    -49, -47, -45, -43, -42, -40, -38, -36, -35, -33, -31, -30,
    -28, -27, -25, -23, -22, -20, -19, -17, -16, -14, -13, -11,
    -10, -8, -7, -6, -4, -3, -1, 0]

ATTACK_TABLE = [
    0.9992175, 0.9984326, 0.9976452, 0.9968553, 0.9960629, 0.9952679,
    0.9944704, 0.9936704, 0.9928677, 0.9920625, 0.9912546, 0.9904441,
    0.9896309, 0.9888151, 0.9879965, 0.9871752, 0.9863512, 0.9855244,
    0.9846949, 0.9838625, 0.9830273, 0.9821893, 0.9813483, 0.9805045,
    0.9796578, 0.9788081, 0.9779555, 0.9770999, 0.9762413, 0.9753797,
    0.9745150, 0.9736472, 0.9727763, 0.9719023, 0.9710251, 0.9701448,
    0.9692612, 0.9683744, 0.9674844, 0.9665910, 0.9656944, 0.9647944,
    0.9638910, 0.9629842, 0.9620740, 0.9611604, 0.9602433, 0.9593226,
    0.9583984, 0.9574706, 0.9565392, 0.9556042, 0.9546655, 0.9537231,
    0.9527769, 0.9518270, 0.9508732, 0.9499157, 0.9489542, 0.9479888,
    0.9470195, 0.9460462, 0.9450689, 0.9440875, 0.9431020, 0.9421124,
    0.9411186, 0.9401206, 0.9391184, 0.9381118, 0.9371009, 0.9360856,
    0.9350659, 0.9340417, 0.9330131, 0.9319798, 0.9309420, 0.9298995,
    0.9288523, 0.9278004, 0.9267436, 0.9256821, 0.9246156, 0.9235442,
    0.9224678, 0.9213864, 0.9202998, 0.9192081, 0.9181112, 0.9170091,
    0.9159016, 0.9147887, 0.9136703, 0.9125465, 0.9114171, 0.9102821,
    0.9091414, 0.9079949, 0.9068427, 0.9056845, 0.9045204, 0.9033502,
    0.9021740, 0.9009916, 0.8998029, 0.8986080, 0.8974066, 0.8961988,
    0.8949844, 0.8900599, 0.8824622, 0.8759247, 0.8691861, 0.8636406,
    0.8535788, 0.8430189, 0.8286135, 0.8149099, 0.8002172, 0.7780663,
    0.7554750, 0.7242125, 0.6828239, 0.6329169, 0.5592135, 0.4551411,
    0.3298770, 0.0000000]

SIN_TABLE = [0, 6, 12, 19, 25, 31, 37, 43, 49, 54, 60, 65, 71, 76, 81, 85, 90,
             94, 98, 102, 106, 109, 112, 115, 117, 120, 122, 123, 125, 126, 126, 127, 127]


def calc_release(r: int) -> float:
    if r == 127:
        return 65535.0
    if r == 126:
        return 24.0
    if r < 50:
        return (r * 2 + 1) / 128.0 / 5.0
    return 60.0 / (126 - r) / 5.0


def volume_ratio(db: float) -> float:
    """Util::CalcVolumeRatio (0.1 dB resolution, silence below -90.4 dB)."""
    if db < VOLUME_MIN_DB:
        db = VOLUME_MIN_DB
    elif db > VOLUME_MAX_DB:
        db = VOLUME_MAX_DB
    idx = 904 + int(10 * db)
    if idx <= 0:
        return 0.0
    return 10.0 ** ((idx - 904) / 200.0)


def pitch_ratio(semitones: float) -> float:
    """Util::CalcPitchRatio (1/256 semitone resolution)."""
    return 2.0 ** (int(256 * semitones) / 3072.0)


def _pan_index(pan: float) -> int:
    pan = (min(max(pan, -1.0), 1.0) + 1.0) / 2.0
    return int(pan * 256 + 0.5)


def pan_ratio(pan: float, curve: int) -> float:
    """Util::CalcPanRatio for the 9 NW4R pan curves."""
    idx = _pan_index(pan)
    kind, center_zero, zero_clamp = divmod(curve, 3)[0], curve % 3 >= 1, curve % 3 == 2
    if kind == 1:
        f = lambda i: math.cos(i * math.pi / 512.0)
    elif kind == 2:
        f = lambda i: 1.0 - i / 256.0
    else:
        f = lambda i: math.sqrt(1.0 - i / 256.0)
    ratio = f(idx)
    if center_zero:
        ratio /= f(128)
    return min(max(ratio, 0.0), 1.0 if zero_clamp else 2.0)


def lpf_coef(scale: float) -> Optional[float]:
    """Util::CalcLpfFreq + AX one-pole low-pass. Returns b0 or None (filter off)."""
    scale = min(max(scale, 0.0), 1.0)
    freq = int(32000 * 2.0 ** (10.0 * (scale - 1.0)))
    if freq >= 16000:
        return None
    w = 2 * math.pi * freq / OUTPUT_RATE
    c = 2.0 - math.cos(w)
    return c - math.sqrt(c * c - 1.0)


class Random:
    """Util::CalcRandom (LCG)."""

    def __init__(self, seed: int = 0x12345678):
        self.u = seed & 0xFFFFFFFF

    def next(self) -> int:
        self.u = (self.u * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.u >> 16


# ---------------------------------------------------------------------------
# Channel (one playing note / voice)
# ---------------------------------------------------------------------------

STATUS_ATTACK, STATUS_DECAY, STATUS_SUSTAIN, STATUS_RELEASE = range(4)
LFO_PITCH, LFO_VOLUME, LFO_PAN = 0, 1, 2


@dataclass
class LfoParam:
    depth: float = 0.0
    speed: float = 6.25
    delay: int = 0
    range: int = 1

    def copy(self) -> "LfoParam":
        return LfoParam(self.depth, self.speed, self.delay, self.range)


class Channel:
    def __init__(self, wave: Wave, start_frame: int, length: int, pan_curve: int, pan_mode: int):
        self.wave = wave
        self.start_frame = start_frame
        self.length = length          # ticks, -1 = until released / wave end
        self.pan_curve = pan_curve
        self.pan_mode = pan_mode
        self.track: Optional["Track"] = None  # None once "freed"
        self.active = True
        self.key = 60
        self.original_key = 60
        self.init_volume = 1.0
        self.inst_volume = 1.0
        self.init_pan = 0.0
        self.tune = 1.0
        self.user_volume = 1.0
        self.user_pitch = 0.0
        self.user_pitch_ratio = 1.0
        self.user_pan = 0.0
        self.user_lpf = 0.0
        self.main_send = 0.0
        self.lfo = LfoParam()
        self.lfo_target = LFO_PITCH
        self.lfo_counter = 0.0
        self.lfo_delay_counter = 0
        self.sweep_pitch = 0.0
        self.sweep_length = 0
        self.sweep_counter = 0
        self.auto_sweep = True
        # envelope
        self.attack = 0.0
        self.decay = 0.0
        self.sustain = 127
        self.release = 0.0
        self.env_value = VOLUME_MIN_DB * 10.0
        self.env_status = STATUS_ATTACK
        self.set_adsr(127, 127, 127, 127)
        # playback state
        self.pos = 0.0
        self.frames: List[tuple] = []
        self.end_samples = None  # samples rendered in the last frame (if partial)

    # -- envelope ------------------------------------------------------------
    def set_adsr(self, a: int, d: int, s: int, r: int) -> None:
        self.set_attack(a)
        self.set_decay(d)
        self.sustain = min(max(s, 0), 127)
        self.set_release(r)

    def set_attack(self, a: int) -> None:
        self.attack = ATTACK_TABLE[min(max(a, 0), 127)]

    def set_decay(self, d: int) -> None:
        self.decay = calc_release(min(max(d, 0), 127))

    def set_sustain(self, s: int) -> None:
        self.sustain = min(max(s, 0), 127)

    def set_release(self, r: int) -> None:
        self.release = calc_release(min(max(r, 0), 127))

    def env_db(self) -> float:
        if self.env_status == STATUS_ATTACK and self.attack == 0.0:
            return 0.0
        return self.env_value / 10.0

    def env_update(self, msec: int) -> None:
        st = self.env_status
        if st == STATUS_ATTACK:
            v = self.env_value
            a = self.attack
            while msec > 0:
                v *= a
                msec -= 1
                if v > -(1.0 / 32.0):
                    v = 0.0
                    st = STATUS_DECAY
            self.env_value = v
            self.env_status = st
            if st != STATUS_DECAY:
                return
        if st == STATUS_DECAY:
            target = DECIBEL_SQUARE_TABLE[self.sustain]
            self.env_value -= self.decay * msec
            if self.env_value <= target:
                self.env_value = target
                self.env_status = STATUS_SUSTAIN
        elif st == STATUS_RELEASE:
            self.env_value -= self.release * msec

    def do_release(self) -> None:
        if self.env_status != STATUS_RELEASE:
            self.env_status = STATUS_RELEASE

    @property
    def released(self) -> bool:
        return self.env_status == STATUS_RELEASE

    # -- lfo / sweep -------------------------------------------------------
    def lfo_value(self) -> float:
        p = self.lfo
        if p.depth == 0.0 or self.lfo_delay_counter < p.delay:
            return 0.0
        idx = int(4 * (32 * self.lfo_counter))
        if idx < 32:
            s = SIN_TABLE[idx]
        elif idx < 64:
            s = SIN_TABLE[32 - (idx - 32)]
        elif idx < 96:
            s = -SIN_TABLE[idx - 64]
        else:
            s = -SIN_TABLE[32 - (idx - 96)]
        return s / 127.0 * p.depth * p.range

    def lfo_update(self, msec: int) -> None:
        p = self.lfo
        if self.lfo_delay_counter < p.delay:
            if self.lfo_delay_counter + msec <= p.delay:
                self.lfo_delay_counter += msec
                return
            msec -= p.delay - self.lfo_delay_counter
            self.lfo_delay_counter = p.delay
        self.lfo_counter += p.speed * msec / 1000.0
        self.lfo_counter -= int(self.lfo_counter)

    def set_sweep(self, pitch: float, time: int, auto: bool) -> None:
        self.sweep_pitch = pitch
        self.sweep_length = time
        self.auto_sweep = auto
        self.sweep_counter = 0

    def update_sweep(self, count: int) -> None:
        self.sweep_counter += count
        if self.sweep_counter > self.sweep_length:
            self.sweep_counter = self.sweep_length

    def sweep_value(self) -> float:
        if self.sweep_pitch == 0.0 or self.sweep_counter >= self.sweep_length:
            return 0.0
        return self.sweep_pitch * (self.sweep_length - self.sweep_counter) / self.sweep_length

    # -- per-frame update (Channel::Update + AX voice) ----------------------
    def update(self) -> None:
        if not self.active:
            return
        lfo = self.lfo_value()
        volume = self.init_volume * self.user_volume
        ve_init = volume_ratio(self.env_db())
        if self.lfo_target == LFO_VOLUME:
            ve_init *= volume_ratio(VOLUME_MAX_DB * lfo)
        if self.env_status == STATUS_RELEASE and volume * ve_init == 0.0:
            self.active = False
            self._finish()
            return
        cent = self.key - self.original_key + self.sweep_value() + self.user_pitch
        if self.lfo_target == LFO_PITCH:
            cent += lfo
        ratio = pitch_ratio(cent) * self.tune * self.user_pitch_ratio
        pan = self.init_pan + self.user_pan
        if self.lfo_target == LFO_PAN:
            pan += lfo
        lpf = lpf_coef(1.0 + self.user_lpf)
        if self.auto_sweep:
            self.update_sweep(FRAME_MS)
        self.lfo_update(FRAME_MS)
        self.env_update(FRAME_MS)
        ve_target = volume_ratio(self.env_db())
        if self.lfo_target == LFO_VOLUME:
            ve_target *= volume_ratio(VOLUME_MAX_DB * self.lfo_value())
        main = min(max(self.main_send + 1.0, 0.0), 1.0)
        if self.wave.channels >= 2 and self.pan_mode == 0:
            gains = ((pan_ratio(pan - 1.0, self.pan_curve), pan_ratio(-(pan - 1.0), self.pan_curve)),
                     (pan_ratio(pan + 1.0, self.pan_curve), pan_ratio(-(pan + 1.0), self.pan_curve)))
        elif self.wave.channels >= 2:  # balance mode
            gains = ((pan_ratio(pan, self.pan_curve), 0.0), (0.0, pan_ratio(-pan, self.pan_curve)))
        else:
            gains = ((pan_ratio(pan, self.pan_curve), pan_ratio(-pan, self.pan_curve)),)
        src = ratio * self.wave.sample_rate / OUTPUT_RATE
        self.frames.append((src, volume * ve_init * main, volume * ve_target * main, gains, lpf))
        # advance the voice and detect the end of a one-shot wave
        self.pos += src * FRAME_SAMPLES
        w = self.wave
        if w.loop and w.loop_end > w.loop_start:
            pass
        elif self.pos >= w.loop_end:
            self.end_samples = max(1, min(FRAME_SAMPLES, int(math.ceil((w.loop_end - (self.pos - src * FRAME_SAMPLES)) / max(src, 1e-9)))))
            self.active = False
            self._finish()

    def _finish(self) -> None:
        if self.track is not None:
            self.track.remove_channel(self)
            self.track = None

    # -- rendering -------------------------------------------------------------
    def render(self) -> Optional[np.ndarray]:
        """Render the recorded frames. Returns a (2, n) float array."""
        if not self.frames:
            return None
        nfr = len(self.frames)
        src = np.array([f[0] for f in self.frames])
        v0 = np.array([f[1] for f in self.frames])
        v1 = np.array([f[2] for f in self.frames])
        n = nfr * FRAME_SAMPLES
        if self.end_samples is not None:
            n -= FRAME_SAMPLES - self.end_samples
        inc = np.repeat(src, FRAME_SAMPLES)[:n]
        pos = np.concatenate(([0.0], np.cumsum(inc)[:-1]))
        ramp = np.tile(np.arange(FRAME_SAMPLES) / FRAME_SAMPLES, nfr)[:n]
        vol = (np.repeat(v0, FRAME_SAMPLES)[:n] + (np.repeat(v1 - v0, FRAME_SAMPLES)[:n]) * ramp)
        w = self.wave
        pcm = w.pcm()
        loop = w.loop and w.loop_end > w.loop_start
        i0 = np.floor(pos).astype(np.int64)
        frac = (pos - i0).astype(np.float32)

        def idx(i):
            if loop:
                over = i >= w.loop_end
                if np.any(over):
                    span = w.loop_end - w.loop_start
                    i = np.where(over, w.loop_start + (i - w.loop_start) % span, i)
            return i

        out = np.zeros((2, n), dtype=np.float64)
        for c, data in enumerate(pcm[:2]):
            ext = np.concatenate((data, np.zeros(4, dtype=np.float32)))
            last = len(data)
            im1 = idx(np.maximum(i0 - 1, 0))
            ia = idx(i0)
            ib = idx(i0 + 1)
            ic = idx(i0 + 2)
            ia, ib, ic, im1 = (np.minimum(x, last) for x in (ia, ib, ic, im1))
            pm, p0, p1, p2 = ext[im1], ext[ia], ext[ib], ext[ic]
            # Catmull-Rom (4-point) interpolation
            t = frac
            s = p0 + 0.5 * t * (p1 - pm + t * (2 * pm - 5 * p0 + 4 * p1 - p2 + t * (3 * (p0 - p1) + p2 - pm)))
            s = s.astype(np.float64) * vol
            s = self._lowpass(s)
            gl = np.repeat(np.array([f[3][min(c, len(f[3]) - 1)][0] for f in self.frames]), FRAME_SAMPLES)[:n]
            gr = np.repeat(np.array([f[3][min(c, len(f[3]) - 1)][1] for f in self.frames]), FRAME_SAMPLES)[:n]
            out[0] += s * gl
            out[1] += s * gr
        return out

    def _lowpass(self, s: np.ndarray) -> np.ndarray:
        coefs = [f[4] for f in self.frames]
        if all(c is None for c in coefs):
            return s
        out = np.empty_like(s)
        y = 0.0
        start = 0
        nfr = len(coefs)
        while start < nfr:
            end = start
            while end < nfr and coefs[end] == coefs[start]:
                end += 1
            a, b = start * FRAME_SAMPLES, min(end * FRAME_SAMPLES, len(s))
            seg = s[a:b]
            b0 = coefs[start]
            if b0 is None:
                out[a:b] = seg
                y = seg[-1] if len(seg) else y
            elif _lfilter is not None:
                res, zf = _lfilter([1.0 - b0], [1.0, -b0], seg, zi=[b0 * y])
                out[a:b] = res
                y = res[-1] if len(res) else y
            else:  # pure Python fallback
                a0 = 1.0 - b0
                for k in range(len(seg)):
                    y = a0 * seg[k] + b0 * y
                    out[a + k] = y
            start = end
        return out


# ---------------------------------------------------------------------------
# Sequence player
# ---------------------------------------------------------------------------

class Track:
    def __init__(self, player: "SeqPlayer", no: int):
        self.player = player
        self.no = no
        self.open = False
        self.channels: List[Channel] = []
        self.seq = player.seq
        self.addr = 0
        self.wait = 0
        self.note_finish_wait = False
        self.mute = False
        self.prg = 0
        self.priority = 64
        self.volume = 127
        self.volume2 = 127
        self.pan = 0
        self.init_pan = 0
        self.surround_pan = 0
        self.pitch_bend = 0
        self.bend_range = 2
        self.attack = self.decay = self.sustain = self.release = 0xFF
        self.main_send = 127
        self.fx_send = [0, 0, 0]
        self.lpf_freq = 64
        self.porta_key = 60
        self.porta_time = 0
        self.porta_flag = False
        self.damper = False
        self.sweep_pitch = 0.0
        self.transpose = 0
        self.lfo = LfoParam()
        self.lfo_target = LFO_PITCH
        self.variables = [-1] * 16
        self.note_wait = True
        self.tie = False
        self.cmp_flag = True
        self.call_stack: List[int] = []
        self.loop_count: List[int] = []
        self.jumps_back = 0

    # -- channel list -------------------------------------------------------
    def remove_channel(self, ch: Channel) -> None:
        if ch in self.channels:
            self.channels.remove(ch)

    def release_all(self, release: int = -1) -> None:
        self.update_channel_param()
        for ch in self.channels:
            if ch.active:
                if release >= 0:
                    ch.set_release(release)
                ch.do_release()

    def free_all(self) -> None:
        for ch in self.channels:
            ch.track = None
        self.channels = []

    def close(self) -> None:
        self.release_all(-1)
        self.free_all()
        self.open = False

    def update_channel_length(self) -> None:
        if not self.open:
            return
        for ch in self.channels:
            if ch.length > 0:
                ch.length -= 1
            if ch.length == 0 and not ch.released and not self.damper:
                ch.do_release()
            if not ch.auto_sweep:
                ch.update_sweep(1)

    def update_channel_param(self) -> None:
        if not self.open or not self.channels:
            return
        p = self.player
        v = (self.volume / 127.0) ** 2 * (self.volume2 / 127.0) ** 2 * (p.main_volume / 127.0) ** 2 * p.volume
        pitch = (self.pitch_bend / 128.0) * self.bend_range
        pan = min(max(self.pan / 63.0, -1.0), 1.0)
        lpf = (self.lpf_freq - 64) / 64.0
        main_send = self.main_send / 127.0 - 1.0
        for ch in self.channels:
            ch.user_volume = v
            ch.user_pitch = pitch
            ch.user_pan = pan
            ch.user_lpf = lpf
            ch.main_send = main_send
            ch.lfo = self.lfo.copy()
            ch.lfo_target = self.lfo_target

    # -- parsing ------------------------------------------------------------
    def parse_next_tick(self, do_note_on: bool = True) -> int:
        if not self.open:
            return 0
        if self.note_finish_wait:
            if self.channels:
                return 1
            self.note_finish_wait = False
        if self.wait > 0:
            self.wait -= 1
            if self.wait > 0:
                return 1
        guard = 0
        while self.wait == 0 and not self.note_finish_wait:
            if self.parse(do_note_on) < 0:
                return -1
            guard += 1
            if guard > 100000:  # endless loop without any wait
                self.player.warnings.add("endless zero-wait loop")
                return -1
        return 1

    def _byte(self) -> int:
        if self.addr >= len(self.seq):
            raise EOFError
        b = self.seq[self.addr]
        self.addr += 1
        return b

    def _u16(self) -> int:
        return (self._byte() << 8) | self._byte()

    def _s16(self) -> int:
        v = self._u16()
        return v - 0x10000 if v >= 0x8000 else v

    def _u24(self) -> int:
        return (self._byte() << 16) | (self._byte() << 8) | self._byte()

    def _var(self) -> int:
        v = 0
        while True:
            b = self._byte()
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v

    def _arg(self, kind: str, override: Optional[str]) -> int:
        kind = override or kind
        if kind == "u8":
            return self._byte()
        if kind == "s16":
            return self._s16()
        if kind == "var":
            return self._var()
        if kind == "rnd":
            lo = self._s16()
            hi = self._s16()
            return ((self.player.rand.next() * (hi - lo + 1)) >> 16) + lo
        if kind == "ind":
            i = self._byte()
            v = self.player.get_var(self, i)
            return v if v is not None else 0
        raise ValueError(kind)

    def parse(self, do_note_on: bool) -> int:
        try:
            return self._parse(do_note_on)
        except EOFError:
            return -1

    def _parse(self, do_note_on: bool) -> int:
        p = self.player
        exec_cmd = True
        override = None
        cmd = self._byte()
        if cmd == 0xA2:  # if
            cmd = self._byte()
            exec_cmd = self.cmp_flag
        if cmd == 0xA0:  # random argument
            cmd = self._byte()
            override = "rnd"
        if cmd == 0xA1:  # variable argument
            cmd = self._byte()
            override = "ind"

        if cmd < 0x80:  # note
            velocity = self._byte()
            length = self._arg("var", override)
            key = cmd + self.transpose
            if not exec_cmd:
                return 0
            key = min(max(key, 0), 127)
            if not self.mute and do_note_on:
                self.note_on(key, velocity, length if length > 0 else -1, self.tie)
            if self.note_wait:
                self.wait = length
                if length == 0:
                    self.note_finish_wait = True
            return 0

        group = cmd & 0xF0
        if group == 0x80:
            if cmd == 0x80:
                t = self._arg("var", override)
                if exec_cmd:
                    self.wait = t
            elif cmd == 0x81:
                a = self._arg("var", override)
                if exec_cmd and a < 0x10000:
                    self.prg = a & 0xFFFF
            elif cmd == 0x88:
                no = self._byte()
                off = self._u24()
                if exec_cmd:
                    p.open_track(no, off, self)
            elif cmd == 0x89:
                off = self._u24()
                if exec_cmd:
                    if off <= self.addr:
                        self.jumps_back += 1
                    self.addr = off
            elif cmd == 0x8A:
                off = self._u24()
                if exec_cmd and len(self.call_stack) < 3:
                    self.call_stack.append(self.addr)
                    self.loop_count.append(0)
                    self.addr = off
            else:
                p.unknown.add(cmd)
            return 0

        if group in (0xB0, 0xC0, 0xD0):
            a = self._arg("u8", override) & 0xFF
            if exec_cmd:
                self._command(cmd, a)
            return 0

        if group == 0x90:
            p.unknown.add(cmd)
            return 0

        if group == 0xE0:
            a = self._arg("s16", override)
            a = ((a + 0x8000) & 0xFFFF) - 0x8000
            if exec_cmd:
                if cmd == 0xE0:
                    self.lfo.delay = a * 5
                elif cmd == 0xE1:
                    p.tempo = a
                elif cmd == 0xE3:
                    self.sweep_pitch = a / 32.0
                else:
                    p.unknown.add(cmd)
            return 0

        if group == 0xF0:
            if cmd == 0xFE:
                self._u16()
            elif cmd == 0xFF:
                return -1
            elif cmd == 0xFD:
                if exec_cmd and self.call_stack:
                    self.addr = self.call_stack.pop()
                    self.loop_count.pop()
            elif cmd == 0xFC:
                if exec_cmd and self.call_stack:
                    count = self.loop_count[-1]
                    if count != 0:
                        count -= 1
                        if count == 0:
                            self.call_stack.pop()
                            self.loop_count.pop()
                            return 0
                    else:
                        self.jumps_back += 1  # infinite loop
                    self.loop_count[-1] = count
                    self.addr = self.call_stack[-1]
            elif cmd == 0xF0:
                ex = self._byte()
                if ex & 0xF0 == 0xE0:  # userproc
                    self._arg("s16", override)
                elif ex & 0xF0 in (0x80, 0x90):
                    var = self._byte()
                    val = self._arg("s16", override)
                    val = ((val + 0x8000) & 0xFFFF) - 0x8000
                    if exec_cmd:
                        self._ex_command(ex, var, val)
                else:
                    p.unknown.add(0xF000 | ex)
            else:
                p.unknown.add(cmd)
            return 0
        p.unknown.add(cmd)
        return 0

    def _command(self, cmd: int, a: int) -> None:
        p = self.player
        s8 = a - 256 if a >= 128 else a
        if cmd == 0xB0:
            p.timebase = a
        elif cmd == 0xC0:
            self.pan = a - 64
        elif cmd == 0xC1:
            self.volume = a
        elif cmd == 0xC2:
            p.main_volume = a
        elif cmd == 0xC3:
            self.transpose = s8
        elif cmd == 0xC4:
            self.pitch_bend = s8
        elif cmd == 0xC5:
            self.bend_range = a
        elif cmd == 0xC6:
            self.priority = a
        elif cmd == 0xC7:
            self.note_wait = bool(a)
        elif cmd == 0xC8:
            self.tie = bool(a)
            self.release_all(-1)
            self.free_all()
        elif cmd == 0xC9:
            self.porta_key = a + self.transpose
            self.porta_flag = True
        elif cmd == 0xCA:
            self.lfo.depth = a / 128.0
        elif cmd == 0xCB:
            self.lfo.speed = a * (100.0 / 256.0)
        elif cmd == 0xCC:
            self.lfo_target = a
        elif cmd == 0xCD:
            self.lfo.range = a
        elif cmd == 0xCE:
            self.porta_flag = a != 0
        elif cmd == 0xCF:
            self.porta_time = a
        elif cmd == 0xD0:
            self.attack = a
        elif cmd == 0xD1:
            self.decay = a
        elif cmd == 0xD2:
            self.sustain = a
        elif cmd == 0xD3:
            self.release = a
        elif cmd == 0xD4:
            if len(self.call_stack) < 3:
                self.call_stack.append(self.addr)
                self.loop_count.append(a)
        elif cmd == 0xD5:
            self.volume2 = a
        elif cmd == 0xD6:
            pass  # printvar
        elif cmd == 0xD7:
            self.surround_pan = a
        elif cmd == 0xD8:
            self.lpf_freq = a
        elif cmd == 0xD9:
            self.fx_send[0] = a
        elif cmd == 0xDA:
            self.fx_send[1] = a
        elif cmd == 0xDB:
            self.main_send = a
        elif cmd == 0xDC:
            self.init_pan = a - 64
        elif cmd == 0xDD:
            if a == 0:
                self.mute = False
            elif a == 1:  # stop
                for ch in self.channels:
                    ch.active = False
                    ch.track = None
                self.channels = []
                self.mute = True
            elif a == 2:  # release
                self.release_all(-1)
                self.free_all()
                self.mute = True
            else:
                self.mute = True
        elif cmd == 0xDE:
            self.fx_send[2] = a
        elif cmd == 0xDF:
            self.damper = a >= 64
        else:
            p.unknown.add(cmd)

    def _ex_command(self, ex: int, var: int, val: int) -> None:
        p = self.player
        cur = p.get_var(self, var)
        if cur is None:
            return
        res = None
        if ex == 0x80:
            res = val
        elif ex == 0x81:
            res = cur + val
        elif ex == 0x82:
            res = cur - val
        elif ex == 0x83:
            res = cur * val
        elif ex == 0x84:
            res = int(cur / val) if val else cur
        elif ex == 0x85:
            res = cur << val if val >= 0 else cur >> -val
        elif ex == 0x86:
            neg = val < 0
            r = (p.rand.next() * (abs(val) + 1)) >> 16
            res = -r if neg else r
        elif ex == 0x87:
            res = cur & val
        elif ex == 0x88:
            res = cur | val
        elif ex == 0x89:
            res = cur ^ val
        elif ex == 0x8A:
            res = ~(val & 0xFFFF)
        elif ex == 0x8B:
            res = int(math.fmod(cur, val)) if val else cur
        elif ex == 0x90:
            self.cmp_flag = cur == val
        elif ex == 0x91:
            self.cmp_flag = cur >= val
        elif ex == 0x92:
            self.cmp_flag = cur > val
        elif ex == 0x93:
            self.cmp_flag = cur <= val
        elif ex == 0x94:
            self.cmp_flag = cur < val
        elif ex == 0x95:
            self.cmp_flag = cur != val
        else:
            p.unknown.add(0xF000 | ex)
        if res is not None:
            p.set_var(self, var, ((res + 0x8000) & 0xFFFF) - 0x8000)

    # -- notes --------------------------------------------------------------
    def note_on(self, key: int, velocity: int, length: int, tie: bool) -> None:
        p = self.player
        ch = None
        if tie and self.channels:
            ch = self.channels[-1]
            ch.key = key
            iv = velocity / 127.0
            ch.init_volume = iv * iv * ch.inst_volume
        if ch is None:
            ch = p.bank_note_on(self, key, velocity, -1 if tie else length)
            if ch is None:
                return
            ch.track = self
            self.channels.append(ch)
        if self.attack != 0xFF:
            ch.set_attack(self.attack)
        if self.decay != 0xFF:
            ch.set_decay(self.decay)
        if self.sustain != 0xFF:
            ch.set_sustain(self.sustain)
        if self.release != 0xFF:
            ch.set_release(self.release)
        sweep = self.sweep_pitch
        if self.porta_flag:
            sweep += self.porta_key - key
        if self.porta_time == 0:
            ch.set_sweep(sweep, length, False)
        else:
            t = self.porta_time * self.porta_time
            t = int(t * abs(sweep))
            t >>= 5
            t = (t << 2) + t
            ch.set_sweep(sweep, t, True)
        self.porta_key = key


class SeqPlayer:
    def __init__(self, seq: bytes, start: int, bank: Rbnk, volume: float = 1.0,
                 pan_curve: int = 0, pan_mode: int = 0, seed: int = 0x12345678):
        self.seq = seq
        self.bank = bank
        self.volume = volume
        self.pan_curve = pan_curve
        self.pan_mode = pan_mode
        self.tempo = 120
        self.timebase = 48
        self.main_volume = 127
        self.tick_fraction = 0.0
        self.local_vars = [-1] * 16
        self.global_vars = [-1] * 16
        self.rand = Random(seed)
        self.tracks: List[Optional[Track]] = [Track(self, i) for i in range(16)]
        self.channels: List[Channel] = []
        self.active = True
        self.frame = 0
        self.unknown = set()
        self.warnings = set()
        self.missing_notes = 0
        self.all_channels: List[Channel] = []
        t0 = self.tracks[0]
        t0.addr = start
        t0.open = True

    def get_var(self, track: Track, idx: int) -> Optional[int]:
        if idx < 16:
            return self.local_vars[idx]
        if idx < 32:
            return self.global_vars[idx - 16]
        if idx < 48:
            return track.variables[idx - 32]
        return None

    def set_var(self, track: Track, idx: int, v: int) -> None:
        if idx < 16:
            self.local_vars[idx] = v
        elif idx < 32:
            self.global_vars[idx - 16] = v
        elif idx < 48:
            track.variables[idx - 32] = v

    def open_track(self, no: int, offset: int, caller: Track) -> None:
        if no >= 16:
            return
        t = self.tracks[no]
        if t is None or t is caller:
            return
        t.close()
        nt = Track(self, no)
        nt.addr = offset
        nt.open = True
        self.tracks[no] = nt

    def bank_note_on(self, track: Track, key: int, velocity: int, length: int) -> Optional[Channel]:
        inst = self.bank.inst(track.prg, key, velocity)
        if inst is None:
            self.missing_notes += 1
            return None
        wave = self.bank.wave(inst.wave_index)
        if wave is None or wave.loop_end <= 0:
            self.missing_notes += 1
            return None
        ch = Channel(wave, self.frame, length, self.pan_curve, self.pan_mode)
        ch.key = key
        ch.original_key = inst.original_key
        iv = velocity / 127.0
        ch.inst_volume = inst.volume / 127.0
        ch.init_volume = iv * iv * ch.inst_volume
        ch.tune = inst.tune
        ch.set_adsr(inst.attack, inst.decay, inst.sustain, inst.release)
        ch.init_pan = (inst.pan - 64) / 63.0 + track.init_pan / 63.0
        self.channels.append(ch)
        self.all_channels.append(ch)
        return ch

    # -- ticks -----------------------------------------------------------------
    def base_tempo(self) -> float:
        return self.timebase * self.tempo / 60000.0

    def parse_next_tick(self) -> bool:
        """Returns True when no track is open any more."""
        any_open = False
        for i, t in enumerate(self.tracks):
            if t is None:
                continue
            t.update_channel_length()
            if t.parse_next_tick(True) < 0:
                t.close()
            if t.open:
                any_open = True
        return not any_open

    def update_tick(self, msec: int) -> None:
        tpm = self.base_tempo()
        if tpm == 0.0:
            return
        rest = float(msec)
        nxt = self.tick_fraction / tpm
        while nxt < rest:
            rest -= nxt
            if self.parse_next_tick():
                self.finish()
                return
            tpm = self.base_tempo()
            if tpm == 0.0:
                return
            nxt = 1.0 / tpm
        nxt -= rest
        self.tick_fraction = nxt * tpm

    def finish(self) -> None:
        for t in self.tracks:
            if t is not None and t.open:
                t.close()
        self.active = False

    def update(self) -> None:
        if self.active:
            self.update_tick(FRAME_MS)
        for t in self.tracks:
            if t is not None:
                t.update_channel_param()

    def loops_done(self, loops: int) -> bool:
        """True once the looping tracks have each looped ``loops`` times.

        A track that has not looped yet but waits on a note that never stops
        (it will never loop) does not hold the others back.
        """
        open_tracks = [t for t in self.tracks if t is not None and t.open]
        return any(t.jumps_back >= loops for t in open_tracks) and \
            all(t.jumps_back >= loops or t.note_finish_wait for t in open_tracks)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@dataclass
class RenderResult:
    samples: np.ndarray            # (2, n) float64, nominal range -1..1
    sample_rate: int = OUTPUT_RATE
    loop_stopped: bool = False     # stopped after N passes of a looping sequence
    capped: bool = False           # hit the maximum duration (faded out)
    warnings: List[str] = field(default_factory=list)


def _mix(channels: List[Channel], total_frames: int) -> np.ndarray:
    out = np.zeros((2, total_frames * FRAME_SAMPLES + FRAME_SAMPLES))
    for ch in channels:
        r = ch.render()
        if r is None:
            continue
        a = ch.start_frame * FRAME_SAMPLES
        b = min(a + r.shape[1], out.shape[1])
        out[:, a:b] += r[:, :b - a]
    return out


def _trim(out: np.ndarray) -> np.ndarray:
    nz = np.nonzero(np.max(np.abs(out), axis=0) > 1e-6)[0]
    if len(nz) == 0:
        return out[:, :FRAME_SAMPLES]
    return out[:, :nz[-1] + 1]


def render_sequence(seq: bytes, start: int, bank: Rbnk, volume: float = 1.0, pan_curve: int = 0,
                    pan_mode: int = 0, loops: int = 2, loop_min_seconds: float = 5.0,
                    max_seconds: float = 20.0, fade_seconds: float = 2.0,
                    seed: int = 0x12345678, safety_seconds: float = 600.0) -> RenderResult:
    """Play a sequence from ``start`` and return the mixed stereo output.

    Looping sequences are stopped (all notes released, like the game stopping
    the sound) once every open track has looped ``loops`` times and at least
    ``loop_min_seconds`` have been rendered.

    A sequence can also *stall*: every track has ended or waits forever on a
    note that never stops (typically an ambience holding a looped sample).
    Such a sound is kept for ``max_seconds`` of stall and cut with a
    ``fade_seconds`` fade-out.  A sequence that is still progressing (music)
    is never cut that way; ``safety_seconds`` only guards against bugs.
    """
    p = SeqPlayer(seq, start, bank, volume, pan_curve, pan_mode, seed)
    max_frames = int(max_seconds * 1000 / FRAME_MS)
    safety_frames = int(safety_seconds * 1000 / FRAME_MS)
    stall_frames = 0
    loop_stopped = capped = False
    while True:
        p.update()
        for ch in list(p.channels):
            ch.update()
        p.channels = [c for c in p.channels if c.active]
        p.frame += 1
        if (p.active and loops > 0 and p.loops_done(loops)
                and p.frame * FRAME_MS >= loop_min_seconds * 1000):
            p.finish()  # like SoundHandle::Stop(): release every note
            loop_stopped = True
        if not p.active and not p.channels:
            break
        open_tracks = [t for t in p.tracks if t is not None and t.open]
        if not open_tracks or all(t.note_finish_wait for t in open_tracks):
            stall_frames += 1  # consecutive frames without any track progressing
        else:
            stall_frames = 0
        if stall_frames >= max_frames or p.frame >= safety_frames:
            capped = True
            break
    out = _mix(p.all_channels, p.frame)
    if capped:
        out = out[:, :p.frame * FRAME_SAMPLES]
        nf = min(int(fade_seconds * OUTPUT_RATE), out.shape[1])
        if nf > 0:
            out[:, -nf:] *= np.linspace(1.0, 0.0, nf)
    else:
        out = _trim(out)
    warns = sorted(p.warnings)
    if p.unknown:
        warns.append("unknown commands: " + ", ".join(f"0x{c:X}" for c in sorted(p.unknown)))
    if p.missing_notes:
        warns.append(f"{p.missing_notes} note(s) without instrument")
    return RenderResult(out, OUTPUT_RATE, loop_stopped, capped, warns)


def render_wsd(rwsd: Rwsd, index: int, volume: float = 1.0, pan_curve: int = 0, pan_mode: int = 0,
               max_seconds: float = 20.0, fade_seconds: float = 2.0) -> RenderResult:
    snd = rwsd.sounds[index]
    chans: List[Channel] = []
    events = snd.events or []
    for ev in events[:1] if events else []:
        note = snd.notes[ev.note_index]
        wave = rwsd.rwar.get(note.wave_index)
        if wave is None:
            continue
        ch = Channel(wave, 0, -1, pan_curve, pan_mode)
        ch.set_adsr(note.attack, note.decay, note.sustain, note.release)
        ch.key = ch.original_key = 60
        ch.user_volume = volume
        ch.user_pitch_ratio = snd.pitch
        ch.user_pan = ((snd.pan - 63) if snd.pan <= 1 else (snd.pan - 64)) / 63.0
        ch.main_send = snd.main_send / 127.0 - 1.0
        chans.append(ch)
    max_frames = int(max_seconds * 1000 / FRAME_MS)
    frame = 0
    capped = False
    live = list(chans)
    while live:
        for ch in live:
            ch.update()
        live = [c for c in live if c.active]
        frame += 1
        if frame >= max_frames:
            capped = True
            break
    out = _mix(chans, frame)
    if capped:
        out = out[:, :frame * FRAME_SAMPLES]
        nf = min(int(fade_seconds * OUTPUT_RATE), out.shape[1])
        out[:, -nf:] *= np.linspace(1.0, 0.0, nf)
    else:
        out = _trim(out)
    return RenderResult(out, OUTPUT_RATE, False, capped, [])
