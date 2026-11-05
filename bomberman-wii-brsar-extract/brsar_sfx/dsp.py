"""Nintendo GameCube/Wii DSP-ADPCM codec.

DSP-ADPCM stores audio in 8-byte frames of 14 samples: one header byte
(``predictor_index << 4 | scale``) followed by 14 signed 4-bit residuals.
Each stream has a table of 8 second-order predictor coefficient pairs
(4.11 fixed point).

* :func:`decode` is a straightforward reference decoder.
* :func:`encode_many` is an encoder written for numpy: the sample-by-sample
  recursion cannot be vectorised along time, so it is vectorised *across
  streams* instead (every stream is a "lane" and all lanes advance one frame at
  a time), with an exhaustive search over the 8 predictors and the 3 best
  scales for every frame.  This keeps pure Python fast enough for hundreds of
  files without needing a C extension.
* :func:`compute_coefs` designs the 8 predictors of a stream with a Lloyd-style
  clustering of the per-frame optimal 2nd-order linear predictors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

SAMPLES_PER_FRAME = 14
BYTES_PER_FRAME = 8


def nibble_to_sample(nibble_addr: int) -> int:
    """Convert a DSP nibble address (as stored in loop points) to a sample index."""
    return (nibble_addr // 16) * 14 + (nibble_addr % 16) - 2


def decode(data: bytes, offset: int, num_samples: int, coefs: Sequence[int],
           hist1: int = 0, hist2: int = 0) -> np.ndarray:
    """Decode ``num_samples`` DSP-ADPCM samples starting at byte ``offset``."""
    out = [0] * num_samples
    c = list(coefs)
    pos = offset
    n = 0
    h1, h2 = hist1, hist2
    end = len(data)
    while n < num_samples and pos < end:
        header = data[pos]
        scale = 1 << (header & 0xF)
        ci = (header >> 4) & 7
        c1 = c[ci * 2]
        c2 = c[ci * 2 + 1]
        for i in range(14):
            if n >= num_samples:
                break
            byte = data[pos + 1 + (i >> 1)] if pos + 1 + (i >> 1) < end else 0
            nib = (byte >> 4) if (i & 1) == 0 else (byte & 0xF)
            if nib >= 8:
                nib -= 16
            s = (((nib * scale) << 11) + 1024 + c1 * h1 + c2 * h2) >> 11
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            out[n] = s
            h2 = h1
            h1 = s
            n += 1
        pos += 8
    return np.asarray(out, dtype=np.int16)


# ---------------------------------------------------------------------------
# Coefficient design
# ---------------------------------------------------------------------------

def _frame_stats(x: np.ndarray):
    """Per-frame autocorrelation sums for 2nd-order prediction."""
    x = x.astype(np.float64)
    n = len(x)
    nf = (n + 13) // 14
    padded = np.zeros(nf * 14 + 2)
    padded[2:2 + n] = x
    idx = np.arange(nf)[:, None] * 14 + np.arange(14)[None, :] + 2
    x0 = padded[idx]
    x1 = padded[idx - 1]
    x2 = padded[idx - 2]
    return (np.sum(x0 * x0, 1), np.sum(x0 * x1, 1), np.sum(x0 * x2, 1),
            np.sum(x1 * x1, 1), np.sum(x1 * x2, 1), np.sum(x2 * x2, 1))


def _solve(r01, r02, r11, r12, r22):
    det = r11 * r22 - r12 * r12
    ok = np.abs(det) > 1e-9 * np.maximum(r11 * r22, 1.0)
    det_safe = np.where(ok, det, 1.0)
    a = np.where(ok, (r01 * r22 - r02 * r12) / det_safe, np.where(r11 > 0, r01 / np.maximum(r11, 1e-12), 0.0))
    b = np.where(ok, (r02 * r11 - r01 * r12) / det_safe, 0.0)
    return a, b


def _stabilise(a, b):
    """Keep the predictor strictly stable (poles inside radius ~0.985).

    Nintendo's own encoder sometimes produces marginally stable pairs such as
    (2.0, -1.0); they are exact on hardware, but decoders that round slightly
    differently (e.g. ffmpeg) then drift. A small margin avoids that at a
    negligible cost in quality.
    """
    b = np.clip(b, -0.97, 0.97)
    lim = 0.985 * (1.0 - b)
    a = np.clip(a, -lim, lim)
    return a, b


def compute_coefs(x: np.ndarray, iterations: int = 12) -> np.ndarray:
    """Design 8 predictor pairs for ``x`` (int16). Returns int array of 16 values."""
    r00, r01, r02, r11, r12, r22 = _frame_stats(x)
    active = r00 > 0
    if np.count_nonzero(active) == 0:
        return np.array([0, 0, 2048, 0, 4096, -2048, 0, 0, 1024, 0, 3072, -1024, 3584, -1536, 1536, 0], dtype=np.int64)
    r00, r01, r02, r11, r12, r22 = (v[active] for v in (r00, r01, r02, r11, r12, r22))

    def err(a, b):
        # residual energy of every frame (rows) under every predictor (columns)
        return (r00[:, None] - 2 * a[None] * r01[:, None] - 2 * b[None] * r02[:, None]
                + a[None] ** 2 * r11[:, None] + 2 * a[None] * b[None] * r12[:, None]
                + b[None] ** 2 * r22[:, None])

    fa, fb = _stabilise(*_solve(r01, r02, r11, r12, r22))
    # initial centres: spread over the frames sorted by predictor "shape"
    order = np.argsort(fa + 0.5 * fb)
    picks = order[np.linspace(0, len(order) - 1, 8).astype(int)]
    a = fa[picks].copy()
    b = fb[picks].copy()
    # always keep a "no prediction" option and a simple first-order option nearby
    a[0], b[0] = 0.0, 0.0
    for _ in range(iterations):
        assign = np.argmin(err(a, b), axis=1)
        for k in range(1, 8):
            m = assign == k
            if not np.any(m):
                # re-seed an empty cluster with the worst-predicted frame
                e = err(a, b)[np.arange(len(assign)), assign]
                j = int(np.argmax(e))
                a[k], b[k] = fa[j], fb[j]
                continue
            ak, bk = _solve(r01[m].sum(), r02[m].sum(), r11[m].sum(), r12[m].sum(), r22[m].sum())
            ak, bk = _stabilise(np.asarray(ak), np.asarray(bk))
            a[k], b[k] = float(ak), float(bk)
    coefs = np.empty(16, dtype=np.int64)
    coefs[0::2] = np.clip(np.round(a * 2048), -32768, 32767)
    coefs[1::2] = np.clip(np.round(b * 2048), -32768, 32767)
    return coefs


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

@dataclass
class EncodedStream:
    data: bytes            # raw DSP-ADPCM frames
    coefs: np.ndarray      # 16 ints
    num_samples: int
    initial_ps: int        # header byte of the first frame
    block_history: List[tuple]  # (hist1, hist2) at the start of each block


def encode_many(streams: Sequence[np.ndarray], coefs_list: Optional[Sequence[np.ndarray]] = None,
                block_samples: int = 0x3800, lanes: int = 192) -> List[EncodedStream]:
    """Encode several int16 streams. ``block_samples`` controls where the decoder
    history is recorded (used by the BRSTM ADPC table)."""
    streams = [np.asarray(s, dtype=np.int16) for s in streams]
    if coefs_list is None:
        coefs_list = [compute_coefs(s) for s in streams]
    results: List[Optional[EncodedStream]] = [None] * len(streams)
    order = sorted(range(len(streams)), key=lambda i: len(streams[i]))
    for start in range(0, len(order), lanes):
        batch = order[start:start + lanes]
        out = _encode_batch([streams[i] for i in batch], [coefs_list[i] for i in batch], block_samples)
        for i, r in zip(batch, out):
            results[i] = r
    return results  # type: ignore[return-value]


def _encode_batch(streams, coefs_list, block_samples) -> List[EncodedStream]:
    L = len(streams)
    lengths = np.array([len(s) for s in streams])
    nframes = (lengths + 13) // 14
    maxf = int(nframes.max()) if L else 0
    X = np.zeros((L, max(maxf, 1) * 14), dtype=np.int64)
    for i, s in enumerate(streams):
        X[i, :len(s)] = s
    C = np.stack([np.asarray(c, dtype=np.int64).reshape(8, 2) for c in coefs_list])  # (L,8,2)
    c1 = C[:, :, 0][:, :, None]  # (L,8,1)
    c2 = C[:, :, 1][:, :, None]
    NS = 3                       # scale candidates per predictor
    h1 = np.zeros(L, dtype=np.int64)
    h2 = np.zeros(L, dtype=np.int64)
    frames_out = np.zeros((L, max(maxf, 1), 8), dtype=np.uint8)
    frames_per_block = block_samples // 14
    history = [[] for _ in range(L)]
    lane_idx = np.arange(L)
    log2_7 = np.log2(7.0)

    for f in range(maxf):
        if f % frames_per_block == 0:
            for i in range(L):
                if f < nframes[i]:
                    history[i].append((int(h1[i]), int(h2[i])))
        x = X[:, f * 14:(f + 1) * 14]  # (L,14)
        # --- estimate the scale from the unquantised prediction residual
        prev1 = np.concatenate([h1[:, None], x[:, :13]], axis=1)
        prev2 = np.concatenate([h2[:, None], h1[:, None], x[:, :12]], axis=1)
        resid = (x[:, None, :] * 2048 - c1 * prev1[:, None, :] - c2 * prev2[:, None, :]) / 2048.0  # (L,8,14)
        peak = np.abs(resid).max(axis=2)  # (L,8)
        with np.errstate(divide="ignore"):
            s0 = np.ceil(np.log2(np.maximum(peak, 1e-9)) - log2_7)
        s0 = np.clip(s0, 0, 12).astype(np.int64)
        scales = np.clip(s0[:, :, None] + np.array([-1, 0, 1])[None, None, :], 0, 12)  # (L,8,3)
        # --- exact simulation of every candidate
        sh1 = np.broadcast_to(h1[:, None, None], (L, 8, NS)).copy()
        sh2 = np.broadcast_to(h2[:, None, None], (L, 8, NS)).copy()
        step = (2048 << scales).astype(np.float64)
        err = np.zeros((L, 8, NS))
        nib = np.zeros((L, 8, NS, 14), dtype=np.int64)
        for k in range(14):
            pred = c1 * sh1 + c2 * sh2
            xk = x[:, k][:, None, None]
            n = np.rint((xk * 2048 - pred) / step)
            np.clip(n, -8, 7, out=n)
            n = n.astype(np.int64)
            dec = (((n << scales) << 11) + 1024 + pred) >> 11
            np.clip(dec, -32768, 32767, out=dec)
            d = dec - xk
            err += d * d
            nib[:, :, :, k] = n
            sh2 = sh1
            sh1 = dec
        flat = err.reshape(L, -1)
        best = np.argmin(flat, axis=1)
        bc, bs = np.divmod(best, NS)
        h1 = sh1[lane_idx, bc, bs]
        h2 = sh2[lane_idx, bc, bs]
        frames_out[:, f, 0] = (bc << 4) | scales[lane_idx, bc, bs]
        nb = nib[lane_idx, bc, bs] & 0xF
        frames_out[:, f, 1:] = (nb[:, 0::2] << 4) | nb[:, 1::2]

    out = []
    for i in range(L):
        nf = int(nframes[i])
        data = frames_out[i, :nf].tobytes()
        out.append(EncodedStream(data, np.asarray(coefs_list[i], dtype=np.int64), int(lengths[i]),
                                 int(frames_out[i, 0, 0]) if nf else 0, history[i]))
    return out
