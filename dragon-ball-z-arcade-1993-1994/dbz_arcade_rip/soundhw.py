"""Emulated DBZ sound board: Z80 @ 4 MHz, YM2151 @ 4 MHz, OKI M6295 @ 1.056 MHz.

Only what the sound program can observe is emulated (YM2151 timers/status,
the sound latch + NMI). Every write to the YM2151 and the OKI is logged with
a timestamp so it can be turned into a VGM file and rendered to audio.
"""
from .z80 import Z80

Z80_CLOCK = 4_000_000
YM_CLOCK = 4_000_000
OKI_CLOCK = 1_056_000


class SoundBoard:
    WAIT_PC = 0x302  # default (dbz 222a10.5e); found automatically in __init__
    def __init__(self, program):
        self.mem = bytearray(0x10000)
        self.mem[0:len(program)] = program
        # the driver's main loop waits for YM2151 timer A with "ld a,($c001) ; rra ; jr nc"
        k = bytes(program).find(b"\x3a\x01\xc0\x1f\x30")
        if k >= 0:
            self.WAIT_PC = k + 3
        self.latch = 0
        self.ym_addr = 0
        self.ym_regs = [0] * 256
        # YM2151 timers (in Z80 cycles)
        self.ta_period = self._ta_period(0)
        self.tb_period = self._tb_period(0)
        self.ta_next = None
        self.tb_next = None
        self.ta_flag = self.tb_flag = 0
        self.irq_a = self.irq_b = False
        self.log = []          # (cycle, 'ym'|'oki', reg_or_0, value)
        self.logging = True
        self.cpu = Z80(self.read, self.write, self.io_in, self.io_out)
        self.idle = False

    # ---- YM2151 timers ----------------------------------------------------------
    @staticmethod
    def _ta_period(na):
        return 64 * (1024 - na) * Z80_CLOCK // YM_CLOCK

    @staticmethod
    def _tb_period(nb):
        return 1024 * (256 - nb) * Z80_CLOCK // YM_CLOCK

    def _update_timers(self):
        now = self.cpu.cycles
        while self.ta_next is not None and now >= self.ta_next:
            self.ta_flag = 1
            self.ta_next += self.ta_period
        while self.tb_next is not None and now >= self.tb_next:
            self.tb_flag = 1
            self.tb_next += self.tb_period

    def _next_timer_event(self):
        ev = [t for t in (self.ta_next, self.tb_next) if t is not None]
        return min(ev) if ev else None

    # ---- bus --------------------------------------------------------------------
    def read(self, a):
        if a < 0xC000:
            return self.mem[a]
        if a == 0xC001 or a == 0xC000:
            self._update_timers()
            st = self.ta_flag | (self.tb_flag << 1)
            # the main loop waits for timer A at 0x2F9..0x303 (status read at 0x2FF)
            if not (st & 3) and self.cpu.pc == self.WAIT_PC:
                self.idle = True
            return st
        if 0xD000 <= a <= 0xD002:
            return 0x00  # OKI status: no voice playing (we never block)
        if a == 0xE000:
            return self.latch
        return self.mem[a]

    def write(self, a, v):
        if 0x8000 <= a < 0xC000:
            self.mem[a] = v
        elif a == 0xC000:
            self.ym_addr = v
        elif a == 0xC001:
            self._ym_write(self.ym_addr, v)
        elif 0xD000 <= a <= 0xD002:
            if self.logging:
                self.log.append((self.cpu.cycles, "oki", 0, v))
        # ROM writes ignored

    def io_in(self, port):
        return 0xFF

    def io_out(self, port, v):
        pass  # port 0: NMI acknowledge

    def _ym_write(self, reg, v):
        self._update_timers()
        self.ym_regs[reg] = v
        if reg in (0x10, 0x11):
            na = (self.ym_regs[0x10] << 2) | (self.ym_regs[0x11] & 3)
            self.ta_period = self._ta_period(na)
        elif reg == 0x12:
            self.tb_period = self._tb_period(v)
        elif reg == 0x14:
            now = self.cpu.cycles
            if v & 0x01:
                if self.ta_next is None:
                    self.ta_next = now + self.ta_period
            else:
                self.ta_next = None
            if v & 0x02:
                if self.tb_next is None:
                    self.tb_next = now + self.tb_period
            else:
                self.tb_next = None
            self.irq_a = bool(v & 0x04)
            self.irq_b = bool(v & 0x08)
            if v & 0x10:
                self.ta_flag = 0
            if v & 0x20:
                self.tb_flag = 0
        if self.logging and reg != 0x14 and reg not in (0x10, 0x11, 0x12):
            self.log.append((self.cpu.cycles, "ym", reg, v))

    # ---- running ----------------------------------------------------------------
    def irq_line(self):
        return (self.ta_flag and self.irq_a) or (self.tb_flag and self.irq_b)

    def run_until(self, cycle_target, idle_skip=True):
        cpu = self.cpu
        step = cpu.step
        while cpu.cycles < cycle_target:
            if cpu.iff1 and (self.irq_a or self.irq_b):
                self._update_timers()
                if self.irq_line():
                    cpu.irq()
            if cpu.halted:
                nxt = self._next_timer_event()
                if nxt is None or not (self.irq_a or self.irq_b):
                    cpu.cycles = cycle_target
                    return
                cpu.cycles = max(cpu.cycles, min(nxt, cycle_target))
                continue
            step()
            if self.idle:
                self.idle = False
                if idle_skip:
                    # busy-waiting on the YM2151 timer flag: jump to the next timer event
                    nxt = self._next_timer_event()
                    if nxt is not None and nxt > cpu.cycles:
                        cpu.cycles = min(nxt, cycle_target)

    def send_command(self, cmd):
        self.latch = cmd & 0xFF
        self.cpu.nmi()
