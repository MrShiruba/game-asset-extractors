"""Load a Dragon Ball Z arcade romset (Banpresto / Konami hardware) and build
the memory regions. Two games run on this board and are both supported:

* ``dbz``  / ``dbza`` : Dragon Ball Z (1993)
* ``dbz2``            : Dragon Ball Z 2 - Super Battle (1994)

Files are matched by CRC32 first, then by name, so renamed dumps still work.
The game is detected from the files present. Layouts follow the MAME driver
(src/mame/konami/dbz.cpp).
"""
import os
import zipfile
import zlib

# role -> list of (name, crc32, size). Roles holding several files are concatenated
# (psac) or word-interleaved (tiles, sprites) as in the MAME ROM_LOAD macros.
GAMES = {
    "dbz": {
        "title": "Dragon Ball Z (1993)",
        "main_sets": {
            "dbz":  (("222b11.9e", 0x4C6B75E9), ("222b12.9f", 0x48637FCE)),
            "dbza": (("222a11.9e", 0x60C7D9B2), ("222a12.9f", 0x6EBC6853)),
        },
        "tiles":    [("222a01.27c", 0x9FCE4ED4, 0x200000), ("222a02.27e", 0x651ACAA5, 0x200000)],
        "oki":      [("222a03.7c", 0x1924467B, 0x040000)],
        "sprites":  [("222a04.3j", 0x2533B95A, 0x200000), ("222a05.1j", 0x731B7F93, 0x200000),
                     ("222a06.3l", 0x97B767D3, 0x200000), ("222a07.1l", 0x430BC873, 0x200000)],
        "psac0":    [("222a09.25l", 0xF7B3F070, 0x200000)],   # roztiles0
        "psac1":    [("222a08.25k", 0x6410EE1B, 0x200000)],   # roztiles1
        "audiocpu": [("222a10.5e", 0x1C93E30A, 0x008000)],
    },
    "dbz2": {
        "title": "Dragon Ball Z 2 - Super Battle (1994)",
        "main_sets": {
            "dbz2": (("a9e.9e", 0xE6A142C9), ("a9f.9f", 0x76CAC399)),
        },
        "tiles":    [("ds-b01.27c", 0x8DC39972, 0x200000), ("ds-b02.27e", 0x7552F8CD, 0x200000)],
        "oki":      [("pcm.7c", 0xB58C884A, 0x040000)],
        "sprites":  [("ds-o01.3j", 0xD018531F, 0x200000), ("ds-o02.1j", 0x5A0F1EBE, 0x200000),
                     ("ds-o03.3l", 0xDDC3BEF1, 0x200000), ("ds-o04.1l", 0xB5DF6676, 0x200000)],
        "psac0":    [("ds-p03.25l", 0x1EAA671B, 0x200000), ("ds-p04.27l", 0x5845FF98, 0x200000)],
        "psac1":    [("ds-p01.25k", 0x1C7AAD68, 0x200000), ("ds-p02.27k", 0xE4C3A43B, 0x200000)],
        "audiocpu": [("s-001.5e", 0x154E6D03, 0x008000)],
    },
}
ROLES = ["tiles", "oki", "sprites", "psac0", "psac1", "audiocpu"]


class RomError(Exception):
    pass


def _read_source(path):
    """Return {basename: bytes} from a zip file or a directory (sub-folders, e.g. the
    bootleg 'dbz2bl/' of merged sets, are ignored)."""
    files = {}
    if os.path.isdir(path):
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isfile(full) and os.path.getsize(full) <= 0x400000:
                with open(full, "rb") as fh:
                    files[name.lower()] = fh.read()
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size > 0x400000 or "/" in info.filename.strip("/"):
                    continue
                files[info.filename.lower()] = zf.read(info)
    else:
        raise RomError(f"{path!r} is neither a zip nor a folder")
    return files


class RomSet:
    def __init__(self, path, strict=False, game=None):
        raw = _read_source(path)
        by_crc = {zlib.crc32(data) & 0xFFFFFFFF: data for data in raw.values()}
        self.warnings = []

        def score(g):
            spec = GAMES[g]
            names = [f for r in ROLES for f in spec[r]] + \
                    [f for s in spec["main_sets"].values() for f in s]
            return sum(1 for f in names if f[1] in by_crc or f[0] in raw)

        if game is None:
            game = max(GAMES, key=score)
            if score(game) == 0:
                raise RomError("no known ROM found (dbz, dbza, dbz2)")
        self.game = game
        self.title = GAMES[game]["title"]

        def get(name, crc, size=None):
            data = by_crc.get(crc)
            if data is None:
                data = raw.get(name)
                if data is not None:
                    msg = f"{name}: CRC mismatch (expected {crc:08x}), using file anyway"
                    if strict:
                        raise RomError(msg)
                    self.warnings.append(msg)
            if data is not None and size is not None and len(data) != size:
                raise RomError(f"{name}: bad size {len(data):#x}, expected {size:#x}")
            return data

        spec = GAMES[game]
        self.files, self.names = {}, {}
        for role in ROLES:
            datas = [get(*f) for f in spec[role]]
            self.names[role] = [f[0] for f in spec[role]]
            self.files[role] = datas if all(d is not None for d in datas) else None
        self.set_name = None
        for set_name, (even, odd) in spec["main_sets"].items():
            e, o = get(*even), get(*odd)
            if e and o:
                self.set_name = set_name
                self.files["main"] = (e, o)
                self.names["main"] = [even[0], odd[0]]
                break
        else:
            self.names["main"] = [n for s in spec["main_sets"].values() for n, _ in s]

    def need(self, role):
        if not self.files.get(role):
            raise RomError("missing ROM(s): " + ", ".join(self.names[role]))
        return self.files[role]

    # ---- regions -------------------------------------------------------
    @property
    def oki(self):
        return self.need("oki")[0]

    @property
    def audiocpu(self):
        return self.need("audiocpu")[0]

    @property
    def maincpu(self):
        """68000 program, big-endian (ROM_LOAD16_BYTE even/odd)."""
        even, odd = self.need("main")
        out = bytearray(len(even) * 2)
        out[0::2] = even
        out[1::2] = odd
        return bytes(out)

    @property
    def sprites(self):
        """K053246 region: ROM_LOAD64_WORD of 4 ROMs (8 bytes per 16-pixel row)."""
        return _interleave_words(self.need("sprites"))

    @property
    def tiles(self):
        """K056832 region: ROM_LOAD32_WORD of 2 ROMs."""
        return _interleave_words(self.need("tiles"))

    @property
    def psac(self):
        """K053936 ROZ tile regions: (roztiles0, roztiles1)."""
        return b"".join(self.need("psac0")), b"".join(self.need("psac1"))


def _interleave_words(roms):
    import numpy as np
    arrs = [np.frombuffer(r, dtype=np.uint16) for r in roms]
    return np.stack(arrs, axis=1).tobytes()
