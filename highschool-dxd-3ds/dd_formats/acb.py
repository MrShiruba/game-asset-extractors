"""CRI Atom ACB (3DS): @UTF tables and CWAV waveforms stored in an embedded AWB (AFS2)."""
import struct


def read_utf(d, base=0):
    """CRI @UTF table (big endian)."""
    if d[base:base + 4] != b'@UTF':
        raise ValueError('no @UTF table at 0x%x' % base)
    b = base + 8
    rows_off, str_off, data_off, name_off, ncols, rowlen, nrows = struct.unpack('>IIIIHHI', d[b:b + 24])

    def s(o):
        p = b + str_off + o
        return d[p:d.index(b'\0', p)].decode('cp932', 'replace')

    def val(p, ty):
        fmts = {0: '>B', 1: '>b', 2: '>H', 3: '>h', 4: '>I', 5: '>i', 6: '>Q', 7: '>q', 8: '>f'}
        if ty in fmts:
            n = struct.calcsize(fmts[ty])
            return struct.unpack(fmts[ty], d[p:p + n])[0], p + n
        if ty == 0xA:
            return s(struct.unpack('>I', d[p:p + 4])[0]), p + 4
        if ty == 0xB:
            o, l = struct.unpack('>II', d[p:p + 8])
            return (b + data_off + o, l), p + 8
        raise ValueError('unknown @UTF type %d' % ty)

    p = b + 24
    cols = []
    for _ in range(ncols):
        flag = d[p]; p += 1
        nm = s(struct.unpack('>I', d[p:p + 4])[0]); p += 4
        st, ty = flag & 0xF0, flag & 0x0F
        const = None
        if st == 0x30:
            const, p = val(p, ty)
        cols.append((nm, st, ty, const))
    rows = []
    for r in range(nrows):
        p = b + rows_off + r * rowlen
        row = {}
        for nm, st, ty, const in cols:
            if st == 0x50:
                row[nm], p = val(p, ty)
            else:
                row[nm] = const
        rows.append(row)
    return s(name_off), rows


def cwav_info(c):
    E = '<' if c[4:6] == b'\xff\xfe' else '>'
    u32 = lambda o: struct.unpack(E + 'I', c[o:o + 4])[0]
    nblk = struct.unpack(E + 'H', c[0x10:0x12])[0]
    info = next(u32(0x18 + k * 12) for k in range(nblk) if c[u32(0x18 + k * 12):u32(0x18 + k * 12) + 4] == b'INFO')
    enc, loop = c[info + 8], c[info + 9]
    rate, ls, le = u32(info + 0xC), u32(info + 0x10), u32(info + 0x14)
    return rate, u32(info + 0x1C), le, enc, loop, ls


def acb_cwav(d):
    """Return ([(name, bcwav_data)], list.txt lines), or None if the ACB has no embedded
    CWAV AWB (e.g. bgm.acb + bgm.awb, which vgmstream already reads)."""
    _, hdr = read_utf(d)
    h = hdr[0]
    ao, al = h.get('AwbFile') or (0, 0)
    if not al or d[ao:ao + 4] != b'AFS2':
        return None
    tab = lambda k: read_utf(d, h[k][0])[1]
    names, cues, synths, waves = tab('CueNameTable'), tab('CueTable'), tab('SynthTable'), tab('WaveformTable')
    osz = d[ao + 5]
    n, align = struct.unpack('<II', d[ao + 8:ao + 16])
    ids = struct.unpack('<%dH' % n, d[ao + 16:ao + 16 + 2 * n])
    p = ao + 16 + 2 * n
    offs = [int.from_bytes(d[p + i * osz:p + (i + 1) * osz], 'little') for i in range(n + 1)]
    files = {}
    for i in range(n):
        s = (offs[i] + align - 1) // align * align
        files[ids[i]] = d[ao + s:ao + offs[i + 1]]
    if not any(f[:4] == b'CWAV' for f in files.values()):
        return None

    def synth_waves(si, seen=()):
        r = []
        o, l = synths[si]['ReferenceItems']
        for k in range(0, l, 4):
            t, idx = struct.unpack('>HH', d[o + k:o + k + 4])
            if t == 1:
                r.append(idx)
            elif t in (2, 3) and idx not in seen:
                r += synth_waves(idx, seen + (idx,))
        return r

    ENC = {0: 'PCM8', 1: 'PCM16', 2: 'DSP-ADPCM', 3: 'IMA-ADPCM'}
    out, log, used = [], [], set()
    for nm in names:
        cue = cues[nm['CueIndex']]
        rt, ri = cue['ReferenceType'], cue['ReferenceIndex']
        wl = list(dict.fromkeys([ri] if rt == 1 else synth_waves(ri) if rt == 2 else []))
        for j, wi in enumerate(wl):
            wid = waves[wi]['Id']; used.add(wid)
            fn = nm['CueName'] + ('' if len(wl) == 1 else '_%d' % j)
            c = files[wid]
            out.append((fn, c))
            if c[:4] == b'CWAV':
                rate, nch, ns, enc, loop, ls = cwav_info(c)
                lp = 'loop %d-%d' % (ls, ns) if loop else 'no loop'
                log.append('%s\twave %d\t%d Hz\t%d ch\t%.2fs\t%s\t%s' % (fn, wid, rate, nch, ns / rate, ENC.get(enc, enc), lp))
    for wid in sorted(set(files) - used):
        out.append(('wave_%03d' % wid, files[wid]))
    return out, log
