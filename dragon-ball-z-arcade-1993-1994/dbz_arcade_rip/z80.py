"""A compact, pure-Python Zilog Z80 interpreter.

Complete documented instruction set plus the common undocumented ones
(IXH/IXL/IYH/IYL, SLL, DDCB/FDCB register copies). Flags follow the
documented behaviour including bits 3/5. Timing uses standard T-states
(close enough for driving a sound program).

Memory and I/O are callbacks: read(addr) / write(addr, val) / io_in / io_out.
"""

# ---- flag tables --------------------------------------------------------------
FC, FN, FP, F3, FH, F5, FZ, FS = 1, 2, 4, 8, 16, 32, 64, 128

SZ = [0] * 256
SZP = [0] * 256
PARITY = [0] * 256
for _i in range(256):
    _p = bin(_i).count("1") % 2 == 0
    PARITY[_i] = FP if _p else 0
    SZ[_i] = (_i & (FS | F5 | F3)) | (FZ if _i == 0 else 0)
    SZP[_i] = SZ[_i] | PARITY[_i]

# T-states for unprefixed opcodes (taken branches add extra below)
CYC = [
    4, 10, 7, 6, 4, 4, 7, 4, 4, 11, 7, 6, 4, 4, 7, 4,
    8, 10, 7, 6, 4, 4, 7, 4, 12, 11, 7, 6, 4, 4, 7, 4,
    7, 10, 16, 6, 4, 4, 7, 4, 7, 11, 16, 6, 4, 4, 7, 4,
    7, 10, 13, 6, 11, 11, 10, 4, 7, 11, 13, 6, 4, 4, 7, 4,
] + [4] * 64 + [4] * 64 + [
    5, 10, 10, 10, 10, 11, 7, 11, 5, 10, 10, 0, 10, 17, 7, 11,
    5, 10, 10, 11, 10, 11, 7, 11, 5, 4, 10, 11, 10, 0, 7, 11,
    5, 10, 10, 19, 10, 11, 7, 11, 5, 4, 10, 4, 10, 0, 7, 11,
    5, 10, 10, 4, 10, 11, 7, 11, 5, 6, 10, 4, 10, 0, 7, 11,
]
for _o in range(0x40, 0xC0):
    if (_o & 7) == 6 or (0x70 <= _o <= 0x77 and _o != 0x76):
        CYC[_o] = 7
CYC[0x76] = 4

# opcodes whose (HL) operand becomes (IX+d) under a DD/FD prefix
_MEM_OPS = {0x34, 0x35, 0x36}
for _o in range(0x40, 0xC0):
    if _o == 0x76:
        continue
    if _o < 0x80 and ((_o & 7) == 6 or ((_o >> 3) & 7) == 6):
        _MEM_OPS.add(_o)
    elif _o >= 0x80 and (_o & 7) == 6:
        _MEM_OPS.add(_o)


class Z80:
    def __init__(self, read, write, io_in=None, io_out=None):
        self.read = read
        self.write = write
        self.io_in = io_in or (lambda port: 0xFF)
        self.io_out = io_out or (lambda port, val: None)
        self.reset()

    def reset(self):
        # r: B C D E H L - A   (index 6 = (HL), handled separately)
        self.r = [0] * 8
        self.f = 0
        self.alt = [0] * 8
        self.alt_f = 0
        self.ix = self.iy = 0xFFFF
        self.sp = 0xFFFF
        self.pc = 0
        self.i = self.rr = 0
        self.iff1 = self.iff2 = 0
        self.im = 0
        self.halted = False
        self.cycles = 0
        self._ei_delay = False
        self._hl_override = None

    # ---- helpers -----------------------------------------------------------
    def fetch(self):
        v = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        return lo | (self.fetch() << 8)

    def fetch_d(self):
        d = self.fetch()
        return d - 256 if d & 0x80 else d

    def read16(self, a):
        return self.read(a) | (self.read((a + 1) & 0xFFFF) << 8)

    def write16(self, a, v):
        self.write(a, v & 0xFF)
        self.write((a + 1) & 0xFFFF, (v >> 8) & 0xFF)

    def push(self, v):
        self.sp = (self.sp - 2) & 0xFFFF
        self.write16(self.sp, v)

    def pop(self):
        v = self.read16(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return v

    @property
    def hl(self):
        return (self.r[4] << 8) | self.r[5]

    @hl.setter
    def hl(self, v):
        self.r[4] = (v >> 8) & 0xFF
        self.r[5] = v & 0xFF

    def get_rp(self, p):  # BC DE HL SP
        r = self.r
        if p == 0: return (r[0] << 8) | r[1]
        if p == 1: return (r[2] << 8) | r[3]
        if p == 2: return (r[4] << 8) | r[5]
        return self.sp

    def set_rp(self, p, v):
        r = self.r
        v &= 0xFFFF
        if p == 0: r[0], r[1] = v >> 8, v & 0xFF
        elif p == 1: r[2], r[3] = v >> 8, v & 0xFF
        elif p == 2: r[4], r[5] = v >> 8, v & 0xFF
        else: self.sp = v

    def get_rp2(self, p):  # BC DE HL AF
        if p == 3:
            return (self.r[7] << 8) | self.f
        return self.get_rp(p)

    def set_rp2(self, p, v):
        if p == 3:
            self.r[7] = (v >> 8) & 0xFF
            self.f = v & 0xFF
        else:
            self.set_rp(p, v)

    def hl_addr(self):
        a = self._hl_override
        return self.hl if a is None else a

    def get_r(self, i):
        if i == 6:
            return self.read(self.hl_addr())
        return self.r[i]

    def set_r(self, i, v):
        if i == 6:
            self.write(self.hl_addr(), v & 0xFF)
        else:
            self.r[i] = v & 0xFF

    def cond(self, c):
        f = self.f
        if c == 0: return not f & FZ
        if c == 1: return bool(f & FZ)
        if c == 2: return not f & FC
        if c == 3: return bool(f & FC)
        if c == 4: return not f & FP
        if c == 5: return bool(f & FP)
        if c == 6: return not f & FS
        return bool(f & FS)

    # ---- ALU ---------------------------------------------------------------
    def alu(self, op, v):
        a = self.r[7]
        if op == 0 or op == 1:  # ADD / ADC
            c = (self.f & FC) if op == 1 else 0
            res = a + v + c
            self.f = (SZ[res & 0xFF] | (FC if res > 0xFF else 0) | ((a ^ v ^ res) & FH)
                      | (FP if ((a ^ ~v) & (a ^ res) & 0x80) else 0))
            self.r[7] = res & 0xFF
        elif op == 2 or op == 3 or op == 7:  # SUB / SBC / CP
            c = (self.f & FC) if op == 3 else 0
            res = a - v - c
            f = ((SZ[res & 0xFF] & ~(F3 | F5)) | FN | (FC if res < 0 else 0) | ((a ^ v ^ res) & FH)
                 | (FP if ((a ^ v) & (a ^ res) & 0x80) else 0))
            if op == 7:
                self.f = f | (v & (F3 | F5))
            else:
                self.f = f | (res & (F3 | F5))
                self.r[7] = res & 0xFF
        elif op == 4:
            a &= v
            self.f = SZP[a] | FH
            self.r[7] = a
        elif op == 5:
            a ^= v
            self.f = SZP[a]
            self.r[7] = a
        else:
            a |= v
            self.f = SZP[a]
            self.r[7] = a

    def inc8(self, v):
        res = (v + 1) & 0xFF
        self.f = (self.f & FC) | SZ[res] | (FH if (v & 0xF) == 0xF else 0) | (FP if v == 0x7F else 0)
        return res

    def dec8(self, v):
        res = (v - 1) & 0xFF
        self.f = (self.f & FC) | SZ[res] | FN | (FH if (v & 0xF) == 0 else 0) | (FP if v == 0x80 else 0)
        return res

    def add16(self, a, b):
        res = a + b
        self.f = ((self.f & (FS | FZ | FP)) | (FC if res > 0xFFFF else 0)
                  | (((a ^ b ^ res) >> 8) & FH) | ((res >> 8) & (F3 | F5)))
        return res & 0xFFFF

    def adc16(self, a, b):
        c = self.f & FC
        res = a + b + c
        r16 = res & 0xFFFF
        self.f = (((r16 >> 8) & (FS | F3 | F5)) | (FZ if r16 == 0 else 0) | (FC if res > 0xFFFF else 0)
                  | (((a ^ b ^ res) >> 8) & FH) | (FP if ((a ^ ~b) & (a ^ res) & 0x8000) else 0))
        return r16

    def sbc16(self, a, b):
        c = self.f & FC
        res = a - b - c
        r16 = res & 0xFFFF
        self.f = (((r16 >> 8) & (FS | F3 | F5)) | (FZ if r16 == 0 else 0) | (FC if res < 0 else 0) | FN
                  | (((a ^ b ^ res) >> 8) & FH) | (FP if ((a ^ b) & (a ^ res) & 0x8000) else 0))
        return r16

    def rot(self, op, v):
        c = self.f & FC
        if op == 0: co = v >> 7; v = ((v << 1) | co) & 0xFF
        elif op == 1: co = v & 1; v = (v >> 1) | (co << 7)
        elif op == 2: co = v >> 7; v = ((v << 1) | c) & 0xFF
        elif op == 3: co = v & 1; v = (v >> 1) | (c << 7)
        elif op == 4: co = v >> 7; v = (v << 1) & 0xFF
        elif op == 5: co = v & 1; v = (v >> 1) | (v & 0x80)
        elif op == 6: co = v >> 7; v = ((v << 1) | 1) & 0xFF
        else: co = v & 1; v >>= 1
        self.f = SZP[v] | co
        return v

    # ---- interrupts ----------------------------------------------------------
    def nmi(self):
        self.halted = False
        self.iff2 = self.iff1
        self.iff1 = 0
        self.push(self.pc)
        self.pc = 0x66
        self.cycles += 11

    def irq(self, vector=0xFF):
        if not self.iff1 or self._ei_delay:
            return False
        self.halted = False
        self.iff1 = self.iff2 = 0
        self.push(self.pc)
        if self.im == 2:
            self.pc = self.read16(((self.i << 8) | (vector & 0xFE)) & 0xFFFF)
            self.cycles += 19
        else:
            self.pc = 0x38
            self.cycles += 13
        return True

    # ---- execution -----------------------------------------------------------
    def step(self):
        self._ei_delay = False
        if self.halted:
            self.cycles += 4
            return
        self.rr = (self.rr & 0x80) | ((self.rr + 1) & 0x7F)
        op = self.fetch()
        if op == 0xCB:
            self.exec_cb(self.fetch(), None)
        elif op == 0xED:
            self.exec_ed(self.fetch())
        elif op == 0xDD or op == 0xFD:
            self.exec_index(op)
        else:
            self.cycles += CYC[op]
            self.exec_main(op)

    def exec_index(self, prefix):
        isix = prefix == 0xDD
        op = self.fetch()
        idx = self.ix if isix else self.iy
        if op == 0xCB:
            d = self.fetch_d()
            addr = (idx + d) & 0xFFFF
            self.exec_cb(self.fetch(), addr)
            return
        if op in (0xDD, 0xFD, 0xED):  # prefix chain: treat previous as NOP
            self.pc = (self.pc - 1) & 0xFFFF
            self.cycles += 4
            return
        self.cycles += CYC[op] + 4
        if op in _MEM_OPS:
            d = self.fetch_d()
            self._hl_override = (idx + d) & 0xFFFF
            self.cycles += 8
            try:
                self.exec_main(op)
            finally:
                self._hl_override = None
            return
        if op == 0xEB:  # EX DE,HL is not affected by the prefix
            self.exec_main(op)
            return
        h, l = self.r[4], self.r[5]
        self.r[4], self.r[5] = idx >> 8, idx & 0xFF
        self.exec_main(op)
        nidx = (self.r[4] << 8) | self.r[5]
        self.r[4], self.r[5] = h, l
        if isix:
            self.ix = nidx
        else:
            self.iy = nidx

    def exec_main(self, op):
        r = self.r
        x = op >> 6
        y = (op >> 3) & 7
        z = op & 7
        if x == 1:
            if op == 0x76:
                self.halted = True
                return
            self.set_r(y, self.get_r(z))
            return
        if x == 2:
            self.alu(y, self.get_r(z))
            return
        if x == 0:
            if z == 0:
                if y == 0: return
                if y == 1:
                    a, f = r[7], self.f
                    r[7], self.f = self.alt[7], self.alt_f
                    self.alt[7], self.alt_f = a, f
                    return
                if y == 2:  # DJNZ
                    d = self.fetch_d()
                    r[0] = (r[0] - 1) & 0xFF
                    if r[0]:
                        self.pc = (self.pc + d) & 0xFFFF
                        self.cycles += 5
                    return
                d = self.fetch_d()
                if y == 3 or self.cond(y - 4):
                    self.pc = (self.pc + d) & 0xFFFF
                    if y != 3:
                        self.cycles += 5
                return
            if z == 1:
                p = y >> 1
                if y & 1:
                    self.hl = self.add16(self.hl, self.get_rp(p))
                else:
                    self.set_rp(p, self.fetch16())
                return
            if z == 2:
                if y == 0: self.write((r[0] << 8) | r[1], r[7])
                elif y == 1: r[7] = self.read((r[0] << 8) | r[1])
                elif y == 2: self.write((r[2] << 8) | r[3], r[7])
                elif y == 3: r[7] = self.read((r[2] << 8) | r[3])
                elif y == 4: self.write16(self.fetch16(), self.hl)
                elif y == 5: self.hl = self.read16(self.fetch16())
                elif y == 6: self.write(self.fetch16(), r[7])
                else: r[7] = self.read(self.fetch16())
                return
            if z == 3:
                p = y >> 1
                self.set_rp(p, self.get_rp(p) + (-1 if y & 1 else 1))
                return
            if z == 4:
                self.set_r(y, self.inc8(self.get_r(y)))
                return
            if z == 5:
                self.set_r(y, self.dec8(self.get_r(y)))
                return
            if z == 6:
                if y == 6 and self._hl_override is not None:
                    # DD 36 d n : d already fetched, n follows
                    self.write(self._hl_override, self.fetch())
                else:
                    self.set_r(y, self.fetch())
                return
            # z == 7
            a = r[7]
            f = self.f
            if y == 0:
                c = a >> 7; a = ((a << 1) | c) & 0xFF
                self.f = (f & (FS | FZ | FP)) | (a & (F3 | F5)) | c
            elif y == 1:
                c = a & 1; a = (a >> 1) | (c << 7)
                self.f = (f & (FS | FZ | FP)) | (a & (F3 | F5)) | c
            elif y == 2:
                c = a >> 7; a = ((a << 1) | (f & FC)) & 0xFF
                self.f = (f & (FS | FZ | FP)) | (a & (F3 | F5)) | c
            elif y == 3:
                c = a & 1; a = (a >> 1) | ((f & FC) << 7)
                self.f = (f & (FS | FZ | FP)) | (a & (F3 | F5)) | c
            elif y == 4:  # DAA
                corr, c = 0, f & FC
                if (f & FH) or (a & 0xF) > 9: corr |= 0x06
                if c or a > 0x99:
                    corr |= 0x60
                    c = FC
                if f & FN:
                    h = FH if (f & FH) and (a & 0xF) < 6 else 0
                    a = (a - corr) & 0xFF
                else:
                    h = FH if (a & 0xF) > 9 else 0
                    a = (a + corr) & 0xFF
                self.f = SZP[a] | c | h | (f & FN)
            elif y == 5:
                a ^= 0xFF
                self.f = (f & (FS | FZ | FP | FC)) | FH | FN | (a & (F3 | F5))
            elif y == 6:
                self.f = (f & (FS | FZ | FP)) | FC | (a & (F3 | F5))
            else:
                self.f = (f & (FS | FZ | FP)) | (a & (F3 | F5)) | (FH if f & FC else 0) | (0 if f & FC else FC)
            r[7] = a
            return
        # x == 3
        if z == 0:
            if self.cond(y):
                self.pc = self.pop()
                self.cycles += 6
            return
        if z == 1:
            if y & 1 == 0:
                self.set_rp2(y >> 1, self.pop())
            elif y == 1:
                self.pc = self.pop()
            elif y == 3:  # EXX
                for i in range(6):
                    r[i], self.alt[i] = self.alt[i], r[i]
            elif y == 5:
                self.pc = self.hl
            else:
                self.sp = self.hl
            return
        if z == 2:
            nn = self.fetch16()
            if self.cond(y):
                self.pc = nn
            return
        if z == 3:
            if y == 0:
                self.pc = self.fetch16()
            elif y == 2:
                self.io_out(self.fetch(), r[7])
            elif y == 3:
                r[7] = self.io_in(self.fetch()) & 0xFF
            elif y == 4:
                v = self.read16(self.sp)
                self.write16(self.sp, self.hl)
                self.hl = v
            elif y == 5:
                de = (r[2] << 8) | r[3]
                r[2], r[3], r[4], r[5] = r[4], r[5], de >> 8, de & 0xFF
            elif y == 6:
                self.iff1 = self.iff2 = 0
            else:
                self.iff1 = self.iff2 = 1
                self._ei_delay = True
            return
        if z == 4:
            nn = self.fetch16()
            if self.cond(y):
                self.push(self.pc)
                self.pc = nn
                self.cycles += 7
            return
        if z == 5:
            if y & 1 == 0:
                self.push(self.get_rp2(y >> 1))
            else:  # CALL nn (y==1)
                nn = self.fetch16()
                self.push(self.pc)
                self.pc = nn
            return
        if z == 6:
            self.alu(y, self.fetch())
            return
        self.push(self.pc)
        self.pc = y * 8

    def exec_cb(self, op, addr):
        x = op >> 6
        y = (op >> 3) & 7
        z = op & 7
        if addr is None:
            self.cycles += 15 if z == 6 else 8
            v = self.read(self.hl) if z == 6 else self.r[z]
            maddr = self.hl
        else:
            self.cycles += 23
            v = self.read(addr)
            maddr = addr
        if x == 1:  # BIT
            res = v & (1 << y)
            f = (self.f & FC) | FH | (SZP[res] & (FS | FZ | FP))
            src = (maddr >> 8) if (z == 6 or addr is not None) else v
            self.f = f | (src & (F3 | F5))
            if addr is not None:
                self.cycles -= 3
            return
        if x == 0:
            v = self.rot(y, v)
        elif x == 2:
            v &= ~(1 << y) & 0xFF
        else:
            v |= 1 << y
        if addr is not None:
            self.write(addr, v)
            if z != 6:
                self.r[z] = v
        elif z == 6:
            self.write(self.hl, v)
        else:
            self.r[z] = v

    def exec_ed(self, op):
        r = self.r
        x = op >> 6
        y = (op >> 3) & 7
        z = op & 7
        self.cycles += 8
        if x == 1:
            if z == 0:
                v = self.io_in((r[0] << 8) | r[1]) & 0xFF
                if y != 6:
                    r[y] = v
                self.f = (self.f & FC) | SZP[v]
                self.cycles += 4
            elif z == 1:
                self.io_out((r[0] << 8) | r[1], 0 if y == 6 else r[y])
                self.cycles += 4
            elif z == 2:
                p = y >> 1
                if y & 1:
                    self.hl = self.adc16(self.hl, self.get_rp(p))
                else:
                    self.hl = self.sbc16(self.hl, self.get_rp(p))
                self.cycles += 7
            elif z == 3:
                nn = self.fetch16()
                p = y >> 1
                if y & 1:
                    self.set_rp(p, self.read16(nn))
                else:
                    self.write16(nn, self.get_rp(p))
                self.cycles += 12
            elif z == 4:  # NEG
                a = r[7]
                r[7] = 0
                self.alu(2, a)
            elif z == 5:  # RETN / RETI
                self.pc = self.pop()
                self.iff1 = self.iff2
                self.cycles += 6
            elif z == 6:
                self.im = (0, 0, 1, 2)[y & 3]
            else:
                if y == 0: self.i = r[7]
                elif y == 1: self.rr = r[7]
                elif y == 2:
                    r[7] = self.i
                    self.f = (self.f & FC) | SZ[r[7]] | (FP if self.iff2 else 0)
                elif y == 3:
                    r[7] = self.rr
                    self.f = (self.f & FC) | SZ[r[7]] | (FP if self.iff2 else 0)
                elif y == 4:  # RRD
                    hl = self.hl
                    m = self.read(hl)
                    a = r[7]
                    self.write(hl, ((a << 4) | (m >> 4)) & 0xFF)
                    r[7] = (a & 0xF0) | (m & 0x0F)
                    self.f = (self.f & FC) | SZP[r[7]]
                    self.cycles += 10
                elif y == 5:  # RLD
                    hl = self.hl
                    m = self.read(hl)
                    a = r[7]
                    self.write(hl, ((m << 4) | (a & 0x0F)) & 0xFF)
                    r[7] = (a & 0xF0) | (m >> 4)
                    self.f = (self.f & FC) | SZP[r[7]]
                    self.cycles += 10
            return
        if x == 2 and z <= 3 and y >= 4:
            self.block(y, z)
            return
        # undefined ED xx: NOP

    def block(self, y, z):
        r = self.r
        inc = 1 if y in (4, 6) else -1
        repeat = y >= 6
        hl = self.hl
        bc = (r[0] << 8) | r[1]
        de = (r[2] << 8) | r[3]
        self.cycles += 8
        if z == 0:  # LDI/LDD
            v = self.read(hl)
            self.write(de, v)
            hl = (hl + inc) & 0xFFFF
            de = (de + inc) & 0xFFFF
            bc = (bc - 1) & 0xFFFF
            n = (v + r[7]) & 0xFF
            self.f = (self.f & (FS | FZ | FC)) | (FP if bc else 0) | (n & F3) | ((n << 4) & F5)
            r[2], r[3] = de >> 8, de & 0xFF
        elif z == 1:  # CPI/CPD
            v = self.read(hl)
            a = r[7]
            res = (a - v) & 0xFF
            hl = (hl + inc) & 0xFFFF
            bc = (bc - 1) & 0xFFFF
            h = FH if (a ^ v ^ res) & 0x10 else 0
            n = (res - (1 if h else 0)) & 0xFF
            self.f = ((self.f & FC) | (SZ[res] & (FS | FZ)) | FN | h | (FP if bc else 0)
                      | (n & F3) | ((n << 4) & F5))
            if repeat and (self.f & FZ):
                repeat = False
        elif z == 2:  # INI/IND
            v = self.io_in(bc) & 0xFF
            self.write(hl, v)
            hl = (hl + inc) & 0xFFFF
            r[0] = (r[0] - 1) & 0xFF
            bc = (r[0] << 8) | r[1]
            self.f = SZ[r[0]] | FN
        else:  # OUTI/OUTD
            v = self.read(hl)
            r[0] = (r[0] - 1) & 0xFF
            bc = (r[0] << 8) | r[1]
            self.io_out(bc, v)
            hl = (hl + inc) & 0xFFFF
            self.f = SZ[r[0]] | FN
        self.hl = hl
        r[0], r[1] = bc >> 8, bc & 0xFF
        if repeat:
            cont = bc != 0 if z <= 1 else r[0] != 0
            if cont:
                self.pc = (self.pc - 2) & 0xFFFF
                self.cycles += 5
