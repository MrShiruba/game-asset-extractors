"""Record the sound program command by command -> VGM (lossless register log).

Dragon Ball Z 2 (s-001.5e) works the same way: 0x01-0x13 music, 0x14-0x7F only reset
the chip, 0x80+ OKI phrases (samples 100-116 except 113 are the music percussion).

Command map of 222a10.5e (found by probing every value and by reading the
68000 code that sends them):
  0x00        stop everything
  0x01-0x10   music (YM2151 + OKI drum samples 100-104); the game itself uses 0x0B-0x11
  0x11        no sound (stop/fade)
  0x12-0x7F   not used by the game: note sequences without instrument data
              (silent on their own; extract with --commands for curiosity)
  0x80-0xFF   play OKI phrase (cmd & 0x7F): ALL voices and sound effects of the game
              are OKI samples -> see the `voices` target
"""
import copy
import json
import os
import struct

from . import oki
from .soundhw import OKI_CLOCK, YM_CLOCK, Z80_CLOCK, SoundBoard

MUSIC = range(0x01, 0x11)
# per game: music commands, GD3 names (English, Japanese) and year
GAME_SOUND = {
    "dbz":  {"music": range(0x01, 0x11), "gd3": ("Dragon Ball Z", "ドラゴンボールZ", "1993")},
    # dbz2 (s-001.5e): 0x01-0x13 music, 0x14-0x7F only reset the chip, 0x80+ OKI phrases
    "dbz2": {"music": range(0x01, 0x14),
             "gd3": ("Dragon Ball Z 2 Super Battle", "ドラゴンボールZ2 スーパーバトル", "1994")},
}



# ----------------------------------------------------------------- helpers ----
def parse_commands(spec):
    if not spec:
        return None
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a, 0), int(b, 0) + 1))
        elif part:
            out.append(int(part, 0))
    return out


# ---------------------------------------------------------------- recorder ----
class Recorder:
    def __init__(self, program, oki_rom):
        self.oki_rom = oki_rom
        self.table = {n: (s, e) for n, s, e in oki.read_table(oki_rom)}
        base = SoundBoard(program)
        base.run_until(Z80_CLOCK // 2)  # let the driver initialise
        self.init_regs = list(base.ym_regs)
        base.log = []
        self.base = base

    def _fresh(self):
        sb = copy.deepcopy(self.base)
        sb.cpu.read, sb.cpu.write = sb.read, sb.write
        sb.cpu.io_in, sb.cpu.io_out = sb.io_in, sb.io_out
        return sb

    def oki_len_cycles(self, phrase):
        s, e = self.table.get(phrase, (0, 0))
        return (e - s + 1) * 2 * Z80_CLOCK // oki.OKI_RATE

    def record(self, cmd, max_seconds, silence=1.0, chunk=0.1):
        """Return (log, end_cycle) ; log relative to the command start."""
        sb = self._fresh()
        t0 = sb.cpu.cycles
        sb.send_command(cmd)
        keyed = [0] * 8
        busy_until = t0
        oki_pending = None
        last_active = t0
        processed = 0
        limit = t0 + int(max_seconds * Z80_CLOCK)
        t = t0
        while t < limit:
            t = min(limit, t + int(chunk * Z80_CLOCK))
            sb.run_until(t)
            for cyc, chip, reg, val in sb.log[processed:]:
                if chip == "ym" and reg == 0x08:
                    keyed[val & 7] = (val >> 3) & 0xF
                elif chip == "oki":
                    if oki_pending is not None:
                        if val >> 4:
                            busy_until = max(busy_until, cyc + self.oki_len_cycles(oki_pending))
                        oki_pending = None
                    elif val & 0x80:
                        oki_pending = val & 0x7F
            processed = len(sb.log)
            if any(keyed) or busy_until > t:
                last_active = t
            elif t - last_active > silence * Z80_CLOCK:
                break
        end = min(t, last_active + int(0.8 * Z80_CLOCK))  # keep a release tail
        log = [(c - t0, chip, r, v) for c, chip, r, v in sb.log if c - t0 <= end - t0]
        return log, end - t0, t >= limit


    def record_loop(self, cmd, max_seconds=300.0, min_loop=2.0):
        """Run a music command until the sound driver comes back to an exact
        previous state (Z80 RAM + YM2151 registers, sampled every timer-A tick).
        Emulation is deterministic, so the track loops exactly there.
        -> (log, end_cycle, loop_start_cycle or None)."""
        sb = self._fresh()
        t0 = sb.cpu.cycles
        sb.send_command(cmd)
        step = sb.ta_period
        seen = {}
        started = False
        for k in range(1, int(max_seconds * Z80_CLOCK / step) + 1):
            sb.run_until(t0 + k * step)
            if not started:
                started = any(e[1] == "ym" and e[2] == 0x08 and (e[3] >> 3) & 0xF for e in sb.log)
                if not started:
                    continue
            state = bytes(sb.mem[0x8000:0xC000]) + bytes(sb.ym_regs)
            h = hash(state)
            first = seen.get(h)
            if first is not None and (k - first) * step >= min_loop * Z80_CLOCK:
                start, end = first * step, k * step
                log = [(c - t0, chip, r, v) for c, chip, r, v in sb.log if c - t0 < end]
                active = any(start <= c < end and (chip == "oki" or (r == 0x08 and (v >> 3) & 0xF))
                             for c, chip, r, v in log)
                if not active:  # nothing plays any more: the track has ended
                    stop = start + Z80_CLOCK  # keep 1 s of release
                    return [e for e in log if e[0] < stop], stop, None
                period = end - start
                start = self._earliest_loop(log, start, period)
                end = start + period
                return [e for e in log if e[0] < end], end, start
            seen.setdefault(h, k)
        end = int(max_seconds * Z80_CLOCK)
        return [(c - t0, chip, r, v) for c, chip, r, v in sb.log if c - t0 < end], end, None


    def _earliest_loop(self, log, start, period):
        """The driver's RAM can differ on the first pass (counters, flags) while the
        music is already identical: move the loop point back as long as every
        write in [s, start) has its twin one period later and the YM2151
        registers are identical on both sides of the boundary."""
        events = {(c, chip, r, v) for c, chip, r, v in log}
        times = sorted({c for c, _, _, _ in log if c < start}, reverse=True)
        by_time = {}
        for c, chip, r, v in log:
            by_time.setdefault(c, []).append((chip, r, v))

        def regs_before(t):
            regs = list(self.init_regs)
            for c, chip, r, v in log:
                if c >= t:
                    break
                if chip == "ym":
                    regs[r] = v
            return regs

        best = start
        for c in times:
            if not all((c + period, chip, r, v) in events for chip, r, v in by_time[c]):
                break
            best = c
        # notes started before the match may still be releasing: keep a margin of
        # identical music before the loop point so both sides sound the same
        if best < start:
            margin = 3 * Z80_CLOCK
            later = [c for c in times if c >= best + margin]
            best = min(later) if later else start
        # make sure the chip state matches at the new boundary, else step forward
        while best < start:
            if regs_before(best) == regs_before(best + period):
                return best
            nxt = [c for c in times if c > best]
            best = min(nxt) if nxt else start
        return start


# ------------------------------------------------------------------- VGM ----
def write_vgm(path, init_regs, log, length_cycles, oki_rom, title, loop_cycles=None, game="dbz"):
    out = bytearray()

    def wait(n):
        while n > 0:
            k = min(n, 0xFFFF)
            if k == 735: out.append(0x62)
            elif k == 882: out.append(0x63)
            elif k <= 16: out.append(0x70 + k - 1)
            else: out.extend(bytes([0x61]) + struct.pack("<H", k))
            n -= k

    # OKI ROM data block (type 0x8B)
    out += bytes([0x67, 0x66, 0x8B]) + struct.pack("<I", len(oki_rom) + 8)
    out += struct.pack("<II", len(oki_rom), 0) + oki_rom
    for reg in _init_reg_list(init_regs):
        out += bytes([0x54, reg, init_regs[reg]])
    pos = 0
    loop_s = loop_cycles * 44100 // Z80_CLOCK if loop_cycles is not None else None
    loop_offset = None
    for cyc, chip, reg, val in log:
        s = cyc * 44100 // Z80_CLOCK
        if loop_s is not None and loop_offset is None and s >= loop_s:
            wait(loop_s - pos)
            pos = max(pos, loop_s)
            loop_offset = 0x100 + len(out)
        wait(s - pos)
        pos = max(pos, s)
        if chip == "ym":
            out += bytes([0x54, reg, val])
        else:
            out += bytes([0xB8, 0x00, val])
    total = length_cycles * 44100 // Z80_CLOCK
    if loop_s is not None and loop_offset is None:
        wait(loop_s - pos)
        pos = max(pos, loop_s)
        loop_offset = 0x100 + len(out)
    wait(total - pos)
    out.append(0x66)

    gd3 = _gd3(title, game)
    header = bytearray(0x100)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x171)
    struct.pack_into("<I", header, 0x18, max(total, pos))
    if loop_offset is not None:  # native VGM loop: the player repeats [loop point, end)
        struct.pack_into("<I", header, 0x1C, loop_offset - 0x1C)
        struct.pack_into("<I", header, 0x20, max(total, pos) - loop_s)
    struct.pack_into("<I", header, 0x30, YM_CLOCK)
    struct.pack_into("<I", header, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", header, 0x98, OKI_CLOCK | 0x80000000)  # bit 31: pin 7 high
    data = header + out
    struct.pack_into("<I", data, 0x14, len(data) - 0x14)
    data += gd3
    struct.pack_into("<I", data, 0x04, len(data) - 4)
    with open(path, "wb") as fh:
        fh.write(data)


def write_oki_sample_vgm(path, rom, slot, start, end, game="dbz"):
    """One OKI phrase as a VGM: only the table and the sample bytes are embedded."""
    out = bytearray()

    def block(addr, data):
        out.extend(bytes([0x67, 0x66, 0x8B]) + struct.pack("<I", len(data) + 8))
        out.extend(struct.pack("<II", len(rom), addr) + data)

    block(0, rom[0:0x400])            # phrase table
    block(start, rom[start:end + 1])  # ADPCM data
    out.extend(bytes([0xB8, 0x00, 0x80 | slot, 0xB8, 0x00, 0x10]))  # phrase -> voice 1, full volume
    total = (end - start + 1) * 2 * 44100 // oki.OKI_RATE + 441
    n = total
    while n > 0:
        k = min(n, 0xFFFF)
        out.extend(bytes([0x61]) + struct.pack("<H", k))
        n -= k
    out.append(0x66)
    header = bytearray(0x100)
    header[0:4] = b"Vgm "
    struct.pack_into("<I", header, 0x08, 0x171)
    struct.pack_into("<I", header, 0x18, total)
    struct.pack_into("<I", header, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", header, 0x98, OKI_CLOCK | 0x80000000)
    data = header + out
    struct.pack_into("<I", data, 0x14, len(data) - 0x14)
    data += _gd3(f"OKI sample {slot:03d} (command {0x80 | slot:#04x})", game)
    struct.pack_into("<I", data, 0x04, len(data) - 4)
    with open(path, "wb") as fh:
        fh.write(data)


def _gd3(title, game="dbz"):
    en, jp, year = GAME_SOUND[game]["gd3"]
    fields = [title, "", en, jp, "Arcade", "", "Banpresto", "",
              year, "dbz-arcade-ripper", ""]
    body = b"".join(s.encode("utf-16-le") + b"\0\0" for s in fields)
    return b"Gd3 " + struct.pack("<II", 0x100, len(body)) + body


def _init_reg_list(regs):
    """Registers worth restoring at t=0 (no timers, no key-on, no test regs)."""
    return [r for r in range(0x18, 0x100) if r not in (0x19,)] + [0x0F, 0x19]


# ------------------------------------------------------------------- main ----
def _signature(log):
    import hashlib
    h = hashlib.md5()
    for c, chip, r, v in log:
        h.update(struct.pack("<IBBB", c // 4000, chip == "ym", r, v))
    return h.hexdigest()


def extract_sounds(rs, out, music_seconds=300.0, commands=None, seconds=6.0, keep_duplicates=False):
    """Record each sound command and write it as a VGM (YM2151 + OKI, lossless)."""
    rec = Recorder(rs.audiocpu, rs.oki)
    music = GAME_SOUND[rs.game]["music"]
    cmds = parse_commands(commands) or list(music)
    index, seen = [], {}
    for cmd in cmds:
        if cmd == 0 or cmd >= 0x80:
            continue
        kind = "music" if cmd in music else "extra"
        loop = None
        if kind == "music":
            log, length, loop = rec.record_loop(cmd, max_seconds=music_seconds)
            cut = loop is None and length >= int(music_seconds * Z80_CLOCK)
        else:
            log, length, cut = rec.record(cmd, seconds, silence=0.6)
        keyons = sum(1 for e in log if e[1] == "ym" and e[2] == 0x08 and (e[3] >> 3) & 0xF)
        if not keyons and not any(e[1] == "oki" for e in log):
            continue  # command produced no sound
        sig = _signature(log)
        if sig in seen and not keep_duplicates:
            index.append({"command": hex(cmd), "duplicate_of": seen[sig]})
            continue
        seen[sig] = hex(cmd)
        d = os.path.join(out, kind)
        os.makedirs(d, exist_ok=True)
        name = f"{kind}_{cmd:02x}"
        write_vgm(os.path.join(d, name + ".vgm"), rec.init_regs, log, length, rs.oki,
                  f"{kind.upper()} {cmd:#04x}", loop_cycles=loop, game=rs.game)
        secs = round(length / Z80_CLOCK, 2)
        entry = {"command": hex(cmd), "type": kind, "file": name + ".vgm", "seconds": secs}
        if loop is not None:
            entry["loop_start"] = round(loop / Z80_CLOCK, 2)
            note = f"  (intro {loop / Z80_CLOCK:.2f}s + loop {(length - loop) / Z80_CLOCK:.2f}s)"
        elif cut:
            entry["cut"] = True
            note = f"  (no loop found, cut at {secs:.0f}s)"
        else:
            note = "  (ends)"
        index.append(entry)
        print(f"  {name}  {secs:6.2f}s{note}", flush=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "sounds_index.json"), "w") as fh:
        json.dump(index, fh, indent=1)
    dups = sum(1 for e in index if "duplicate_of" in e)
    if dups:
        print(f"  ({dups} commands were exact duplicates and were skipped)")
    return index
