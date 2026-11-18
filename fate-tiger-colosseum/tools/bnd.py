"""BND archive reader for Fate/tiger colosseum (PSP, ULJM05266).

See docs/formats.md for the full format description.
"""
import os
import struct
import sys

MAGIC = b"BND\0"


class BND:
    """A BND archive located at `base` inside the open binary file `f`."""

    def __init__(self, f, base=0):
        self.f, self.base = f, base
        f.seek(base)
        hdr = f.read(0x28)
        if hdr[:4] != MAGIC:
            raise ValueError("not a BND archive (magic=%r) at 0x%x" % (hdr[:4], base))
        (_, self.version, self.align, self.header_size, self.names_offset,
         self.data_offset, _, _, self.file_count, self.entry_count) = struct.unpack_from("<4s9I", hdr)

        f.seek(base + 0x28)
        raw = f.read(16 * self.entry_count)
        # Entries are keyed by their offset, which is what the name table points to.
        self.entries = {}
        for i in range(self.entry_count):
            name_hash, name_off, data_off, size = struct.unpack_from("<4I", raw, 16 * i)
            self.entries[0x28 + 16 * i] = (name_hash, name_off, data_off, size)

        f.seek(base + self.names_offset)
        self.names = f.read(self.data_offset - self.names_offset)

    def files(self):
        """Return [(path, absolute_offset, size)] in name-table order."""
        out, dirs, p, n = [], {}, 0, self.names
        while p + 7 < len(n):
            depth = struct.unpack_from("<b", n, p)[0]
            rec_len = n[p + 2]
            entry_off = struct.unpack_from("<I", n, p + 3)[0]
            if depth == 0 or rec_len == 0:
                break
            end = n.index(b"\0", p + 7)
            name = n[p + 7:end].decode("ascii", "replace")
            p += rec_len

            if depth > 0:  # directory
                dirs[depth] = name
                for k in [k for k in dirs if k > depth]:
                    del dirs[k]
                continue

            parent = "".join(dirs[k] for k in sorted(dirs) if k < -depth)
            entry = self.entries.get(entry_off)
            if entry is None:
                print("  ! no entry for %s" % name, file=sys.stderr)
                continue
            out.append(((parent + name).lstrip("/"), self.base + entry[2], entry[3]))
        return out


def _copy(f, offset, size, dst):
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    f.seek(offset)
    remaining = size
    with open(dst, "wb") as o:
        while remaining:
            chunk = f.read(min(remaining, 1 << 20))
            if not chunk:
                print("  ! truncated: " + dst, file=sys.stderr)
                break
            o.write(chunk)
            remaining -= len(chunk)


def walk(f, base=0, recursive=True, depth=0):
    """Yield (depth, path, offset, size, is_nested_bnd) for every file."""
    bnd = BND(f, base)
    for path, off, size in bnd.files():
        nested = False
        if recursive and path.lower().endswith(".bnd"):
            f.seek(off)
            nested = f.read(4) == MAGIC
        yield depth, path, off, size, nested
        if nested:
            yield from walk(f, off, recursive, depth + 1)


def list_files(path, recursive=True):
    with open(path, "rb") as f:
        for depth, rel, off, size, _ in walk(f, 0, recursive):
            print("%s0x%08x %10d  %s" % ("  " * depth, off, size, rel))


def extract(path, out_dir, recursive=True, keep_nested=True):
    """Extract every file. Nested BND paths are already complete, so all files
    land in the same tree (e.g. prj/tiger/data/builded/battle/...)."""
    count = 0
    with open(path, "rb") as f:
        for _, rel, off, size, nested in walk(f, 0, recursive):
            if nested and not keep_nested:
                continue
            _copy(f, off, size, os.path.join(out_dir, rel))
            count += 1
    return count
