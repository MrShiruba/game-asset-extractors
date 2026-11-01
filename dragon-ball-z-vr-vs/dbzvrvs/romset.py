"""ROM set: the MAME 'dbzvrvs' zip and the memory regions built from it."""
import os, sys, zipfile, zlib

ROMS = {  # name: crc32 (MAME segas32.cpp)
    "epr-16543": 0x7b9bc6f5, "epr-16542a": 0x6449ab22, "epr-16541": 0x1d61d836,
    "mpr-16540": 0xb6f9bb43, "mpr-16539": 0x38c26418, "mpr-16538": 0x4d402c31,
    "mpr-16545": 0x51748bac, "mpr-16544": 0xf6c93dfc,
    "mpr-16546": 0x96f4be31, "mpr-16548": 0x00377f59, "mpr-16550": 0x168e8966, "mpr-16552": 0xa31dae31,
    "mpr-16547": 0x50d328ed, "mpr-16549": 0xa5802e9f, "mpr-16551": 0xdede05fc, "mpr-16553": 0xc0a43009,
}


def load_zip(path):
    files = {}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            base = os.path.basename(info.filename).lower()
            for n in ROMS:
                if base == n or base.startswith(n + "."):
                    files[n] = z.read(info)
    missing = [n for n in ROMS if n not in files]
    if missing:
        sys.exit("missing ROMs in zip: " + ", ".join(missing))
    for n, crc in ROMS.items():
        if zlib.crc32(files[n]) & 0xffffffff != crc:
            print("warning: %s has a bad CRC (not the MAME 'dbzvrvs' set?)" % n, flush=True)
    return files


def sound_region(files):
    """MAME 'soundcpu' region: epr-16541 x4 at 0, mpr-16540/39/38 at 1/2/3 MB."""
    r = bytearray(0x400000)
    for i in range(4):
        r[i * 0x40000:(i + 1) * 0x40000] = files["epr-16541"]
    for i, n in enumerate(("mpr-16540", "mpr-16539", "mpr-16538")):
        r[(i + 1) * 0x100000:(i + 2) * 0x100000] = files[n]
    return bytes(r)


def program(files):
    """V60 program: epr-16543 (data, 0x00000-0x7FFFF) + epr-16542a (code and data, 0x80000-0xFFFFF)."""
    return files["epr-16543"] + files["epr-16542a"]
