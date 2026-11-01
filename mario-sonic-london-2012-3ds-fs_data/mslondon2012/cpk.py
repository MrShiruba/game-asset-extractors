"""CRI CPK archives (ITOC and TOC)."""
from .crilayla import crilayla_decompress
from .utf import parse_utf, utf_rows


def _table(read, off, size):
    return parse_utf(read(off, size)[0x10:])[2]


def list_cpk(read):
    """read(offset, size) -> bytes. Returns [(name, id, offset, size, extract_size)]."""
    h = _table(read, 0, 0x800)[0]
    files = []
    if h.get("TocOffset"):
        toc_off, cont_off = h["TocOffset"], h.get("ContentOffset")
        base = toc_off if not cont_off else min(toc_off, cont_off)
        for r in _table(read, toc_off, h["TocSize"] + 0x10):
            fid = r.get("ID") or 0
            name = r.get("FileName") or "%04d" % fid
            if r.get("DirName"):
                name = r["DirName"].strip("/") + "/" + name
            files.append((name, fid, base + r["FileOffset"], r["FileSize"],
                          r.get("ExtractSize") or r["FileSize"]))
    elif h.get("ItocOffset"):
        it = _table(read, h["ItocOffset"], h["ItocSize"] + 0x10)[0]
        entries = []
        for key in ("DataL", "DataH"):
            if isinstance(it.get(key), bytes) and it[key]:
                entries += utf_rows(it[key])
        entries.sort(key=lambda e: e["ID"])
        align = h.get("Align") or 0x800
        off = h["ContentOffset"]
        for e in entries:
            files.append(("%04d" % e["ID"], e["ID"], off, e["FileSize"], e["ExtractSize"]))
            off += (e["FileSize"] + align - 1) // align * align
    else:
        raise ValueError("CPK has neither TOC nor ITOC")
    return files


def mem_reader(data):
    return lambda off, size: data[off:off + size]


def cpk_entries_mem(data):
    """[(name, id, decompressed data)] for an in-memory CPK."""
    out = []
    for name, fid, off, size, _ in list_cpk(mem_reader(data)):
        blob = data[off:off + size]
        if blob[:8] == b"CRILAYLA":
            blob = crilayla_decompress(blob)
        out.append((name, fid, blob))
    return out
