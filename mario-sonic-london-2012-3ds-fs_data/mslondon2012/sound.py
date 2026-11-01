"""Step 2: sound banks. Pairs each ACB with its streamed AWB and lists every
cue with the waveforms it plays (for the report and the names.csv check).
Nothing is copied or converted: the waveforms stay inside the .acb / .awb."""
import os

from .acb import Acb, awb_entries, describe_stream_candidates, find_stream_awb
from .filetypes import guess_ext, safe


def job_acb(job):
    """Reads one ACB.

    Returns (n_listed, index_lines, problems, stream_folder, names) where names
    are the per-waveform names derived from the cues (Cue, Cue_Left/_Right for
    stereo pairs, Cue_01... for variations).
    """
    acb_path, raw_root = job
    problems, index = [], []
    rel = os.path.relpath(acb_path, raw_root)
    try:
        with open(acb_path, "rb") as f:
            acb = Acb(f.read())
    except Exception as e:
        return 0, index, ["%s: unreadable ACB (%s)" % (rel, e)], None, []

    mem = {}
    if acb.h.get("AwbFile"):
        try:
            mem = awb_entries(acb.h["AwbFile"])
        except Exception as e:
            problems.append("%s: unreadable embedded AWB (%s)" % (rel, e))

    stream, folder = {}, None
    need = {}
    for i, w in enumerate(acb.waves):
        is_stream, aid = acb.wave_ref(i)
        if is_stream:
            need[aid] = (w.get("SamplingRate"), w.get("NumChannels"), w.get("NumSamples"))
    stream_missing = False
    if need:
        stream, folder, err = find_stream_awb(acb_path, need)
        if stream is None:
            stream, stream_missing = {}, True
            problems.append("%s: %d streamed waveforms, no matching AWB folder found nearby"
                            " [%s]" % (rel, len(need), describe_stream_candidates(acb_path, need)))
        else:
            index.append("%s: streamed waveforms from %s%s"
                         % (rel, os.path.relpath(folder, raw_root),
                            " (sample counts %.1f%% off on average)" % (100 * err)
                            if err else ""))

    def wave_ext(wi):
        """Native extension of waveform wi (.bcwav / .adx), or None if missing."""
        is_stream, aid = acb.wave_ref(wi)
        src = stream.get(aid) if is_stream else mem.get(aid)
        if isinstance(src, str):
            with open(src, "rb") as f:
                src = f.read(0x40)
        if src is None:
            if not (is_stream and stream_missing):
                problems.append("%s: waveform %d (%s id %d) not found"
                                % (rel, wi, "stream" if is_stream else "memory", aid))
            return None
        return guess_ext(src)

    taken = set()
    names = []
    referenced = set()

    def unique(name):
        n, k = name, 2
        while n.lower() in taken:
            n = "%s_%d" % (name, k)
            k += 1
        taken.add(n.lower())
        return n

    def emit(name, wi, note):
        ext = wave_ext(wi)
        if ext is None:
            return
        names.append(name)
        w = acb.waves[wi]
        index.append("%s/%s%s: waveform %d, %d Hz, %d ch%s"
                     % (rel, name, ext, wi, w.get("SamplingRate") or 0,
                        w.get("NumChannels") or 0, note))

    for cue, leaves in acb.cue_list():
        seen, uniq = set(), []
        for wi, pan in leaves:
            if wi not in seen:
                seen.add(wi)
                uniq.append((wi, pan))
        referenced |= seen
        if not uniq:
            index.append("%s/%s: no waveform" % (rel, cue))
            continue
        name = unique(safe(cue))
        pair = (len(uniq) == 2 and uniq[0][1] is not None and uniq[1][1] is not None
                and uniq[0][1] * uniq[1][1] < 0)
        for k, (wi, pan) in enumerate(uniq, 1):
            if pair:
                suffix = "_Left" if pan < 0 else "_Right"
            elif len(uniq) > 1:
                suffix = "_%02d" % k
            else:
                suffix = ""
            emit(name + suffix, wi, ", pan %d" % pan if pan else "")

    for wi in range(len(acb.waves)):
        if wi not in referenced:
            emit(unique("_unreferenced_%03d" % wi), wi, ", not used by any cue")
    return len(names), index, problems, folder, names
