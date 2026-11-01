"""File type detection from contents, and safe file names."""
import re
import struct

from .utf import parse_utf, unmask_utf


MAGIC_EXT = [
    (b"CGFX", ".bcres"), (b"SARC", ".sarc"), (b"darc", ".darc"),
    (b"BCH\x00", ".bch"), (b"CTPK", ".ctpk"), (b"CFNT", ".bcfnt"),
    (b"CFNU", ".bcfnt"), (b"CLYT", ".bclyt"), (b"CLAN", ".bclan"),
    (b"CWAV", ".bcwav"), (b"CSTM", ".bcstm"), (b"CSAR", ".bcsar"),
    (b"CWAR", ".bcwar"), (b"CWSD", ".bcwsd"), (b"CSEQ", ".bcseq"),
    (b"CBNK", ".bcbnk"), (b"AFS2", ".awb"), (b"AFS\x00", ".afs"),
    (b"IDSP", ".idsp"), (b"RIFF", ".wav"), (b"OggS", ".ogg"),
    (b"Yaz0", ".yaz0"), (b"CPK ", ".cpk"), (b"\x89PNG", ".png"),
    (b"MsgStdBn", ".msbt"), (b"MsgPrjBn", ".msbp"), (b"SMDH", ".smdh"),
]


def safe(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")
    return s or "_"


def guess_ext(data):
    for magic, ext in MAGIC_EXT:
        if data.startswith(magic):
            return ext
    if data[:4] == b"@UTF" or unmask_utf(data[:4]) == b"@UTF":
        try:
            name, cols, _ = parse_utf(data)
        except Exception:
            return ".utf"
        if "CueTable" in cols or "AwbFile" in cols:
            return ".acb"
        if name == "Header" and ("CategoryTable" in cols or "DspSettingTable" in cols
                                 or "AcfGuid" in cols or "CueTable" not in cols):
            return ".acf"
        return "." + safe(name)[:24] + ".utf"
    if data[:3] == b"HCA" or bytes(c & 0x7F for c in data[:3]) == b"HCA":
        return ".hca"
    if data[:2] == b"\x80\x00" and len(data) > 8:
        off, = struct.unpack(">H", data[2:4])
        if data[off - 2:off + 4] == b"(c)CRI":
            return ".adx"
    if len(data) >= 0x28 and data[-0x28:-0x24] == b"CLIM":
        return ".bclim"
    m = data[:4]
    if len(m) == 4 and all(0x20 <= c < 0x7F for c in m):
        return "." + "".join(c if c.isalnum() else "_" for c in m.decode()).lower()
    return ".bin"
