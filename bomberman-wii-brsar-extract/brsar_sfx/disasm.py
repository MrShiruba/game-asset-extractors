"""Human-readable disassembly of NW4R sequence (MML) byte code.

Useful to understand why a sound loops, which tracks it opens, etc.
Follows calls/jumps/opentracks from the start offset.
"""

from __future__ import annotations

from typing import Dict, List, Set

NAMES = {
    0x80: "wait", 0x81: "prg", 0x88: "opentrack", 0x89: "jump", 0x8A: "call",
    0xB0: "timebase", 0xC0: "pan", 0xC1: "volume", 0xC2: "main_volume", 0xC3: "transpose",
    0xC4: "pitchbend", 0xC5: "bendrange", 0xC6: "priority", 0xC7: "notewait", 0xC8: "tie",
    0xC9: "porta", 0xCA: "mod_depth", 0xCB: "mod_speed", 0xCC: "mod_type", 0xCD: "mod_range",
    0xCE: "porta_sw", 0xCF: "porta_time", 0xD0: "attack", 0xD1: "decay", 0xD2: "sustain",
    0xD3: "release", 0xD4: "loop_start", 0xD5: "volume2", 0xD6: "printvar", 0xD7: "surround_pan",
    0xD8: "lpf_cutoff", 0xD9: "fxsend_a", 0xDA: "fxsend_b", 0xDB: "mainsend", 0xDC: "init_pan",
    0xDD: "mute", 0xDE: "fxsend_c", 0xDF: "damper", 0xE0: "mod_delay", 0xE1: "tempo",
    0xE3: "sweep_pitch", 0xFC: "loop_end", 0xFD: "ret", 0xFE: "alloctrack", 0xFF: "fin",
}
EX_NAMES = {
    0x80: "setvar", 0x81: "addvar", 0x82: "subvar", 0x83: "mulvar", 0x84: "divvar", 0x85: "shiftvar",
    0x86: "randvar", 0x87: "andvar", 0x88: "orvar", 0x89: "xorvar", 0x8A: "notvar", 0x8B: "modvar",
    0x90: "cmp_eq", 0x91: "cmp_ge", 0x92: "cmp_gt", 0x93: "cmp_le", 0x94: "cmp_lt", 0x95: "cmp_ne",
    0xE0: "userproc",
}
NOTE_NAMES = ["cn", "cs", "dn", "ds", "en", "fn", "fs", "gn", "gs", "an", "as", "bn"]


def _note(k: int) -> str:
    return f"{NOTE_NAMES[k % 12]}{k // 12 - 1}"


def disassemble(seq: bytes, start: int, max_lines: int = 2000) -> List[str]:
    lines: Dict[int, str] = {}
    todo = [start]
    seen: Set[int] = set()
    labels: Set[int] = {start}
    while todo and len(lines) < max_lines:
        pc = todo.pop()
        while pc < len(seq) and pc not in seen and len(lines) < max_lines:
            seen.add(pc)
            at = pc
            prefix = ""
            argkind = None

            def b():
                nonlocal pc
                v = seq[pc] if pc < len(seq) else 0
                pc += 1
                return v

            def s16():
                v = (b() << 8) | b()
                return v - 0x10000 if v >= 0x8000 else v

            def var():
                v = 0
                while True:
                    x = b()
                    v = (v << 7) | (x & 0x7F)
                    if not x & 0x80 or pc >= len(seq):
                        return v

            def arg(default):
                if argkind == "rnd":
                    lo, hi = s16(), s16()
                    return f"random({lo}, {hi})"
                if argkind == "ind":
                    return f"VAR_{b()}"
                return str(default())

            cmd = b()
            if cmd == 0xA2:
                prefix += "_if "
                cmd = b()
            if cmd == 0xA0:
                argkind = "rnd"
                cmd = b()
            elif cmd == 0xA1:
                argkind = "ind"
                cmd = b()
            stop = False
            if cmd < 0x80:
                vel = b()
                ln = arg(var)
                text = f"{_note(cmd)} {vel}, {ln}"
            else:
                name = NAMES.get(cmd, f"cmd_{cmd:02X}")
                g = cmd & 0xF0
                if cmd in (0x80, 0x81):
                    text = f"{name} {arg(var)}"
                elif cmd == 0x88:
                    no = b()
                    off = (b() << 16) | (b() << 8) | b()
                    text = f"{name} {no}, @{off:06X}"
                    labels.add(off)
                    todo.append(off)
                elif cmd in (0x89, 0x8A):
                    off = (b() << 16) | (b() << 8) | b()
                    text = f"{name} @{off:06X}"
                    labels.add(off)
                    todo.append(off)
                    if cmd == 0x89 and not prefix:
                        stop = True
                elif g in (0xB0, 0xC0, 0xD0):
                    text = f"{name} {arg(b)}"
                elif g == 0xE0:
                    text = f"{name} {arg(s16)}"
                elif cmd == 0xFE:
                    text = f"{name} 0x{(b() << 8) | b():04X}"
                elif cmd == 0xF0:
                    ex = b()
                    en = EX_NAMES.get(ex, f"ex_{ex:02X}")
                    if ex & 0xF0 == 0xE0:
                        text = f"{en} {arg(s16)}"
                    elif ex & 0xF0 in (0x80, 0x90):
                        text = f"{en} VAR_{b()}, {arg(s16)}"
                    else:
                        text = en
                else:
                    text = name
                if cmd in (0xFF, 0xFD) and not prefix:
                    stop = True
            lines[at] = prefix + text
            if stop:
                break
    out = []
    for at in sorted(lines):
        if at in labels:
            out.append(f"@{at:06X}:")
        out.append(f"  {at:06X}  {lines[at]}")
    return out
