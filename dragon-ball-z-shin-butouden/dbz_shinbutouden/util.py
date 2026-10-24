"""Input handling: game files and/or folders are both accepted."""
import os


def iter_inputs(paths):
    """Yield (path, relative_path) for every file.

    A folder is walked recursively and relative paths keep its structure
    (END/EDPCM0.PCM, KOJIN/GOKU18.PCM...). A file given on its own keeps only
    its name.
    """
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs.sort()
                for n in sorted(names):
                    full = os.path.join(root, n)
                    yield full, os.path.relpath(full, p)
        elif os.path.isfile(p):
            yield p, os.path.basename(p)
        else:
            print("  ! not found: %s" % p)


def stem(rel):
    """KOJIN/GOKU18.PCM -> KOJIN/GOKU18"""
    return rel.rsplit('.', 1)[0] if '.' in os.path.basename(rel) else rel
