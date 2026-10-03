#!/usr/bin/env python3
"""
zb_extract.py - Extractor for DreamMix TV World Fighters ".zb" archives
(GameCube: scfight.zb / PlayStation 2: SCFIGHT.ZB, IRXZ.ZB).

Usage:
    python zb_extract.py scfight.zb                 # extract to ./scfight/
    python zb_extract.py scfight.zb -o out_dir      # extract to out_dir/
    python zb_extract.py scfight.zb --list          # only print the file table
    python zb_extract.py scfight.zb --keep-prefix   # keep the full /home/project/... path

The GameCube and PS2 versions use the exact same archive format (big-endian
on both consoles), so the same code handles both.

No executable is needed: the TOC decryption algorithm and its constants were
reverse-engineered from main.dol (GKWJ18, hi_fileio.c) and are embedded here.

Archive layout (all integers big-endian)
----------------------------------------
Header (0x20 bytes, plaintext):
    0x00 u32  magic       = 0x0131A36E (20030318)
    0x04 u32  version     = 0x32
    0x08 u32  file_count
    0x0C u32  toc_size    (TOC runs from 0x20 to 0x20 + toc_size)
    0x10 u32  key_ab      (seed: high 16 bits = A, low 16 bits = B)
    0x14 u32  key_k       (seed: K)
    0x18 u32  timestamp   (time_t)
    0x1C u32  timestamp   (time_t, duplicate)

TOC entry (repeated file_count times), encrypted with a keystream:
    cstring   path        (each char XORed with low byte of keystream,
                           unless the char already equals that byte;
                           the NUL terminator is not encrypted)
    u32       flags       ^ K  -> low byte: 'z' (0x7A) = zlib, 'n' = stored
    u32       raw_size    ^ K
    u32       stored_size ^ K
    u32       offset      ^ K  (absolute offset in the archive)
    u32       unknown     (plaintext)
    u32       unknown     (plaintext)
    cstring   extra       (encrypted like path, usually empty)

Every encrypted byte/word advances the keystream by exactly one step.
File data is not encrypted: it is either stored as-is or a raw zlib stream.
"""

import argparse
import os
import struct
import sys
import zlib

MAGIC = 0x0131A36E
HEADER_SIZE = 0x20
# Development path prefixes stripped by default.
# GameCube: /home/project/ScFight/GCN/masterdata/...
# PS2:      /home/project/ScFight/masterdata/...  and  /home/project/ScFight/program/modules/...
DEFAULT_PREFIXES = ("/home/project/ScFight/GCN/", "/home/project/ScFight/")

# LFSR constants (table at 0x80208688 in main.dol, entries 18..23)
A_TAP1, A_TAP2, A_MASK = 0x0008, 0x4000, 0x7FFF
B_TAP1, B_TAP2, B_MASK = 0x0004, 0x4000, 0x7FFF


class KeyStream:
    """Stream cipher built from two small LFSR-like registers (A, B) feeding K."""

    def __init__(self, key_ab, key_k):
        self.a = key_ab >> 16
        self.b = key_ab & 0xFFFF
        self.k = key_k

    def next(self):
        a, b = self.a, self.b

        bit = 1 if (a & A_TAP1) == A_TAP1 else 0
        if (a & A_TAP2) == A_TAP2:
            bit ^= 1
        a = A_MASK & ((2 * a + (bit ^ 1)) & 0xFFFFFFFF)

        bit = 1 if (b & B_TAP1) == B_TAP1 else 0
        if (b & B_TAP2) == B_TAP2:
            bit ^= 1
        b = B_MASK & ((2 * b + (bit ^ 1)) & 0xFFFFFFFF)

        a = (5 * a + 1) & 0xFFFFFFFF
        b = (5 * b + 1) & 0xFFFFFFFF
        self.a, self.b = a, b
        self.k = (self.k ^ (a | (b << 15))) & 0xFFFFFFFF
        return self.k


class Reader:
    def __init__(self, data, pos):
        self.data = data
        self.pos = pos

    def u32(self):
        v = struct.unpack_from(">I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def cstring(self):
        end = self.data.index(b"\0", self.pos)
        s = bytearray(self.data[self.pos:end])
        self.pos = end + 1
        return s


def decrypt_string(buf, ks):
    for i in range(len(buf)):
        k = ks.next() & 0xFF
        if buf[i] != k:
            buf[i] ^= k
    return bytes(buf).decode("latin-1")


def read_toc(data):
    magic, version, count, toc_size, key_ab, key_k, ts1, ts2 = struct.unpack_from(">8I", data, 0)
    if magic != MAGIC:
        raise ValueError("bad magic 0x%08X (expected 0x%08X): not a scfight.zb archive" % (magic, MAGIC))
    if version != 0x32:
        print("warning: unexpected version 0x%X" % version, file=sys.stderr)

    ks = KeyStream(key_ab, key_k)
    r = Reader(data, HEADER_SIZE)
    entries = []
    for _ in range(count):
        path = decrypt_string(r.cstring(), ks)
        flags = (r.u32() ^ ks.next()) & 0xFF
        raw_size = r.u32() ^ ks.next()
        stored_size = r.u32() ^ ks.next()
        offset = r.u32() ^ ks.next()
        unk1 = r.u32()
        unk2 = r.u32()
        extra = decrypt_string(r.cstring(), ks)
        entries.append({
            "path": path,
            "compressed": flags == ord("z"),
            "flags": flags,
            "raw_size": raw_size,
            "stored_size": stored_size,
            "offset": offset,
            "unk1": unk1,
            "unk2": unk2,
            "extra": extra,
        })

    if r.pos != HEADER_SIZE + toc_size:
        print("warning: TOC ended at 0x%X, header says 0x%X" % (r.pos, HEADER_SIZE + toc_size), file=sys.stderr)
    return entries


def safe_relpath(path, prefixes):
    for prefix in prefixes:
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    parts = [p for p in path.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return os.path.join(*parts) if parts else None


def main():
    ap = argparse.ArgumentParser(description="Extract DreamMix TV World Fighters .zb archives (GameCube and PS2).")
    ap.add_argument("archive", help="path to the .zb archive (scfight.zb, SCFIGHT.ZB, IRXZ.ZB)")
    ap.add_argument("-o", "--output", help="output directory (default: <archive name> without extension)")
    ap.add_argument("-l", "--list", action="store_true", help="list files without extracting")
    ap.add_argument("--keep-prefix", action="store_true",
                    help="keep the full original path (/home/project/ScFight/...)")
    args = ap.parse_args()

    with open(args.archive, "rb") as f:
        data = f.read()

    entries = read_toc(data)
    prefixes = () if args.keep_prefix else DEFAULT_PREFIXES

    if args.list:
        try:
            for e in entries:
                print("%s  %10d  %10d  0x%08X  %s" % (
                    "z" if e["compressed"] else "-", e["raw_size"], e["stored_size"], e["offset"], e["path"]))
            print("%d files" % len(entries))
        except BrokenPipeError:
            pass
        return 0

    out_dir = args.output or os.path.splitext(os.path.basename(args.archive))[0]
    errors = 0
    for e in entries:
        rel = safe_relpath(e["path"], prefixes)
        if rel is None:
            print("skip: empty path", file=sys.stderr)
            errors += 1
            continue
        blob = data[e["offset"]:e["offset"] + e["stored_size"]]
        if e["compressed"]:
            try:
                blob = zlib.decompress(blob)
            except zlib.error as ex:
                print("error: %s: %s" % (e["path"], ex), file=sys.stderr)
                errors += 1
                continue
        if len(blob) != e["raw_size"]:
            print("warning: %s: size %d != expected %d" % (e["path"], len(blob), e["raw_size"]), file=sys.stderr)
        dest = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(blob)

    print("extracted %d/%d files to %s" % (len(entries) - errors, len(entries), out_dir))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
