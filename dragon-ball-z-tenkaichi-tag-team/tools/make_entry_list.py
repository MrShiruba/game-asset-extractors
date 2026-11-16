"""
List every entry and sub-entry of one PACKFILE.BIN, with the names the extractor gives:

    python3 tools/make_entry_list.py files-jp/PSP_GAME/USRDIR/PACKFILE.BIN

writes docs/entries_<game id>.csv (game id read from PSP_GAME/PARAM.SFO next to the
PACKFILE, e.g. ULJS00311; or given with --id ULJS00311). Nothing is extracted.

Every release lists the same 14097 entries (an entry a release does not use is there
with type "empty" and size 0: 00048_training_jp in the EU / US releases); the parts
of an archive follow it, one level down per "_KKK".

Columns:
    id       entry number, then part numbers: 01427, 01427_002, 01427_495_005
    name     the name of the extracted file or folder, without numbers or extension
    type     extension of the extracted file, "archive", "empty"
    offset   entries: byte offset in PACKFILE.BIN; parts: byte offset in the data of
             their archive (after decompression when that archive is compressed)
    size     bytes as stored there (compressed size for a compressed entry / part)
To extract, read the tables of the file (FORMATS.md, section PACKFILE.BIN): these columns
are for looking at the data (hex editor, comparing releases), they differ in every
release.
"""
import argparse
import collections
import csv
import os
import struct
import sys
import zlib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from tttpack import archive, names                              # noqa: E402
from tttpack import layout as layout_rules                       # noqa: E402
from tttpack.extract import PADDING_ENTRY, output_path, read_intro, read_story  # noqa: E402
from tttpack.formats import guess_ext, screens, unwrap_zlib     # noqa: E402
from tttpack.packfile import PackFile                           # noqa: E402
from tttpack.sound_bank import sound_bank_pair                  # noqa: E402
from tttpack import texture                                     # noqa: E402


def game_id(packfile):
    """DISC_ID of PSP_GAME/PARAM.SFO next to PSP_GAME/USRDIR/PACKFILE.BIN, or None."""
    sfo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(packfile))), "PARAM.SFO")
    try:
        with open(sfo, "rb") as f:
            data = f.read()
        if data[:4] != b"\0PSF":
            return None
        keys, values, count = struct.unpack_from("<III", data, 8)
        for k in range(count):
            key_at, _, length, _, value_at = struct.unpack_from("<HHIII", data, 0x14 + 16 * k)
            key = data[keys + key_at:data.index(b"\0", keys + key_at)]
            if key == b"DISC_ID":
                return data[values + value_at:values + value_at + length].rstrip(b"\0").decode()
    except (OSError, ValueError, struct.error):
        return None
    return None


def short_name(path):
    """File name without folders, leading numbers and extension."""
    base = os.path.basename(path)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    parts = stem.split("_")
    while parts and parts[0].isdigit():
        parts.pop(0)
    return "_".join(parts)


def part_rows(data, layout, ident, out):
    """Rows of the parts of an archive (data decompressed), from its unpack() layout."""
    count = struct.unpack_from(">I", data, 0)[0]
    offsets = struct.unpack_from(">%dI" % (count + 1), data, 4)
    for k, node in enumerate(layout):
        sub = "%s_%03d" % (ident, k)
        start, end = offsets[k], offsets[k + 1]
        raw = data[start:end]
        if node is None:
            out.append([sub, "", "empty", start, 0])
            continue
        unpacked = unwrap_zlib(raw) if node.get("zlib") else None
        if "arc" in node:
            inner = unpacked if unpacked is not None else raw
            name = short_name(node.get("name", ""))
            out.append([sub, name, "archive", start, len(raw)])
            part_rows(inner, node["arc"], sub, out)
        elif "file" in node:
            ext = node["file"].rsplit(".", 1)[-1]
            out.append([sub, short_name(node["file"]), ext, start, len(raw)])
        else:                                   # compressed part that is empty
            out.append([sub, "", "empty", start, len(raw)])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("packfile")
    p.add_argument("--id", help="game id for the file name (default: read from PARAM.SFO)")
    p.add_argument("-o", "--output", default=os.path.join(ROOT, "docs"))
    args = p.parse_args()
    ident_game = args.id or game_id(args.packfile)
    if not ident_game:
        sys.exit("game id not found (PSP_GAME/PARAM.SFO): give it with --id ULJS00311")

    archive.DRY_RUN = True
    pack = PackFile(args.packfile)
    story, intro = read_story(pack), read_intro(pack)
    rows = []
    for entry in pack.entries:
        ident = "%05d" % entry.index
        offset = pack.offset(entry)
        label = names.entry(entry.index)
        if entry.size == 0:
            rows.append([ident, names.shown(label) or label or "", "empty", offset, 0])
            continue
        stored = entry.packed_size or entry.size
        try:
            data = pack.read(entry)
        except (ValueError, zlib.error):
            rows.append([ident, label or "", "unreadable", offset, stored])
            continue
        ext = guess_ext(data)
        is_archive = ext == "bin" and archive.parts(data) is not None
        if is_archive:
            folder = "%s/%s" % (layout_rules.entry_folder(entry.index, label, "arc"), ident)
            shown = names.shown(label)
            rows.append([ident, shown or "", "archive", offset, stored])
            if sound_bank_pair(data):
                layout = [{"file": "x/%s_000_sounds.pbd" % ident}, {"file": "x/%s_001_sounds.phd" % ident}]
            else:
                layout = archive.unpack(data, folder, ident, types=collections.Counter(), png=False,
                                        index=entry.index, root=".")
            part_rows(data, layout, ident, rows)
            continue
        if ext == "bin":
            if entry.index == PADDING_ENTRY:
                ext = "padding"
            elif texture.decode(data) is not None:
                ext = "tex"
            elif screens(data):
                ext = "fb"
        path = output_path(entry.index, ext, story, intro, label)
        rows.append([ident, short_name(path), ext, offset, stored])

    os.makedirs(args.output, exist_ok=True)
    target = os.path.join(args.output, "entries_%s.csv" % ident_game)
    with open(target, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "name", "type", "offset", "size"])
        w.writerows(rows)
    print("%s: %d rows (%d entries)" % (target, len(rows), len(pack.entries)))


if __name__ == "__main__":
    main()
