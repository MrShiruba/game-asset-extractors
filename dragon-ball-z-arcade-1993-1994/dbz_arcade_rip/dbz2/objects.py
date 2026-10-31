"""Object scripts of Dragon Ball Z 2 (interpreter at 0xCC40).

0x10F36 + 4*id -> script. Each command starts with a word whose high nibble is the
opcode (handler table 0xCC82):
  0x0/0x3/0x7  word delay, word frame (shared bank 0x8E900, index & 0x3FFF)
  0x8          jump: the long at the command (low 24 bits) ; loops while the
               counter set by 0x4 runs, then goes on (4 bytes)
  0xC          colour (low 12 bits)     0x9 priority     0xD move (+1 word)
  0xE          spawn the object script (low 12 bits)     0xF end
  others       1 word
"""
SCRIPTS = 0x10F36
NUM_SCRIPTS = 210
_SIZES = {0: 4, 1: 2, 2: 2, 3: 4, 4: 2, 5: 2, 6: 2, 7: 4, 8: 4, 9: 2, 10: 2, 11: 2, 12: 2, 13: 4, 14: 2}


def walk(m, addr, limit=2000):
    """-> (frames in order of first use, colours set, spawned scripts)"""
    w = lambda a: int.from_bytes(m[a:a + 2], "big")
    frames, colours, spawns, seen, todo = [], [], [], set(), [(addr, False)]
    while todo and len(seen) < limit:
        p, counter = todo.pop(0)
        while p not in seen and 0x400 <= p < len(m) - 4:
            seen.add(p)
            op = m[p] >> 4
            if op in (0, 3, 7):
                frames.append(w(p + 2) & 0x3FFF)
            elif op == 4:
                counter = True
            elif op == 8:
                target = int.from_bytes(m[p:p + 4], "big") & 0xFFFFFF
                if not counter:          # no loop counter: plain jump
                    p = target
                    continue
                todo.append((target, True))
                counter = False
            elif op == 12:
                colours.append(w(p) & 0xFFF)
            elif op == 14:
                spawns.append(w(p) & 0xFFF)
            elif op == 15:
                break
            p += _SIZES[op]
    return list(dict.fromkeys(frames)), colours, spawns


def scripts(m):
    """-> list of (id, address, frames, colours, spawned ids)"""
    l = lambda a: int.from_bytes(m[a:a + 4], "big")
    return [(i, l(SCRIPTS + 4 * i)) + walk(m, l(SCRIPTS + 4 * i)) for i in range(NUM_SCRIPTS)]
