"""Reads the table of contents of a CGFX (.bcres) file: models, textures..."""
import struct

KINDS = ["models", "textures", "luts", "materials", "shaders", "cameras", "lights",
         "fog", "environments", "skeletal_anims", "texture_anims", "visibility_anims",
         "camera_anims", "light_anims", "emitters"]


def cgfx_contents(blob):
    """Returns {kind: [names]} for the non-empty dictionaries of a CGFX file."""
    if blob[:4] != b"CGFX":
        raise ValueError("not a CGFX file")
    hsize, = struct.unpack_from("<H", blob, 6)
    if blob[hsize:hsize + 4] != b"DATA":
        raise ValueError("DATA block not found")
    out = {}
    for i, kind in enumerate(KINDS):
        p = hsize + 8 + i * 8
        count, rel = struct.unpack_from("<Ii", blob, p)
        if not count:
            continue
        dic = p + 4 + rel
        if blob[dic:dic + 4] != b"DICT":
            raise ValueError("bad %s dictionary" % kind)
        names = []
        for e in range(count):
            q = dic + 0x1C + e * 0x10 + 8          # name offset field of entry e
            s = q + struct.unpack_from("<i", blob, q)[0]
            names.append(blob[s:blob.index(b"\0", s)].decode("ascii", "replace"))
        out[kind] = names
    return out


def cgfx_category(contents):
    """'models', 'animations', 'textures', 'scenes' (cameras, lights, colour
    tables...) or 'other' for a CGFX table of contents."""
    if contents.get("models"):
        return "models"
    if any(k.endswith("_anims") for k in contents):
        return "animations"
    if contents.get("textures"):
        return "textures"
    if contents.get("cameras") or contents.get("lights") or contents.get("fog") \
            or contents.get("environments") or contents.get("luts"):
        return "scenes"
    return "other"


def cgfx_label(contents):
    """Short name for the file: its first model, else first texture, else anything."""
    for kind in ["models", "textures"] + KINDS:
        if contents.get(kind):
            return contents[kind][0]
    return ""
