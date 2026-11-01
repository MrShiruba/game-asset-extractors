"""Step 1: (recursive) extraction of fs_data.cpk and nested CPKs."""
import os
import struct

from .cpk import cpk_entries_mem
from .crilayla import crilayla_decompress
from .filetypes import guess_ext, safe
from .swif import swif_kind, unwrap_swif
from .text import is_message_table, message_txt


def write_tree(blob, dest_noext, keep_cpk, problems, depth=0, unwrap=True):
    """Writes blob; if it is a CPK, extracts it into dest_noext/ (recursively).

    keep_cpk: False, True (keep every raw CPK too) or "awb" (only sound banks).
    """
    ext = guess_ext(blob)
    if ext == ".cpk" and depth < 8:
        try:
            entries = cpk_entries_mem(blob)
        except Exception as e:
            problems.append("%s.cpk: unreadable CPK (%s), kept raw" % (dest_noext, e))
        else:
            # keep_cpk: True = keep every raw CPK, "awb" = keep only the CPKs
            # that are sound banks (all entries are waveforms): they are the
            # streamed .awb files of the ACBs and vgmstream can play them.
            is_awb = bool(entries) and all(guess_ext(sub) in (".adx", ".bcwav", ".hca")
                                           for _, _, sub in entries)
            if keep_cpk is True or (keep_cpk == "awb" and is_awb):
                with open(dest_noext + ".cpk", "wb") as f:
                    f.write(blob)
            os.makedirs(dest_noext, exist_ok=True)
            n = 0
            for name, _, sub in entries:
                base = os.path.join(dest_noext, *[safe(x) for x in name.split("/")])
                if "." in os.path.basename(name):
                    base = os.path.splitext(base)[0]
                os.makedirs(os.path.dirname(base), exist_ok=True)
                n += write_tree(sub, base, keep_cpk, problems, depth + 1, unwrap)
            return n
    with open(dest_noext + ext, "wb") as f:
        f.write(blob)
    n = 1
    if ext == ".bin" and unwrap and is_message_table(blob):
        # game text: keep the .bin, and write a readable UTF-8 .txt next to it
        try:
            with open(dest_noext + ".txt", "w", encoding="utf-8", newline="\n") as f:
                f.write(message_txt(blob))
            n += 1
        except (ValueError, struct.error) as e:
            problems.append("%s.bin: text export failed (%s)" % (dest_noext, e))
    if ext == ".swif" and unwrap:
        # texture SWIF: keep it, and write the .bcres it wraps next to it (bytes
        # unchanged). Layout SWIFs hold no image data: nothing to unwrap.
        try:
            kind = swif_kind(blob)
            parts = unwrap_swif(blob) if kind == "texture" else []
            if kind == "unknown":
                problems.append("%s.swif: unknown SWIF kind" % dest_noext)
        except (ValueError, struct.error) as e:
            problems.append("%s.swif: %s" % (dest_noext, e))
            parts = []
        for k, part in enumerate(parts):
            suffix = "" if len(parts) == 1 else "_%d" % k
            with open(dest_noext + suffix + ".bcres", "wb") as f:
                f.write(part)
            n += 1
    return n


def job_extract(job):
    cpk, dest_noext, off, size, ext_size, keep_cpk, unwrap = job
    problems = []
    with open(cpk, "rb") as f:
        f.seek(off)
        blob = f.read(size)
    if blob[:8] == b"CRILAYLA":
        try:
            blob = crilayla_decompress(blob)
        except Exception as e:
            problems.append("%s: CRILAYLA failure (%s), kept raw" % (dest_noext, e))
    n = write_tree(blob, dest_noext, keep_cpk, problems, unwrap=unwrap)
    return n, problems
