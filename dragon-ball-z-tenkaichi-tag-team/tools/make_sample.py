"""
Make a small PACKFILE that keeps the data of some entries only (the others become
empty), to share or test a few entries without the whole 1.6 GB file.

    python3 tools/make_sample.py PACKFILE.BIN SAMPLE.BIN 0 1436-1440 13937

The sample has the same 14097-entry table, so ttt_unpack.py extracts it with the same
names and folders as the full file.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tttpack.packfile import KEY, SECTOR, PackFile, align   # noqa: E402


def parse_indices(args):
    keep = set()
    for arg in args:
        for item in arg.split(","):
            if "-" in item:
                a, b = item.split("-")
                keep.update(range(int(a), int(b) + 1))
            elif item:
                keep.add(int(item))
    return keep


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    source, target = sys.argv[1], sys.argv[2]
    keep = parse_indices(sys.argv[3:])
    pack = PackFile(source)
    count = len(pack.entries)
    table, blobs, sector = bytearray(), [], 0
    for entry in pack.entries:
        if entry.index in keep:
            pack.f.seek(pack.offset(entry))
            raw = pack.f.read(entry.packed_size or entry.size)
            size, packed = entry.size, entry.packed_size
        else:
            raw, size, packed = b"", 0, 0
        table += struct.pack("<4I", sector ^ KEY, size ^ entry.index, packed ^ KEY,
                             entry.unknown ^ entry.index)
        blobs.append(raw + bytes(align(len(raw), SECTOR) - len(raw)))
        sector += align(len(raw), SECTOR) // SECTOR
    pack.f.seek(0)
    header = bytearray(pack.f.read(0x10))
    head = header + table
    with open(target, "wb") as out:
        out.write(head + bytes(align(len(head), 0x1000) - len(head)))
        for blob in blobs:
            out.write(blob)
    print("%s: %d of %d entries kept, %d bytes" % (target, len(keep & set(range(count))), count,
                                                 os.path.getsize(target)))


if __name__ == "__main__":
    main()
