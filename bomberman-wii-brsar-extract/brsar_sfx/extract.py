"""High level extraction: BRSAR in, audio files + manifest out."""

from __future__ import annotations

import csv
import json
import multiprocessing as mp
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import dsp
from .categories import folder_for
from .formats import Rbnk, Rseq, Rwar, Rwsd
from .player import OUTPUT_RATE, RenderResult, render_sequence, render_wsd
from .rsar import SOUND_TYPE_SEQ, SOUND_TYPE_STRM, SOUND_TYPE_WAVE, FormatError, Rsar, SoundEntry
from .writers import ADPCM_BLOCK_SAMPLES, build_brstm


@dataclass
class Options:
    codec: str = "pcm16"          # "pcm16" (lossless, default) or "adpcm" (small, lossy)
    loops: int = 2
    loop_min_seconds: float = 5.0
    max_seconds: float = 20.0
    fade_seconds: float = 2.0
    normalize: bool = True
    force_stereo: bool = False
    flat: bool = False
    seed: int = 0x12345678
    jobs: int = 0


@dataclass
class Rendered:
    sound: SoundEntry
    folder: str
    pcm: Optional[np.ndarray] = None   # int16 (channels, n)
    gain: float = 1.0
    peak: float = 0.0
    loop_stopped: bool = False
    capped: bool = False
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# sound selection
# ---------------------------------------------------------------------------

def select_sounds(rsar: Rsar, include: Optional[str] = None,
                  exclude: Optional[str] = None) -> List[SoundEntry]:
    """Every sound of the archive (sound effects, jingles and music), optionally filtered."""
    sounds = list(rsar.sounds)
    if include:
        rx = re.compile(include, re.I)
        sounds = [s for s in sounds if rx.search(s.name)]
    if exclude:
        rx = re.compile(exclude, re.I)
        sounds = [s for s in sounds if not rx.search(s.name)]
    return sounds


# ---------------------------------------------------------------------------
# rendering (runs in worker processes)
# ---------------------------------------------------------------------------

_W: Dict[str, object] = {}


def _worker_init(path: str, opts: Options) -> None:
    with open(path, "rb") as f:
        _W["rsar"] = Rsar(f.read())
    _W["opts"] = opts
    _W["banks"] = {}
    _W["rwsd"] = {}


def _bank(rsar: Rsar, bank_id: int) -> Rbnk:
    cache = _W["banks"]
    if bank_id not in cache:
        data, wave = rsar.get_file(rsar.banks[bank_id].file_id)
        cache[bank_id] = Rbnk(data, Rwar(wave))
    return cache[bank_id]


def render_sound(rsar: Rsar, s: SoundEntry, opts: Options) -> RenderResult:
    vol = s.volume / 127.0
    if s.sound_type == SOUND_TYPE_SEQ:
        data, _ = rsar.get_file(s.file_id)
        seq = Rseq(data)
        bank = _bank(rsar, s.bank_id)
        return render_sequence(seq.seq, s.seq_offset, bank, vol, s.pan_curve, s.pan_mode,
                               loops=opts.loops, loop_min_seconds=opts.loop_min_seconds,
                               max_seconds=opts.max_seconds, fade_seconds=opts.fade_seconds,
                               seed=opts.seed)
    if s.sound_type == SOUND_TYPE_WAVE:
        cache = _W["rwsd"]
        if s.file_id not in cache:
            data, wave = rsar.get_file(s.file_id)
            cache[s.file_id] = Rwsd(data, Rwar(wave))
        return render_wsd(cache[s.file_id], s.wsd_index, vol, s.pan_curve, s.pan_mode,
                          max_seconds=opts.max_seconds, fade_seconds=opts.fade_seconds)
    raise FormatError("stream sounds (STRM) are external .brstm files, not inside the BRSAR")


def _render_job(args):
    index, folder = args
    rsar: Rsar = _W["rsar"]
    opts: Options = _W["opts"]
    s = rsar.sounds[index]
    out = Rendered(s, folder)
    try:
        r = render_sound(rsar, s, opts)
    except Exception as e:  # keep going with the other sounds
        out.error = f"{type(e).__name__}: {e}"
        return out
    x = r.samples
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    out.peak = peak
    if peak > 1.0:
        if opts.normalize:
            out.gain = 0.999 / peak
            x = x * out.gain
        else:
            x = np.clip(x, -1.0, 1.0)
    pcm = np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int16)
    nz = np.nonzero(np.any(pcm != 0, axis=0))[0]
    if len(nz) and not r.capped:
        pcm = pcm[:, :nz[-1] + 1]  # drop the inaudible (all-zero) tail
    if not opts.force_stereo and np.array_equal(pcm[0], pcm[1]):
        pcm = pcm[:1]
    out.pcm = pcm
    out.loop_stopped = r.loop_stopped
    out.capped = r.capped
    out.warnings = r.warnings
    return out


def _encode_job(streams):
    return dsp.encode_many(streams, block_samples=ADPCM_BLOCK_SAMPLES, lanes=len(streams))


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)


def extract(path: str, out_dir: str, sounds: List[SoundEntry], rsar: Rsar, opts: Options,
            log=print) -> List[Rendered]:
    t0 = time.time()
    names = {s.name for s in rsar.sounds}
    jobs = []
    for s in sounds:
        player = rsar.players[s.player_id] if s.player_id < len(rsar.players) else None
        folder = "" if opts.flat else folder_for(s.name, player, names)
        jobs.append((s.index, folder))

    nproc = opts.jobs or max(1, min(os.cpu_count() or 1, 8))
    ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else mp.get_context()
    results: List[Rendered] = []
    log(f"Rendering {len(jobs)} sounds with {nproc} process(es)...")
    if nproc > 1:
        with ctx.Pool(nproc, initializer=_worker_init, initargs=(path, opts)) as pool:
            for i, r in enumerate(pool.imap(_render_job, jobs, chunksize=1), 1):
                results.append(r)
                _progress(log, i, len(jobs))
    else:
        _worker_init(path, opts)
        for i, j in enumerate(jobs, 1):
            results.append(_render_job(j))
            _progress(log, i, len(jobs))
    log(f"  rendered in {time.time() - t0:.1f}s")

    ok = [r for r in results if r.pcm is not None]
    encoded: Dict[int, list] = {}
    if opts.codec == "adpcm" and ok:
        t1 = time.time()
        streams = []
        for ri, r in enumerate(ok):
            for c in range(r.pcm.shape[0]):
                streams.append((ri, c, r.pcm[c]))
        streams.sort(key=lambda t: len(t[2]))
        lanes = 64
        batches = [streams[i:i + lanes] for i in range(0, len(streams), lanes)]
        # longest batches first for better load balancing
        batches.sort(key=lambda b: -len(b[-1][2]))
        log(f"Encoding {len(streams)} channel(s) to DSP-ADPCM...")
        payload = [[t[2] for t in b] for b in batches]
        if nproc > 1:
            with ctx.Pool(nproc) as pool:
                enc_batches = pool.map(_encode_job, payload, chunksize=1)
        else:
            enc_batches = [_encode_job(p) for p in payload]
        for b, eb in zip(batches, enc_batches):
            for (ri, c, _), e in zip(b, eb):
                encoded.setdefault(ri, [None, None])[c] = e
        log(f"  encoded in {time.time() - t1:.1f}s")

    os.makedirs(out_dir, exist_ok=True)
    for ri, r in enumerate(ok):
        if opts.codec == "adpcm":
            blob = build_brstm(OUTPUT_RATE, adpcm=[e for e in encoded[ri] if e is not None])
        else:
            blob = build_brstm(OUTPUT_RATE, pcm16=r.pcm)
        d = os.path.join(out_dir, r.folder) if r.folder else out_dir
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, _safe(r.sound.name) + ".brstm"), "wb") as f:
            f.write(blob)

    _write_manifest(out_dir, results, opts)
    for r in results:
        if r.error:
            log(f"  ! {r.sound.name}: {r.error}")
    log(f"Done: {len(ok)}/{len(results)} sounds written to {out_dir} in {time.time() - t0:.1f}s")
    return results


def _progress(log, i, n):
    if i == n or i % 25 == 0:
        log(f"  {i}/{n}")


def _write_manifest(out_dir: str, results: List[Rendered], opts: Options) -> None:
    rows = []
    for r in results:
        s = r.sound
        rows.append({
            "name": s.name,
            "folder": r.folder,
            "type": s.type_name,
            "channels": int(r.pcm.shape[0]) if r.pcm is not None else 0,
            "seconds": round(r.pcm.shape[1] / OUTPUT_RATE, 3) if r.pcm is not None else 0,
            "volume": s.volume,
            "looped": r.loop_stopped,
            "capped": r.capped,
            "normalized_gain_db": round(20 * np.log10(r.gain), 2) if r.gain != 1.0 else 0.0,
            "notes": "; ".join(r.warnings + ([r.error] if r.error else [])),
        })
    with open(os.path.join(out_dir, "manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name"])
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({
            "sample_rate": OUTPUT_RATE,
            "codec": opts.codec,
            "loops": opts.loops,
            "loop_min_seconds": opts.loop_min_seconds,
            "max_seconds": opts.max_seconds,
            "fade_seconds": opts.fade_seconds,
            "normalize": opts.normalize,
            "seed": opts.seed,
        }, f, indent=2)


# ---------------------------------------------------------------------------
# raw native files
# ---------------------------------------------------------------------------

EXT = {b"RSEQ": ".brseq", b"RBNK": ".brbnk", b"RWSD": ".brwsd", b"RWAR": ".brwar", b"RSTM": ".brstm"}


def dump_raw(rsar: Rsar, out_dir: str, log=print) -> None:
    """Write every sub-file of the archive in its native format, plus an index."""
    os.makedirs(out_dir, exist_ok=True)
    names: Dict[int, List[str]] = {}
    for b in rsar.banks:
        names.setdefault(b.file_id, []).append(b.name)
    for s in rsar.sounds:
        names.setdefault(s.file_id, []).append(s.name)
    index = []
    count = 0
    for fe in rsar.files:
        if not rsar.has_file(fe.index):
            index.append({"file_id": fe.index, "external": fe.external_name})
            continue
        data, wave = rsar.get_file(fe.index)
        kind = bytes(data[:4])
        label = names.get(fe.index, [])
        stem = f"{fe.index:04d}_{_safe(label[0]) if len(label) == 1 else kind.decode('ascii', 'replace')}"
        fn = stem + EXT.get(kind, ".bin")
        with open(os.path.join(out_dir, fn), "wb") as f:
            f.write(data)
        entry = {"file_id": fe.index, "file": fn, "type": kind.decode("ascii", "replace"),
                 "groups": rsar.file_groups(fe.index), "used_by": label}
        if wave:
            wn = stem + ".brwar"
            with open(os.path.join(out_dir, wn), "wb") as f:
                f.write(wave)
            entry["wave_archive"] = wn
        index.append(entry)
        count += 1
    sounds = []
    for s in rsar.sounds:
        e = {"name": s.name, "type": s.type_name, "file_id": s.file_id, "volume": s.volume,
             "player": rsar.players[s.player_id] if s.player_id < len(rsar.players) else s.player_id}
        if s.sound_type == SOUND_TYPE_SEQ:
            e.update(seq_offset=s.seq_offset, bank=rsar.banks[s.bank_id].name if s.bank_id < len(rsar.banks) else s.bank_id,
                     bank_file_id=rsar.banks[s.bank_id].file_id if s.bank_id < len(rsar.banks) else None)
        elif s.sound_type == SOUND_TYPE_WAVE:
            e.update(wsd_index=s.wsd_index)
        sounds.append(e)
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"files": index, "sounds": sounds}, f, indent=1)
    log(f"Wrote {count} native files + index.json to {out_dir}")
