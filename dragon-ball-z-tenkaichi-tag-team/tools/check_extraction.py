"""
Check that an extraction has every file of its release, from the list of the release:

    python3 tools/check_extraction.py docs/entries_ULUS10537.csv files-us/.../packfile_out

Every row of the list that is not empty must have its file or folder in the extraction
(found by the numbers at the start of the names, anywhere in the folders); an
archive with nothing in it has no folder and is not looked for. A sound bank
(.pbd + .phd parts) counts as there when its folder of .vag (or its .pbd / .phd) is.
Lists the missing rows; nothing listed = nothing missing. For an extraction made with
or without --txt / --png (not --no-unpack).
"""
import csv
import os
import re
import sys

ID = re.compile(r"^\d{5}(?:_\d{3})*")


def found_ids(root):
    """Ids at the start of every file / folder name, with all their shorter forms (the
    slot numbers of the .vag files look like part numbers)."""
    found = set()
    for _, folders, files in os.walk(root):
        for name in folders + files:
            m = ID.match(name)
            if not m:
                continue
            numbers = m.group(0).split("_")
            for n in range(1, len(numbers) + 1):
                found.add("_".join(numbers[:n]))
    return found


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f, delimiter=";")]


def bank_id(row, rows_by_id, children):
    """Id the extractor gives the folder of a sound bank: the entry when the entry is
    the bank alone, else the .pbd part."""
    ident = row["id"]
    parent, k = ident.rsplit("_", 1)
    if row["type"] == "phd":
        ident = "%s_%03d" % (parent, int(k) - 1)
    if "_" not in parent and children.get(parent, 0) == 2:
        return parent
    return ident


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    listing, root = sys.argv[1:]
    if not os.path.isdir(root) or not os.listdir(root):
        sys.exit("%s: no such folder, or empty (is the extraction finished?)" % root)
    rows = read_rows(listing)
    rows_by_id = {row["id"]: row for row in rows}
    children = {}
    for row in rows:
        if "_" in row["id"]:
            parent = row["id"].rsplit("_", 1)[0]
            children[parent] = children.get(parent, 0) + 1
    # an archive whose parts are all empty has no folder: nothing to look for
    filled = set()
    for row in rows:
        if row["type"] not in ("empty", "archive"):
            numbers = row["id"].split("_")
            filled.update("_".join(numbers[:n]) for n in range(1, len(numbers) + 1))
    found = found_ids(root)
    missing, checked = [], 0
    for row in rows:
        if row["type"] == "empty" or row["type"] == "archive" and row["id"] not in filled:
            continue
        checked += 1
        ident = row["id"]
        if row["type"] in ("pbd", "phd"):
            ident = bank_id(row, rows_by_id, children)
        if ident not in found:
            missing.append(row)
    for row in missing:
        print("missing: %s %s (%s)" % (row["id"], row["name"], row["type"]))
    print("%d rows checked, %d missing" % (checked, len(missing)))
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
