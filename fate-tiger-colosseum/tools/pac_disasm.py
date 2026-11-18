"""Disassembler for Fate/tiger colosseum .pac scripts.

Every instruction starts with the 4-byte marker "25 GG OO 00": GG = command group, OO =
command index inside the group. Command names and argument layouts come from the game
itself (EBOOT.BIN): names from the command registration tables, argument layouts from the
operand reads done by each command handler. They are stored in pac_opcodes.json.

Argument codes in pac_opcodes.json:
  t4  typed operand: 1 type byte, padding to 4, then a 32-bit value
  r4  raw 32-bit value (r1 / r2: raw 8 / 16-bit value)
  s   inline null-terminated Shift-JIS string
  L   string stored at the offset given by the previous raw argument (…Label commands)
Each instruction is padded to 4 bytes.

Operand types (the type byte of a "t" argument):
  0x00 / 0x01 / 0x02  integer immediate      0x10  float immediate
  0x04  local integer variable  -> i[n]      0x20  local float variable  -> f[n]
  0x08  global integer variable -> gi[n]     0x40  global float variable -> gf[n]
Local variables belong to the running script, global ones are shared by all scripts.
"""
import json
import os
import struct

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "pac_opcodes.json"), encoding="utf-8") as _f:
    GROUPS = {int(k): v for k, v in json.load(_f).items()}

VAR_NAMES = {0x04: "i", 0x08: "gi", 0x20: "f", 0x40: "gf"}
# Commands whose layout is decided at run time.
OVERRIDES = {(0, "cmd_inxJmp"): ["t4"]}  # followed by a table of u32 jump offsets
JUMPS = {"cmd_jmp", "cmd_call", "cmd_loop", "cmd_resJmp", "cmd_resCall"}


def _is_marker(d, p):
    if p + 4 > len(d) or d[p] != 0x25 or d[p + 3] != 0:
        return False
    g, o = d[p + 1], d[p + 2]
    return g in GROUPS and o < len(GROUPS[g]["ops"])


def command_name(group, op):
    g = GROUPS[group]
    name = g["ops"][op]["name"]
    return name if group in (0, 1, 2) else "%s.%s" % (g["name"], name)


def _f32(v):
    return struct.unpack("<f", struct.pack("<I", v))[0]


def _raw(v, floaty):
    e = (v >> 23) & 0xff
    if floaty and v and 100 < e < 160:
        return "%g" % _f32(v)
    return str(v - (1 << 32)) if v >= 0x80000000 else ("0x%x" % v if v > 0xffff else str(v))


def _cstr(d, off):
    end = d.find(b"\0", off)
    if end < 0:
        return None, len(d)
    try:
        return d[off:end].decode("cp932"), end + 1
    except UnicodeDecodeError:
        return None, end + 1


def _args(group, op):
    entry = GROUPS[group]["ops"][op]
    return OVERRIDES.get((group, entry["name"]), entry["args"])


def decode(d, p):
    """Decode the instruction at p. Returns (end_offset, text, string_refs)."""
    g, o = d[p + 1], d[p + 2]
    name = GROUPS[g]["ops"][o]["name"]
    q, out, refs, last_raw = p + 4, [], [], None
    for a in _args(g, o):
        if a == "s":
            text, q = _cstr(d, q)
            out.append('"%s"' % text if text is not None else '"?"')
            continue
        if a == "L":
            text, _ = _cstr(d, last_raw) if last_raw is not None and last_raw < len(d) else (None, 0)
            refs.append(last_raw)
            out[-1] += ' "%s"' % (text if text is not None else "?")
            continue
        kind, size = a[0], int(a[1])
        t = None
        if kind == "t":
            t = d[q]
            q += 1
        if size > 1:
            q = (q + size - 1) // size * size
        v = int.from_bytes(d[q:q + size], "little")
        q += size
        if kind == "t":
            if t in VAR_NAMES:
                out.append("%s[%d]" % (VAR_NAMES[t], v))
            elif t == 0x10:
                out.append("%g" % _f32(v))
            else:
                out.append(_raw(v, False))
        else:
            last_raw = v
            if name in JUMPS or name.startswith("cmd_if") or name.startswith("selectMenuItem"):
                out.append("->0x%x" % v)
            else:
                out.append("0x%x" % v if a == "r4" and name.endswith("Label") else _raw(v, g in (4, 5)))
    q = (q + 3) & ~3
    return q, ", ".join(out), refs


def string_pool_start(d):
    """Strings used by …Label commands sit after the code: the lowest one marks its end."""
    end = len(d)
    p = 0
    while p + 4 <= end:
        if not _is_marker(d, p):
            p += 4
            continue
        q, _, refs = decode(d, p)
        for r in refs:
            if r is not None and p < r < end:
                end = r
        p = q if q > p else p + 4
    return end


def disassemble(path):
    """Return a list of text lines."""
    d = open(path, "rb").read()
    end = string_pool_start(d)
    lines, p = [], 0
    while p + 4 <= end:
        if not _is_marker(d, p):
            start = p
            while p + 4 <= end and not _is_marker(d, p):
                p += 4
            words = struct.unpack_from("<%dI" % ((p - start) // 4), d, start)
            prev = lines[-1] if lines else ""
            if "cmd_inxJmp" in prev:
                lines.append("%06x  .jumptable %s" % (start, " ".join("->0x%x" % w for w in words)))
            else:
                lines.append("%06x  .data %s" % (start, " ".join("%08x" % w for w in words)))
            continue
        q, text, _ = decode(d, p)
        lines.append("%06x  %-45s %s" % (p, command_name(d[p + 1], d[p + 2]), text))
        p = q
    if end < len(d):
        lines.append("%06x  ; --- string pool (%d bytes) ---" % (end, len(d) - end))
    return lines


# cmd_XXX.pac files use a separate 8-instruction interpreter (see docs/formats.md).
CMD_OPS = {1: ("entry", 3), 2: ("nop", 0), 3: ("pad", 4), 4: ("state", 2), 5: ("then", 0),
           6: ("commit", 1), 7: ("action", 10), 8: ("param", None)}


def disassemble_cmd(path):
    d = open(path, "rb").read()
    hdr = struct.unpack_from("<5I", d, 0)
    lines = ["000000  .header actions=0x%x entries=0x%x params=0x%x (0x%x, 0x%x)"
             % (hdr[0], hdr[3], hdr[4], hdr[1], hdr[2])]
    p = 0x14
    while p + 4 <= len(d):
        op = struct.unpack_from("<H", d, p + 2)[0]
        if d[p] != 0x25 or d[p + 1] != 0 or op not in CMD_OPS:
            start = p
            while p + 4 <= len(d) and not (d[p] == 0x25 and d[p + 1] == 0 and
                                           struct.unpack_from("<H", d, p + 2)[0] in CMD_OPS):
                p += 4
            words = struct.unpack_from("<%dI" % ((p - start) // 4), d, start)
            lines.append("%06x  .data %s" % (start, " ".join("0x%x" % w for w in words)))
            continue
        name, n = CMD_OPS[op]
        q = p + 4
        if n is None:
            n = 0
            while q + 4 * n + 4 <= len(d) and d[q + 4 * n] != 0x25:
                n += 1
        words = struct.unpack_from("<%dI" % n, d, q) if n else ()
        if name == "pad":
            text = "pressed=%d kind=%d buttons=0x%x window=%d" % words
        elif name == "entry":
            text = "id=%d action=0x%x after=%s" % (words[0], words[1],
                                                   "any" if words[2] == 0xFFFFFFFF else "0x%x" % words[2])
        else:
            text = ", ".join(_raw(w, True) for w in words)
        lines.append("%06x  %-8s %s" % (p, name, text))
        p = q + 4 * n
    return lines


def dump(src, out_dir):
    """src: a .pac file or a folder of them. Writes <name>.asm files."""
    os.makedirs(out_dir, exist_ok=True)
    if os.path.isdir(src):
        files = sorted(os.path.join(src, f) for f in os.listdir(src) if f.endswith(".pac"))
    else:
        files = [src]
    done = {}
    for pac in files:
        base = os.path.basename(pac)
        if os.path.getsize(pac) < 8 or base.lower().endswith("idtable.pac"):
            continue  # empty AI files and plain ID tables are not bytecode
        name = os.path.splitext(base)[0]
        if name.startswith("cmd_"):
            lines = disassemble_cmd(pac)
        else:
            lines = disassemble(pac)
        if name == "param":
            lines.insert(0, "; NOTE: param.pac starts with (id, value) pairs, shown as .data.")
        with open(os.path.join(out_dir, name + ".asm"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        done[base] = len(lines)
    return done
