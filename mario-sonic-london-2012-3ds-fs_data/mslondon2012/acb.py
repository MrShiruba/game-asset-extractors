"""CRI ADX2 ACB sound banks (early 3DS version 0.81) and their AWB."""
import os
import re
import struct

from .cpk import cpk_entries_mem
from .utf import parse_utf, utf_rows


CMD_NOTE_ON = (2000, 2003)


CMD_PAN = 11


def parse_cmds(b):
    out, p = [], 0
    while b and p + 3 <= len(b):
        code, = struct.unpack_from(">H", b, p)
        sz = b[p + 2]
        out.append((code, b[p + 3:p + 3 + sz]))
        p += 3 + sz
    return out


class Acb:
    def __init__(self, data):
        _, _, rows = parse_utf(data)
        h = self.h = rows[0]
        g = lambda k: utf_rows(h.get(k))
        self.cues = g("CueTable")
        self.names = g("CueNameTable")
        self.waves = g("WaveformTable")
        self.synths = g("SynthTable")
        self.seqs = g("SequenceTable")
        self.tracks = g("TrackTable")
        cmd = g("CommandTable")
        self.cmds = [parse_cmds(c.get("Command") or b"") for c in cmd]
        ev = g("TrackEventTable")
        self.events = [parse_cmds(c.get("Command") or b"") for c in ev] if ev else self.cmds

    def _pan(self, cmd_index, table=None):
        table = self.cmds if table is None else table
        if cmd_index is None or cmd_index == 0xFFFF or cmd_index >= len(table):
            return None
        for code, data in table[cmd_index]:
            if code == CMD_PAN and len(data) >= 2:
                return struct.unpack(">h", data[:2])[0]
        return None

    def leaves(self, rtype, idx, pan=None, depth=0):
        """List of (waveform_index, pan) reachable from (type, index)."""
        if depth > 32:
            return []
        out = []
        if rtype == 1:
            if idx < len(self.waves):
                out.append((idx, pan))
        elif rtype == 2:
            if idx >= len(self.synths):
                return out
            s = self.synths[idx]
            p = self._pan(s.get("CommandIndex"))
            p = pan if p is None else p
            items = s.get("ReferenceItems") or b""
            for i in range(0, len(items) - 3, 4):
                t, n = struct.unpack_from(">HH", items, i)
                out += self.leaves(t, n, p, depth + 1)
        elif rtype == 3:
            if idx >= len(self.seqs):
                return out
            s = self.seqs[idx]
            ti = s.get("TrackIndex") or b""
            for i in range(0, len(ti) - 1, 2):
                tn, = struct.unpack_from(">H", ti, i)
                if tn >= len(self.tracks):
                    continue
                tr = self.tracks[tn]
                p = self._pan(tr.get("CommandIndex"))
                p = pan if p is None else p
                ei = tr.get("EventIndex")
                if ei is None or ei == 0xFFFF or ei >= len(self.events):
                    continue
                for code, data in self.events[ei]:
                    if code in CMD_NOTE_ON and len(data) >= 4:
                        t, n = struct.unpack(">HH", data[:4])
                        out += self.leaves(t, n, p, depth + 1)
        return out

    def cue_list(self):
        """[(name, [(waveform_index, pan)])] in cue order."""
        by_index = {}
        for n in self.names:
            by_index.setdefault(n["CueIndex"], n["CueName"])
        res = []
        for i, c in enumerate(self.cues):
            name = by_index.get(i, "cue_%04d" % c.get("CueId", i))
            res.append((name, self.leaves(c["ReferenceType"], c["ReferenceIndex"])))
        return res

    def wave_ref(self, wi):
        """(is_streamed, awb_id) for a WaveformTable row."""
        w = self.waves[wi]
        streaming = w.get("Streaming") or 0
        if streaming == 1:
            sid = w.get("StreamAwbId")
            return True, (w["Id"] if sid is None else sid)
        mid = w.get("MemoryAwbId")
        return False, (w["Id"] if mid is None else mid)


def awb_entries(blob):
    """{id: waveform} for an AWB (CPK or AFS2)."""
    if blob[:4] == b"CPK ":
        return {fid: b for _, fid, b in cpk_entries_mem(blob)}
    if blob[:4] == b"AFS2":
        n, = struct.unpack_from("<I", blob, 8)
        osz = blob[5]
        idsz = blob[6] if blob[6] else 2
        align = struct.unpack_from("<H", blob, 0x0C)[0] or 0x20
        ids = [int.from_bytes(blob[0x10 + i * idsz:0x12 + i * idsz + idsz - 2], "little")
               for i in range(n)]
        base = 0x10 + n * idsz
        offs = [int.from_bytes(blob[base + i * osz:base + (i + 1) * osz], "little")
                for i in range(n + 1)]
        out = {}
        for i in range(n):
            s = (offs[i] + align - 1) // align * align
            out[ids[i]] = blob[s:offs[i + 1]]
        return out
    raise ValueError("unknown AWB format (%r)" % blob[:4])


def folder_entries(folder):
    """{id: path} for a folder extracted from a numbered CPK (0000.adx...)."""
    out = {}
    for fn in os.listdir(folder):
        m = re.match(r"^(\d{4,})\.", fn)
        if m and os.path.isfile(os.path.join(folder, fn)):
            out[int(m.group(1))] = os.path.join(folder, fn)
    return out


def wave_info(path):
    """(sample_rate, channels, num_samples) from an ADX or CWAV header, or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(0x200)
        if head[:2] == b"\x80\x00":
            ch = head[7]
            rate, n = struct.unpack_from(">ii", head, 8)
            return rate, ch, n
        if head[:4] == b"CWAV":
            info, = struct.unpack_from("<I", head, 0x18)
            rate, = struct.unpack_from("<I", head, info + 0x0C)
            n, = struct.unpack_from("<i", head, info + 0x14)
            ch, = struct.unpack_from("<I", head, info + 0x1C)
            return rate, ch, n
    except (OSError, struct.error):
        pass
    return None


def _compare(want, got):
    """Relative sample-count error, or None if rate/channels differ."""
    if got is None:
        return None
    rate, ch, n = want
    g_rate, g_ch, g_n = got
    if (rate and g_rate != rate) or (ch and g_ch != ch) or not n:
        return None
    return abs(g_n - n) / float(n)


def describe_stream_candidates(acb_path, need, search=16):
    """Human-readable diagnosis of the folders near an ACB (for the report)."""
    d, fn = os.path.split(acb_path)
    m = re.match(r"^(\d+)\.acb$", fn)
    if not m:
        return "file name is not numeric"
    num, width = int(m.group(1)), len(m.group(1))
    out = []
    for dist in range(1, search + 1):
        name = "%0*d" % (width, num + dist)
        cand = os.path.join(d, name)
        if not os.path.isdir(cand):
            continue
        files = folder_entries(cand)
        present = [i for i in need if i in files]
        errs = [_compare(need[i], wave_info(files[i])) for i in present]
        same_fmt = [e for e in errs if e is not None]
        out.append("%s: %d files, %d/%d ids present, %d same rate/channels, mean error %s"
                   % (name, len(files), len(present), len(need), len(same_fmt),
                      "%.0f%%" % (100 * sum(same_fmt) / len(same_fmt)) if same_fmt else "-"))
    return "; ".join(out) or "no folder in the next %d entries" % search


def find_stream_awb(acb_path, need, search=16, max_error=0.5):
    """Finds the extracted CPK folder holding an ACB's streamed waveforms.

    need = {awb_id: (sample_rate, channels, num_samples)} from the ACB.
    Streamed AWBs are stored a few entries after their ACB, not always the
    next one (1427.acb -> 1428/, but 1566.acb -> 1569/ and 1567.acb -> 1568/).
    A candidate folder must hold every id with the same sample rate and
    channel count. The ACB sample counts are often off from the ADX headers
    (up to ~10%, apparently the length before trimming), so they only rank
    the candidates: same file count first, then smallest mean error.
    Returns ({awb_id: path}, folder, mean_error) or (None, None, None).
    """
    d, fn = os.path.split(acb_path)
    m = re.match(r"^(\d+)\.acb$", fn)
    if not m:
        return None, None, None
    num, width = int(m.group(1)), len(m.group(1))
    best = None
    for dist in range(1, search + 1):
        cand = os.path.join(d, "%0*d" % (width, num + dist))
        if not os.path.isdir(cand):
            continue
        files = folder_entries(cand)
        if not all(i in files for i in need):
            continue
        errs = [_compare(need[i], wave_info(files[i])) for i in need]
        if any(e is None for e in errs):
            continue
        err = sum(errs) / len(errs)
        if err > max_error:
            continue
        score = (len(files) == len(need), -err, -dist)
        if best is None or score > best[0]:
            best = (score, {i: files[i] for i in need}, cand, err)
    return best[1:] if best else (None, None, None)
