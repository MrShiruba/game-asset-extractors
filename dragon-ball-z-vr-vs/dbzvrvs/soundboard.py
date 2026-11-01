"""Interface to the sound-board emulator s32snd (C, compiled on the fly): runs one sound command of
the Z80 sound program and writes a VGM log or a WAV render; plus the VGM/WAV file helpers."""
import os, shutil, subprocess, struct, gzip, wave
import numpy as np

C_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "s32snd")


def build_emulator(workdir):
    exe = os.path.join(workdir, "s32snd.exe" if os.name == "nt" else "s32snd")
    for cc in (os.environ.get("CC"), "cc", "gcc", "clang"):
        if not cc or not shutil.which(cc):
            continue
        cmd = [cc, "-O2", "-o", exe, os.path.join(C_DIR, "s32snd.c"), os.path.join(C_DIR, "z80.c")]
        if subprocess.run(cmd).returncode == 0:
            return exe
    return None


def run_emu(exe, region_path, table, code, out, maxsec=None, tail=None, logsamples=False, center=False):
    args = [exe, region_path, str(table), str(code), out]
    if maxsec is not None:
        args.append(str(maxsec))
        if tail is not None:
            args.append(str(tail))
    env = dict(os.environ)
    if logsamples:
        env["S32_LOG_SAMPLES"] = "1"
    if center:
        env["S32_CENTER_PAN"] = "1"
    p = subprocess.run(args, capture_output=True, text=True, env=env)
    if p.returncode:
        raise RuntimeError(p.stderr)
    info = dict(kv.split("=") for kv in p.stdout.split())
    # (sample index, FD step, start time in 1/44100 s) for every sample the driver starts
    steps = [tuple(map(int, l.split()[1:5])) for l in p.stderr.splitlines() if l.startswith("SMP ")]
    return info, steps


# ---------------------------------------------------------------- VGM tags
def gd3(title_en, title_jp=""):
    fields = [title_en, title_jp,
              "Dragon Ball Z: V.R.V.S.", "ドラゴンボールZ V.R.V.S.",
              "Sega System 32", "セガ システム32",
              "", "", "1994", "", "Logged with s32snd (dbzvrvs_rip.py)"]
    body = b"".join(f.encode("utf-16-le") + b"\0\0" for f in fields)
    return b"Gd3 " + struct.pack("<II", 0x100, len(body)) + body


def finish_vgm(raw_path, out_path, title):
    d = bytearray(open(raw_path, "rb").read())
    tag = gd3(title)
    gd3_off = len(d)
    d += tag
    struct.pack_into("<I", d, 0x14, gd3_off - 0x14)
    struct.pack_into("<I", d, 0x04, len(d) - 4)
    with gzip.GzipFile(out_path, "wb", compresslevel=9, mtime=0) as f:
        f.write(bytes(d))


# ---------------------------------------------------------------- WAV helpers
def read_wav(path):
    with wave.open(path) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2)
    return a
