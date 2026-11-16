"""
Compare two extractions (two releases, or two versions of the tool) by their files,
leaving out what is expected to differ: the entry / part numbers at the start of the
names and the language suffixes (_jp, _en, _es, _fr, _de, _it).

    python3 tools/compare_outputs.py files-jp/.../packfile_out files-eu/.../packfile_out

Lists the files of one side that have no counterpart on the other (grouped by folder,
numbers shown as N, languages as _LANG), then a count per file type on each side.
Nothing listed = the same kinds of files in the same places.
"""
import collections
import os
import re
import sys

LANG = re.compile(r"_(jp|en|es|fr|de|it)(?=[._]|$)")
NUMBER = re.compile(r"^\d{5}(?:_\d{3})*")
SKIP = {"index.csv", "unnamed.txt"}


def normal(rel):
    parts = []
    for part in rel.split("/"):
        part = NUMBER.sub("N", part)
        part = LANG.sub("_LANG", part)
        parts.append(part)
    return "/".join(parts)


def scan(root):
    files, types = set(), collections.Counter()
    for folder, _, names in os.walk(root):
        for name in names:
            if name in SKIP:
                continue
            rel = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
            files.add(normal(rel))
            types[os.path.splitext(name)[1] or "(none)"] += 1
    return files, types


def report(title, paths):
    if not paths:
        return
    print("%s: %d" % (title, len(paths)))
    groups = collections.defaultdict(list)
    for path in sorted(paths):
        groups[os.path.dirname(path)].append(os.path.basename(path))
    for folder, names in sorted(groups.items()):
        shown = ", ".join(names[:6]) + (" ... (%d)" % len(names) if len(names) > 6 else "")
        print("  %s/  %s" % (folder, shown))


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    for root in sys.argv[1:]:
        if not os.path.isdir(root) or not os.listdir(root):
            sys.exit("%s: no such folder, or empty (is the extraction finished?)" % root)
    (a, ta), (b, tb) = scan(sys.argv[1]), scan(sys.argv[2])
    report("Only in the first", a - b)
    report("Only in the second", b - a)
    if a == b:
        print("Same files (numbers and languages aside).")
    print("\nFiles per type (first / second):")
    for ext in sorted(set(ta) | set(tb)):
        print("  %-8s %7d / %d" % (ext, ta[ext], tb[ext]))


if __name__ == "__main__":
    main()
