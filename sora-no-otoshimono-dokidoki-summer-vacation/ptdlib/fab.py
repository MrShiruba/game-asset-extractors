"""FANM (.fab) / FSCN (.fsb): 2D animations and menu scenes.

    0x00 char[4] 'FANM' (animation) or 'FSCN' (scene)
    0x04 u32     file size
    0x0C u32     offset of the first embedded texture
    0x1C u32     texture name table: one u16 per texture, offset into the names
    0x20 u32     texture names (NUL-terminated, Shift-JIS); the table ends here

Embedded textures are complete GIM files ('MIG.00.1PSP') stored back to back,
in the same order as the names. Each GIM's size is u32 at +0x14 plus 0x10.
Some files only reference external .gim files and embed nothing.
The layout / animation data itself is not decoded yet.

The name list also holds references to other animations ('*.anm', loaded as
.fab); those have no embedded data and are skipped when pairing names with
textures. Texture names usually end in .tm2 (or .gim) and can be relative paths in Windows style,
e.g. '..\\bg.tm2' in commu/10_ending/ending_a/ed_a.fsb. Only the final name is
kept, so files always stay inside the <name>_tex folder.
"""
import os
import re
import struct
import sys

from .util import write_file

MAGICS = (b'FANM', b'FSCN')
GIM_MAGIC = b'MIG.00.1PSP'


def texture_names(data):
    """Texture names from the header's name table, or None if it looks invalid."""
    if len(data) < 0x24:
        return None
    table, base = struct.unpack_from('<II', data, 0x1C)
    if not (0 < table < base <= len(data)) or (base - table) % 2:
        return None
    names = []
    for off in struct.unpack_from('<%dH' % ((base - table) // 2), data, table):
        start = base + off
        end = data.find(b'\0', start)
        if start >= len(data) or end < 0:
            return None
        names.append(data[start:end].decode('cp932', 'replace'))
    return names


def safe_name(name, k):
    """Keep only the file name of a (possibly relative, '\\' or '/') path."""
    base = os.path.splitext(re.split(r'[\\/]', name)[-1])[0].strip()
    return base if base and base not in ('.', '..') else 'tex_%02d' % k


def textures(data):
    """Return (texture_names_found, [(name_without_ext, gim_bytes)]) for the embedded GIMs."""
    starts = [m.start() for m in re.finditer(re.escape(GIM_MAGIC), data)]
    # '.anm' entries are references to other animations (.fab), not textures
    names = [n for n in texture_names(data) or [] if not n.lower().endswith('.anm')]
    out, used = [], set()
    for k, s in enumerate(starts):
        size = struct.unpack_from('<I', data, s + 0x14)[0] + 0x10
        base = safe_name(names[k], k) if k < len(names) else 'tex_%02d' % k
        name, dup = base, 2
        while name.lower() in used:              # two paths with the same file name
            name = '%s_dup%d' % (base, dup)
            dup += 1
        used.add(name.lower())
        out.append((name, data[s:s + size]))
    return len(names), out


def convert(path, data, lower=True):
    """Write embedded textures to <name>_tex/*.gim. Returns the file count."""
    nnames, texs = textures(data)
    if texs and nnames != len(texs):
        print('  ! %s: %d texture names for %d embedded textures'
              % (path, nnames, len(texs)), file=sys.stderr)
    outdir = os.path.splitext(path)[0] + '_tex'
    for name, gim in texs:
        write_file(os.path.join(outdir, (name.lower() if lower else name) + '.gim'), gim)
    return len(texs)
