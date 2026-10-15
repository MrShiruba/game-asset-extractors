#!/usr/bin/env python3
"""
Kanokon Esuii (PS2, SLPM-55041) extractor.

  Handles the proprietary .DAT archives only:
    CPS images      -> PNG
    SC3 scripts     -> .sc3 + .txt (Japanese text, decoded with charset.txt)
    SYSTEM font     -> PNG sheet
    SYSTEM 00079    -> voice length table (CSV)
    SOUND.DAT       -> .sq / .hd / .bd + one WAV per sample (correct rate)
    anything else   -> .bin
  The .AFS archives (voice/BGM/SE) are already readable with standard
  AFS/ADX tools and are not handled here.

Usage:
  python3 kanokon_extract.py <game_dir> [output_dir] [--jobs N]
  python3 kanokon_extract.py CHARA.DAT out/        (single file)

  --jobs  number of worker processes (default: number of CPU cores)

Formats (reverse-engineered from SLPM_550.41):
  DAT : table of uint32 pairs (offset in 0x800 sectors, size in KiB),
        offsets RELATIVE to 0x8000 (fixed 32 KiB table area).
  CPS : 0x20-byte header ("CPS\\0", size, 0x68, 0x0100, unpacked size,
        "bmp\\0", u16 width, height, bpp, flag), modified KID obfuscation
        (starts at 0x20, first 4 KiB only, 8-word key table), then KID RLE
        from 0x28. 8 bpp output = 1024-byte RGBA palette (CSM1) + pixels.
"""
import mmap, os, struct, sys
from concurrent.futures import ProcessPoolExecutor

M32 = 0xFFFFFFFF
KEYTAB = [0x2623A189, 0x146FD8D7, 0x8E6F55FF, 0x1F497BCD,
          0x1BB74F41, 0x0EB731D1, 0x5C031379, 0x64350881]
DAT_BASE = 0x8000

# ----------------------------------------------------------------- CPS
def cps_deobfuscate(buf):
    b = bytearray(buf)
    n = struct.unpack_from("<I", b, 4)[0]
    if n > len(b):
        raise ValueError("truncated CPS (%d > %d)" % (n, len(b)))
    del b[n:]
    v_off = (struct.unpack_from("<I", b, n - 4)[0] - 0x7534682) & M32
    if v_off and v_off + 4 <= n:
        lim = min(n, 0x1000) - 4
        seed = (struct.unpack_from("<I", b, v_off)[0] + v_off + 0x3786425) & M32
        i, k = 0x20, 0
        while i < lim:
            if i != v_off:
                v = struct.unpack_from("<I", b, i)[0]
                struct.pack_into("<I", b, i, (v - (n + seed + KEYTAB[k])) & M32)
            seed = (seed * 0x41C64E6D + 0x9B06) & M32
            k = (k + 1) & 7
            i += 4
    struct.pack_into("<I", b, n - 4, 0)
    return b

def kid_unrle(src, pos, out_sz):
    out = bytearray(out_sz)
    o = 0
    i = pos
    n = len(src)
    while o < out_sz and i < n:
        rt = src[i]; i += 1
        if rt & 0x80:
            if rt & 0x40:                      # single-byte run
                rl = (rt & 0x1F) + 2
                if rt & 0x20:
                    rl += src[i] << 5; i += 1
                c = src[i]; i += 1
                rl = min(rl, out_sz - o)
                out[o:o + rl] = bytes((c,)) * rl
                o += rl
            else:                              # back-reference
                rl = ((rt >> 2) & 0xF) + 2
                s = o - src[i] - ((rt & 3) << 8) - 1; i += 1
                rl = min(rl, out_sz - o)
                if s + rl <= o:
                    out[o:o + rl] = out[s:s + rl]
                else:
                    for k in range(rl):
                        out[o + k] = out[s + k]
                o += rl
        else:
            if rt & 0x40:                      # repeated block
                rl = (rt & 0x3F) + 2
                it = src[i] + 1; i += 1
                blk = bytes(src[i:i + rl]); i += rl
                for _ in range(it):
                    r = min(rl, out_sz - o)
                    out[o:o + r] = blk[:r]
                    o += r
            else:                              # literals
                rl = (rt & 0x1F) + 1
                if rt & 0x20:
                    rl += src[i] << 5; i += 1
                r = min(rl, out_sz - o)
                out[o:o + r] = src[i:i + r]
                i += rl
                o += r
    return out

def cps_decode(buf):
    b = cps_deobfuscate(buf)
    unp = struct.unpack_from("<I", b, 0xC)[0]
    kind = bytes(b[0x10:0x14]).rstrip(b"\0").decode("ascii", "replace")
    w, h, bpp, flag = struct.unpack_from("<4H", b, 0x14)
    data = kid_unrle(b, 0x28, unp - 8)
    return kind, w, h, bpp, flag, data

def csm1(pal):
    """Undo the PS2 CSM1 palette swizzle (swap entries 8-15 and 16-23 of each 32)."""
    p = list(pal)
    for base in range(0, len(p) - 31, 32):
        for i in range(8):
            p[base + 8 + i], p[base + 16 + i] = pal[base + 16 + i], pal[base + 8 + i]
    return p

def a2(v):  # PS2 alpha 0..0x80 -> 0..255
    return 255 if v >= 0x80 else v * 2

def cps_to_png(buf, path):
    from PIL import Image
    kind, w, h, bpp, flag, d = cps_decode(buf)
    npx = w * h
    # The header bpp field is unreliable (some BG logos are direct colour but
    # flagged as 8 bpp), so the format is inferred from the unpacked size.
    L = len(d)
    if L == npx * 4:
        bpp = 32
    elif L == npx * 3:
        bpp = 24
    elif L == 1024 + npx:
        bpp = 8
    elif L == npx * 2:
        bpp = 16
    elif L == 64 + (npx + 1) // 2:
        bpp = 4
    if bpp == 8:
        pal = [(d[i*4], d[i*4+1], d[i*4+2], a2(d[i*4+3])) for i in range(256)]
        pal = csm1(pal)
        im = Image.new("P", (w, h))
        im.putdata(d[1024:1024 + npx])
        flat = [c for rgba in pal for c in rgba]
        im.putpalette(flat, rawmode="RGBA")
        im = im.convert("RGBA")
    elif bpp == 4:
        pal = [(d[i*4], d[i*4+1], d[i*4+2], a2(d[i*4+3])) for i in range(16)]
        raw = d[64:64 + (npx + 1) // 2]
        px = bytearray(npx)
        for i in range(npx):
            v = raw[i >> 1]
            px[i] = (v >> 4) if (i & 1) else (v & 0xF)
        im = Image.new("P", (w, h)); im.putdata(px)
        im.putpalette([c for rgba in pal for c in rgba], rawmode="RGBA")
        im = im.convert("RGBA")
    elif bpp == 32:
        im = Image.frombytes("RGBA", (w, h), bytes(d[:npx * 4]))
        r, g, b_, a = im.split()
        im = Image.merge("RGBA", (r, g, b_, a.point(a2)))
    elif bpp == 24:
        im = Image.frombytes("RGB", (w, h), bytes(d[:npx * 3]))
    elif bpp == 16:
        px = struct.unpack_from("<%dH" % npx, d, 0)
        out = bytearray(npx * 4)
        for i, v in enumerate(px):
            out[i*4]   = (v & 0x1F) << 3
            out[i*4+1] = ((v >> 5) & 0x1F) << 3
            out[i*4+2] = ((v >> 10) & 0x1F) << 3
            out[i*4+3] = 255 if v & 0x8000 else 0
        im = Image.frombytes("RGBA", (w, h), bytes(out))
    else:
        raise ValueError("unsupported bpp %d" % bpp)
    im.save(path, optimize=False)
    return "%s %dx%d %dbpp" % (kind, w, h, bpp)

# ----------------------------------------------------------------- SC3
CHARSET = None   # glyph index -> character, loaded from charset.txt
CHARSET_PATH = None

def load_charset(path):
    global CHARSET
    if path and os.path.isfile(path):
        CHARSET = list(open(path, encoding="utf-8").read().replace("\n", ""))

def glyph(g):
    if CHARSET and g < len(CHARSET) and CHARSET[g] != "□":
        return CHARSET[g]
    return "{%03x}" % g

def sc3_strings(d):
    """String table of an SC3 script -> list of (speaker, text).
    Control codes: 01 name 02 = speaker, 00 = line break, 03 = end of line,
    04 xx = colour, FF = end of string; >= 0x80 = 2-byte glyph index."""
    st, rt = struct.unpack_from("<II", d, 4)
    n = max(0, (rt - st) // 4)
    if st + 4 * n > len(d):
        n = max(0, (len(d) - st) // 4)
    out = []
    if n == 0:
        return out
    for o in struct.unpack_from("<%dI" % n, d, st):
        name, cur = "", []
        i = o; in_name = False
        while i < len(d):
            b = d[i]
            if b == 0xFF: break
            if b >= 0x80:
                ch = glyph(((b & 0x7F) << 8) | d[i + 1]); i += 2
                if in_name: name += ch
                else: cur.append(ch)
                continue
            i += 1
            if b == 0x01: in_name = True
            elif b == 0x02: in_name = False
            elif b == 0x00: cur.append("\n")
            elif b == 0x03: pass
            elif b == 0x04:
                cur.append("[c%d]" % d[i]); i += 1
            else:
                cur.append("[%02x]" % b)
        out.append((name, "".join(cur)))
    return out

def sc3_to_txt(d, path):
    with open(path, "w", encoding="utf-8") as f:
        for k, (name, text) in enumerate(sc3_strings(d)):
            t = text.replace("\n", "\\n")
            f.write("%04d\t%s\t%s\n" % (k, name, t))

# ----------------------------------------------------------------- DAT
def dat_entries(m):
    ents = []
    for p in range(0, DAT_BASE, 8):
        o, s = struct.unpack_from("<II", m, p)
        if p and o == 0 and s == 0:
            break
        ents.append((DAT_BASE + o * 0x800, s * 0x400))
    return ents

def _job(args):
    path, idx, off, size, outdir, charset = args
    if charset and CHARSET is None:
        load_charset(charset)
    with open(path, "rb") as f:
        f.seek(off); buf = f.read(size)
    base = os.path.join(outdir, "%05d" % idx)
    try:
        if buf[:4] == b"CPS\0":
            return idx, cps_to_png(buf, base + ".png")
        if buf[:4] == b"SC3\0":
            open(base + ".sc3", "wb").write(buf.rstrip(b"\0") or buf)
            sc3_to_txt(buf, base + ".txt")
            return idx, "script SC3"
        open(base + ".bin", "wb").write(buf)
        return idx, "bin"
    except Exception as e:
        open(base + ".bin", "wb").write(buf)
        return idx, "ERROR %s -> .bin" % e

# ----------------------------------------------------------------- SOUND
def extract_sound(path, outdir):
    """SOUND.DAT entry 0 = [u32 SQ size][u32 BD size][u32 HD size] + 0x74
    bytes of padding, then SQ, BD, HD (standard Sony PS2 sound bank)."""
    with open(path, "rb") as f:
        m = f.read()
    o, s = dat_entries(m)[0]
    sq_sz, bd_sz, hd_sz = struct.unpack_from("<3I", m, o)
    p = o + 0x80
    sq = m[p:p + sq_sz]
    k = sq.find(b"IECSsreV", 8)            # leftover padding after the sequence
    if k > 0: sq = sq[:k]
    bd = m[p + sq_sz:p + sq_sz + bd_sz]
    hd = m[p + sq_sz + bd_sz:p + sq_sz + bd_sz + hd_sz]
    assert hd[:8] == b"IECSsreV" and hd[0x10:0x18] == b"IECSdaeH", "HD header not found"
    for ext, blob in (("sq", sq), ("hd", hd), ("bd", bd)):
        open(os.path.join(outdir, "sound." + ext), "wb").write(blob)
    print("SOUND.DAT: sound.sq (%d B), sound.hd (%d B), sound.bd (%d B) -> %s"
          % (len(sq), len(hd), len(bd), outdir))
    n = hd_to_wavs(hd, bd, os.path.join(outdir, "samples"))
    print("  %d samples -> %s (per-sample rate read from the HD)"
          % (n, os.path.join(outdir, "samples")))

ADPCM_COEF = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))

def adpcm_decode(frames):
    """PS-ADPCM (SPU2) -> 16-bit mono PCM. Stops at the end flag."""
    out = []; s1 = s2 = 0
    for f in range(0, len(frames) - 15, 16):
        hdr, flag = frames[f], frames[f + 1]
        sh = hdr & 0xF; c1, c2 = ADPCM_COEF[min(hdr >> 4, 4)]
        for byte in frames[f + 2:f + 16]:
            for nib in (byte & 0xF, byte >> 4):
                s = ((nib - 16 if nib & 8 else nib) << 12) >> (sh if sh <= 12 else 9)
                s += (s1 * c1 + s2 * c2) >> 6
                s = -32768 if s < -32768 else 32767 if s > 32767 else s
                s2, s1 = s1, s
                out.append(s)
        if flag & 1 and f > 0:
            break
    return struct.pack("<%dh" % len(out), *out)

def hd_to_wavs(hd, bd, outdir):
    """HD 'Vagi' table: per sample, u32 offset in BD, u16 sample rate, u8 loop flag."""
    import wave
    os.makedirs(outdir, exist_ok=True)
    v = hd.find(b"IECSigaV")
    if v < 0: return 0
    mx = struct.unpack_from("<I", hd, v + 12)[0]
    offs = struct.unpack_from("<%dI" % (mx + 1), hd, v + 16)
    ents = [struct.unpack_from("<IHB", hd, v + o) for o in offs]
    starts = sorted(set(e[0] for e in ents)) + [len(bd)]
    for k, (off, rate, loop) in enumerate(ents):
        end = starts[starts.index(off) + 1]
        pcm = adpcm_decode(bd[off:end])
        name = "sample_%02d_%dHz%s.wav" % (k, rate, "_loop" if loop else "")
        with wave.open(os.path.join(outdir, name), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(pcm)
    return len(ents)

# ----------------------------------------------------------------- SYSTEM
def voice_table(path, out, game_dir):
    """SYSTEM entry 79: sample count (u32) of every voice in VOICE.AFS."""
    d = open(path, "rb").read()
    vals = struct.unpack("<%dI" % (len(d) // 4), d)
    names, rates = {}, {}
    afs = next((os.path.join(game_dir, f) for f in os.listdir(game_dir)
                if f.upper() == "VOICE.AFS"), None) if game_dir else None
    if afs:
        with open(afs, "rb") as f:
            m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        n = struct.unpack_from("<I", m, 4)[0]
        ents = [struct.unpack_from("<II", m, 8 + i * 8) for i in range(n)]
        first = min(eo for eo, es in ents if es)
        for tp in (8 + n * 8, first - 8):
            to, ts = struct.unpack_from("<II", m, tp)
            if to and ts >= n * 0x30 and to + ts <= len(m):
                for i in range(n):
                    names[i] = m[to + i*0x30: to + i*0x30 + 32].split(b"\0")[0].decode("cp932", "replace")
                break
        for i, (eo, es) in enumerate(ents):
            if es >= 16 and m[eo:eo + 2] == b"\x80\x00":
                rates[i] = struct.unpack_from(">I", m, eo + 8)[0]
        count = n
    else:
        count = max(i for i, v in enumerate(vals) if v) + 1
    with open(out, "w", encoding="utf-8-sig") as f:
        f.write("voice_index;file;samples;duration_s\n")
        for i in range(count):
            v = vals[i] if i < len(vals) else 0
            r = rates.get(i)
            dur = "%.2f" % (v / r) if (v and r) else ""
            f.write("%d;%s;%d;%s\n" % (i, names.get(i, ""), v, dur))
    print("  voice lengths -> %s%s" % (out, "" if afs else " (VOICE.AFS not found: no names or durations)"))

def export_font(path, out, cols=64):
    """Game font: 24x24 glyphs, 4 bpp (high nibble = left pixel)."""
    from PIL import Image
    d = open(path, "rb").read()
    n = len(d) // 288
    rows = (n + cols - 1) // cols
    im = Image.new("L", (cols * 24, rows * 24))
    px = bytearray(cols * 24 * rows * 24)
    W = cols * 24
    for g in range(n):
        gx, gy = (g % cols) * 24, (g // cols) * 24
        for k in range(288):
            b = d[g * 288 + k]
            y, x = divmod(k * 2, 24)
            p = (gy + y) * W + gx + x
            px[p] = (b >> 4) * 17
            px[p + 1] = (b & 15) * 17
    im.frombytes(bytes(px))
    im.save(out)
    print("  font -> %s (%d glyphs, index = row*%d + column)" % (out, n, cols))

# ----------------------------------------------------------------- main
def extract_dat(path, outroot, jobs=None):
    name = os.path.splitext(os.path.basename(path))[0].upper()
    outdir = os.path.join(outroot, name)
    os.makedirs(outdir, exist_ok=True)
    if name == "SOUND":
        return extract_sound(path, outdir)
    with open(path, "rb") as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        ents = dat_entries(m)
    print("%s: %d entries" % (os.path.basename(path), len(ents)))
    tasks = [(path, i, o, s, outdir, CHARSET_PATH) for i, (o, s) in enumerate(ents)]
    stats = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for done, (i, info) in enumerate(ex.map(_job, tasks, chunksize=4), 1):
            key = "ERROR" if info.startswith("ERROR") else info.split(" ")[0]
            stats[key] = stats.get(key, 0) + 1
            if key == "ERROR":
                print("  [%05d] %s" % (i, info))
            if done % 100 == 0 or done == len(tasks):
                print("  %d/%d" % (done, len(tasks)), end="\r", flush=True)
    print("\n  -> %s  %s" % (outdir, stats))
    if name == "SYSTEM":
        font = os.path.join(outdir, "00014.bin")
        if os.path.isfile(font):
            export_font(font, os.path.join(outdir, "00014_font.png"))
        vt = os.path.join(outdir, "00079.bin")
        if os.path.isfile(vt):
            voice_table(vt, os.path.join(outdir, "00079_voice_lengths.csv"),
                        os.path.dirname(os.path.abspath(path)))

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jobs = None
    if "--jobs" in sys.argv:
        jobs = int(sys.argv[sys.argv.index("--jobs") + 1]); args.remove(str(jobs))
    if not args:
        sys.exit(__doc__)
    src = args[0]; out = args[1] if len(args) > 1 else "extracted"
    global CHARSET_PATH
    here = os.path.dirname(os.path.abspath(__file__))
    for c in ("charset.txt", os.path.join(here, "charset.txt")):
        if os.path.isfile(c):
            CHARSET_PATH = os.path.abspath(c); load_charset(c)
            print("charset:", CHARSET_PATH); break
    files = [src] if os.path.isfile(src) else sorted(
        os.path.join(src, f) for f in os.listdir(src)
        if f.upper().endswith(".DAT"))
    for p in files:
        extract_dat(p, out, jobs)

if __name__ == "__main__":
    main()
