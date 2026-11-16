"""
Compare two PACKFILE.BIN entry by entry (same 14097-entry table in every release):

    python3 tools/compare_packfiles.py US/PACKFILE.BIN EU/PACKFILE.BIN

Prints, for the entries whose data differ, the entry number and name and how they
differ (only in the first file, only in the second, or different bytes), then a count.
Entries are compared decompressed. BBQ scripts are compared without their build time
(u32 at +8): a rebuilt but unchanged script counts as the same.

    python3 tools/compare_packfiles.py --parts US/PACKFILE.BIN EU/PACKFILE.BIN

also goes into the archives of the entries that differ and lists the parts that
differ (part numbers as in the extracted file names: NNNNN_KKK_MMM).
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tttpack import archive, names          # noqa: E402
from tttpack.formats import unwrap_zlib      # noqa: E402
from tttpack.packfile import PackFile        # noqa: E402


def normal(data):
    """Bytes as compared: decompressed, BBQ build time zeroed."""
    inflated = unwrap_zlib(data)
    if inflated is not None:
        data = inflated
    if data[:8] == b".BBQ1.00" and len(data) >= 12:
        data = data[:8] + bytes(4) + data[12:]
    return data


def digest(data):
    return hashlib.sha1(normal(data)).hexdigest()


def digests(path):
    pack = PackFile(path)
    out = []
    for entry in pack.entries:
        if entry.size == 0:
            out.append(None)
            continue
        try:
            out.append((entry.size, digest(pack.read(entry))))
        except Exception as ex:          # unreadable entry: compare its error
            out.append((entry.size, "error %s" % ex))
    return pack, out


def part_differences(a, b, prefix, depth=0):
    """Lines for the parts that differ between two versions of an archive."""
    a, b = normal(a), normal(b)
    pa, pb = archive.parts(a), archive.parts(b)
    if depth >= archive.MAX_DEPTH or pa is None or pb is None:
        return ["      %s  %d / %d bytes" % (prefix, len(a), len(b))]
    lines = []
    if len(pa) != len(pb):
        lines.append("      %s  %d / %d parts" % (prefix, len(pa), len(pb)))
    for k in range(max(len(pa), len(pb))):
        x = pa[k] if k < len(pa) else b""
        y = pb[k] if k < len(pb) else b""
        if digest(x) != digest(y):
            if not x or not y:
                lines.append("      %s_%03d  %s" % (prefix, k, "only in first" if x else "only in second"))
            else:
                lines += part_differences(x, y, "%s_%03d" % (prefix, k), depth + 1)
    return lines


def main():
    args = [x for x in sys.argv[1:] if x != "--parts"]
    deep = "--parts" in sys.argv[1:]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    (pack_a, a), (pack_b, b) = digests(args[0]), digests(args[1])
    counts = {"same": 0, "only in first": 0, "only in second": 0, "different": 0}
    for index in range(max(len(a), len(b))):
        x = a[index] if index < len(a) else None
        y = b[index] if index < len(b) else None
        if x == y:
            if x is not None:
                counts["same"] += 1
            continue
        kind = "only in first" if y is None else "only in second" if x is None else "different"
        counts[kind] += 1
        sizes = "%s / %s" % (x[0] if x else "-", y[0] if y else "-")
        print("%05d  %-28s %-15s sizes %s" % (index, names.entry(index) or "", kind, sizes))
        if deep and kind == "different":
            for line in part_differences(pack_a.read(pack_a.entries[index]),
                                         pack_b.read(pack_b.entries[index]), "%05d" % index):
                print(line)
    print("; ".join("%s: %d" % item for item in counts.items()))


if __name__ == "__main__":
    main()
