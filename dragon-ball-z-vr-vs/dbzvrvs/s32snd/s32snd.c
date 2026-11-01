/*
 * s32snd.c - Sega System 32 sound board emulator / VGM logger
 *            (tuned for Dragon Ball Z: V.R.V.S. sound program epr-16541)
 *
 * Runs the Z80 sound program, sends one sound command through the shared RAM
 * mailbox (e700 = code, e701 = table) and logs every write to the two YM3438
 * and the RF5C68 into a VGM 1.71 file.
 *
 * Usage: s32snd <soundregion.bin> <table> <code> <out.vgm> [maxsec] [tailsec]
 *   soundregion.bin : 4 MB image laid out like MAME's "soundcpu" region
 *                     (epr-16541 x4 at 0, mpr-16540/16539/16538 at 1/2/3 MB)
 *   table           : value written to e701 (1 = music, 2..7 = voices/SFX)
 *   code            : value written to e700 (index in that table)
 * Prints one line: "samples=N loop_start=S loop_len=L end=<loop|stop|timeout>"
 *
 * Hardware facts from MAME src/mame/sega/segas32.cpp:
 *   Z80 @ 32.2159MHz/4, YM3438 x2 @ 32.2159MHz/4, RF5C68 @ 50MHz/4
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "z80.h"

#define Z80_CLOCK 8053975u
#define RF_CLOCK  12500000u
#define VGM_RATE  44100u

static uint8_t *region;          /* 4 MB */
static uint8_t ram[0x2000];      /* e000-ffff */
static uint8_t rfram[0x10000];
static int rf_wbank, rf_chsel;
static int sound_bank;
static uint8_t irq_control[4];
static uint8_t irq_input;
static int irq_line;
static uint8_t dummy;
static z80 cpu;

/* ---------------- YM3438 timers ---------------- */
typedef struct {
    int addr[2];
    int ta, tb, ctrl, status;
    int ta_cnt, tb_cnt, tb_div, ch3mode;
    uint8_t regs[2][256];
} ym_t;
static ym_t ym[2];

/* ---------------- RF5C68 (MAME rf5c68.cpp) for WAV rendering ---------------- */
typedef struct { int enable, env, pan, start; uint32_t addr, step, loopst; } rfch_t;
static rfch_t rch[8]; static int rf_enable, rf_cbank;
static int16_t *wav; static size_t wavn, wavcap; static uint64_t rf_done;
static int wav_mode, rf_on, center_pan; static int smp_hook = -1;
static uint64_t now_samples(void);
static void rf_reg(int r, uint8_t d) {
    rfch_t *c = &rch[rf_cbank];
    switch (r) {
    case 0: c->env = d; break;
    case 1: c->pan = d; break;
    case 2: c->step = (c->step & 0xff00) | d; if (smp_hook >= 0) { fprintf(stderr, "SMP %d %u %llu %d\n", smp_hook, c->step, (unsigned long long)now_samples(), rf_cbank); smp_hook = -1; } break;
    case 3: c->step = (c->step & 0x00ff) | (d << 8); break;
    case 4: c->loopst = (c->loopst & 0xff00) | d; break;
    case 5: c->loopst = (c->loopst & 0x00ff) | (d << 8); break;
    case 6: c->start = d; if (!c->enable) c->addr = (uint32_t)d << 19; break;
    case 7: rf_enable = (d >> 7) & 1; if (d & 0x40) rf_cbank = d & 7; break;
    case 8:
        for (int i = 0; i < 8; i++) { rch[i].enable = (~d >> i) & 1; if (!rch[i].enable) rch[i].addr = (uint32_t)rch[i].start << 19; }
        break;
    }
}
static void rf_sample(void) {
    int l = 0, r = 0;
    if (rf_enable) for (int i = 0; i < 8; i++) {
        rfch_t *c = &rch[i];
        if (!c->enable) continue;
        int lv = (c->pan & 15) * c->env, rv = ((c->pan >> 4) & 15) * c->env;
        int s = rfram[(c->addr >> 11) & 0xffff];
        if (s == 0xff) { c->addr = c->loopst << 11; s = rfram[(c->addr >> 11) & 0xffff]; if (s == 0xff) continue; }
        c->addr += c->step;
        if (s & 0x80) { s &= 0x7f; l += (s * lv) >> 5; r += (s * rv) >> 5; }
        else { l -= (s * lv) >> 5; r -= (s * rv) >> 5; }
    }
    if (l > 32767) l = 32767;
    if (l < -32768) l = -32768;
    if (r > 32767) r = 32767;
    if (r < -32768) r = -32768;
    if (wavn + 2 > wavcap) { wavcap = wavcap ? wavcap * 2 : 1 << 20; wav = realloc(wav, wavcap * 2); }
    wav[wavn++] = l; wav[wavn++] = r;
}
static void rf_catchup(void);

/* ---------------- VGM event log ---------------- */
static uint8_t *ev;  static size_t evlen, evcap;
typedef struct { uint64_t t; size_t off; } evidx_t;
static evidx_t *eix; static size_t eixn, eixcap;
static uint64_t t0;              /* cycle at which recording time starts */
static int recording;            /* 0 = init phase (time forced to 0) */

static uint64_t now_samples(void) {
    if (!recording) return 0;
    return (uint64_t)(cpu.cyc - t0) * VGM_RATE / Z80_CLOCK;
}
static void ev_bytes(const uint8_t *b, size_t n) {
    if (evlen + n > evcap) { evcap = (evcap + n) * 2; ev = realloc(ev, evcap); }
    memcpy(ev + evlen, b, n); evlen += n;
}
static void ev_begin(uint64_t t) {
    if (eixn == eixcap) { eixcap = eixcap ? eixcap * 2 : 4096; eix = realloc(eix, eixcap * sizeof(evidx_t)); }
    eix[eixn].t = t; eix[eixn].off = evlen; eixn++;
}

/* RF5C68 RAM write grouping into data blocks (type 0xC0) */
static uint8_t blk[0x1000]; static int blk_n, blk_start; static uint64_t blk_t;
static void blk_flush(void) {
    if (!blk_n) return;
    uint8_t h[9] = {0x67, 0x66, 0xC0};
    uint32_t sz = blk_n + 2;
    h[3] = sz; h[4] = sz >> 8; h[5] = sz >> 16; h[6] = sz >> 24;
    h[7] = blk_start; h[8] = blk_start >> 8;
    ev_begin(blk_t); ev_bytes(h, 9); ev_bytes(blk, blk_n);
    blk_n = 0;
}
static void log_cmd3(uint8_t c, uint8_t a, uint8_t d) {
    blk_flush();
    uint8_t b[3] = {c, a, d};
    ev_begin(now_samples()); ev_bytes(b, 3);
}
static void log_rfmem(int off, uint8_t d) {
    uint64_t t = now_samples();
    if (blk_n && (off != blk_start + blk_n || t - blk_t > 256)) blk_flush();
    if (!blk_n) { blk_start = off; blk_t = t; }
    blk[blk_n++] = d;
}

/* ---------------- interrupts (segas32_state::update_sound_irq_state) ---------------- */
static void update_irq(void) {
    uint8_t eff = irq_input & ~irq_control[3] & 7;
    irq_line = eff != 0;
}
static void signal_irq(int which) {
    for (int i = 0; i < 3; i++) if (irq_control[i] == which) irq_input |= 1 << i;
    update_irq();
}
static void clear_irq(int which) {
    for (int i = 0; i < 3; i++) if (irq_control[i] == which) irq_input &= ~(1 << i);
    update_irq();
}
static int ym1_irq_state;
static void ym_check_irq(void) {
    int s = (ym[0].status & 3) != 0;
    if (s != ym1_irq_state) {
        ym1_irq_state = s;
        if (s) signal_irq(0); else clear_irq(0);
    }
}

static void ym_write(int chip, int port, uint8_t data) {
    ym_t *y = &ym[chip];
    int p = port >> 1;
    if (!(port & 1)) { y->addr[p] = data; return; }
    int a = y->addr[p];
    y->regs[p][a] = data;
    if (p == 0) {
        if (a == 0x24) y->ta = (y->ta & 3) | (data << 2);
        else if (a == 0x25) y->ta = (y->ta & 0x3fc) | (data & 3);
        else if (a == 0x26) y->tb = data;
        else if (a == 0x27) {
            if ((data & 1) && !(y->ctrl & 1)) y->ta_cnt = y->ta;
            if ((data & 2) && !(y->ctrl & 2)) { y->tb_cnt = y->tb; y->tb_div = 0; }
            if (data & 0x10) y->status &= ~1;
            if (data & 0x20) y->status &= ~2;
            y->ctrl = data;
            if (chip == 0) ym_check_irq();
        }
    }
    /* timer registers are not logged (the driver acks timer A thousands of
       times per second); 0x27 is kept only when the CH3 mode bits change */
    if (p == 0 && a >= 0x24 && a <= 0x27) {
        if (a != 0x27 || ((data ^ y->ch3mode) & 0xc0) == 0) return;
        y->ch3mode = data & 0xc0; data &= 0xc0;
    }
    log_cmd3((chip ? 0xA2 : 0x52) + p, a, data);
}

static void ym_tick(void) {   /* one YM sample (144 clocks) */
    for (int c = 0; c < 2; c++) {
        ym_t *y = &ym[c];
        if (y->ctrl & 1) {
            if (++y->ta_cnt >= 1024) { y->ta_cnt = y->ta; if (y->ctrl & 4) y->status |= 1; }
        }
        if (y->ctrl & 2) {
            if (++y->tb_div >= 16) {
                y->tb_div = 0;
                if (++y->tb_cnt >= 256) { y->tb_cnt = y->tb; if (y->ctrl & 8) y->status |= 2; }
            }
        }
    }
    ym_check_irq();
}

/* ---------------- memory / ports ---------------- */
static uint8_t mem_r(void *u, uint16_t a) {
    (void)u;
    if (a < 0xa000) return region[a];
    if (a < 0xc000) return region[(sound_bank * 0x2000 + (a - 0xa000)) & 0x3fffff];
    if (a < 0xd000) return 0xff;
    if (a < 0xe000) return rfram[rf_wbank * 0x1000 + (a & 0xfff)];
    return ram[a - 0xe000];
}
static void mem_w(void *u, uint16_t a, uint8_t d) {
    (void)u;
    if (a < 0xc000) return;
    if (a < 0xd000) {
        int r = a & 0x0f;
        if (r > 8) return;
        if (r == 1 && center_pan) {   /* SFX/voices: the game pans them to the player's side */
            int m = (d & 15) > (d >> 4) ? (d & 15) : (d >> 4);
            d = (uint8_t)((m << 4) | m);
        }
        if (rf_on) { rf_catchup(); rf_reg(r, d); }
        if (r == 7) { if (d & 0x40) rf_chsel = d & 7; else rf_wbank = d & 15; }
        log_cmd3(0xB0, r, d);
        return;
    }
    if (a < 0xe000) {
        int off = a & 0xfff;
        if (rf_on) rf_catchup();
        rfram[rf_wbank * 0x1000 + off] = d;
        log_rfmem(off, d);
        return;
    }
    ram[a - 0xe000] = d;
}
static uint8_t port_r(z80 *z, uint8_t p) {
    (void)z;
    if ((p & 0xf0) == 0x80) return ym[0].status;
    if ((p & 0xf0) == 0x90) return ym[1].status;
    if (p == 0xf1) return dummy;
    return 0xff;
}
static void port_w(z80 *z, uint8_t p, uint8_t d) {
    (void)z;
    switch (p & 0xf0) {
    case 0x80: ym_write(0, p & 3, d); break;
    case 0x90: ym_write(1, p & 3, d); break;
    case 0xa0: sound_bank = (sound_bank & ~0x3f) | (d & 0x3f); break;
    case 0xb0: sound_bank = (sound_bank & 0x3f) | ((d & 4) << 4) | ((d & 3) << 7); break;
    case 0xc0:
        if (p & 1) { irq_input &= d; update_irq(); }
        break;
    case 0xd0:
        if ((p & 0x0f) < 8) { irq_control[p & 3] = d; update_irq(); }
        break;
    case 0xf0: if (p == 0xf1) dummy = d; break;
    }
}

static void rf_catchup(void) {
    if (!recording) return;
    uint64_t target = (uint64_t)(cpu.cyc - t0) * (RF_CLOCK / 384.0) / Z80_CLOCK;
    while (rf_done < target) { rf_sample(); rf_done++; }
}

/* ---------------- run ---------------- */
static uint64_t next_ym;
static void run_until(uint64_t cyc) {
    while (cpu.cyc < cyc) {
        cpu.int_pending = irq_line;
        z80_step(&cpu);
        while (cpu.cyc >= next_ym) { ym_tick(); next_ym += 144; }
    }
}

static void wr16(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; }
static void wr32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s region.bin table code out.vgm [maxsec] [tailsec]\n", argv[0]); return 1; }
    int table = atoi(argv[2]), code = atoi(argv[3]);
    double maxsec = argc > 5 ? atof(argv[5]) : 600.0;
    double tailsec = argc > 6 ? atof(argv[6]) : 3.0;
    size_t ol = strlen(argv[4]);
    wav_mode = ol > 4 && !strcmp(argv[4] + ol - 4, ".wav");
    /* the RF5C68 is also rendered for SFX/voice VGMs, to know when the sound has really ended */
    rf_on = wav_mode || table != 1;
    center_pan = getenv("S32_CENTER_PAN") != NULL;
    int log_samples = getenv("S32_LOG_SAMPLES") != NULL;
    region = calloc(1, 0x400000);
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(region, 1, 0x400000, f) != 0x400000) { fprintf(stderr, "bad region\n"); return 1; }
    fclose(f);

    z80_init(&cpu);
    cpu.read_byte = mem_r; cpu.write_byte = mem_w;
    cpu.port_in = port_r; cpu.port_out = port_w;
    next_ym = 144;

    /* boot: 0.5 s, everything logged at time 0 */
    run_until(Z80_CLOCK / 2);

    /* send command */
    recording = 1; t0 = cpu.cyc;
    ram[0x700] = code; ram[0x701] = table;

    /* track playlist pointers (slot e900) to find the loop */
    #define MAXP 512
    uint16_t pptr[MAXP]; uint64_t ptime[MAXP]; size_t pidx[MAXP]; int np = 0;
    uint64_t loop_t = 0, end_t = 0; size_t loop_ev = 0; int found_loop = 0, stopped = 0;
    uint64_t stop_cyc = 0;
    uint64_t maxcyc = t0 + (uint64_t)(maxsec * Z80_CLOCK);
    int song_started = 0;

    while (cpu.cyc < maxcyc) {
        uint16_t pc = cpu.pc;
        if (table == 1 && (pc == 0x13f1 || pc == 0x1359)) {
            uint16_t slot = pc == 0x13f1 ? ((cpu.h << 8) | cpu.l) & 0xff00 : cpu.ix;
            uint16_t ptr = pc == 0x13f1 ? ((cpu.d << 8) | cpu.e) : ((cpu.h << 8) | cpu.l);
            if (slot == 0xe900) {
                song_started = 1;
                uint64_t t = now_samples();
                blk_flush();
                int k;
                for (k = 0; k < np; k++) if (pptr[k] == ptr) break;
                if (k < np) {   /* playlist came back to a position already played */
                    found_loop = 1; loop_t = ptime[k]; loop_ev = pidx[k]; end_t = t;
                    break;
                }
                if (np < MAXP) { pptr[np] = ptr; ptime[np] = t; pidx[np] = eixn; np++; }
            }
        }
        if (pc == 0x1372 && cpu.ix == 0xe900 && !stopped && (table == 1 ? song_started : 1)) {
            stopped = 1; stop_cyc = cpu.cyc;
        }
        if (log_samples && pc == 0x0bd0) smp_hook = ram[0x00d];
        if (table != 1 && !stopped && cpu.cyc - t0 > Z80_CLOCK / 4 && (cpu.cyc & 0x3ff) < 24) {
            /* SFX / voices: stop once no track slot is active and the PCM
               output has been silent for 0.3 s (samples outlive their track) */
            if (rf_on) rf_catchup();
            int active = 0;
            for (int s = 0; s < 8; s++) if (ram[0x900 + s * 0x100] & 0x80) active = 1;
            if (!active && rf_on) {
                size_t N = 32552 * 3 / 10 * 2;
                if (wavn >= N) { active = 0; for (size_t k = wavn - N; k < wavn; k++) if (wav[k]) { active = 1; break; } }
                else active = 1;
            }
            if (!active) { stopped = 1; stop_cyc = cpu.cyc; }
        }
        if (stopped && cpu.cyc - stop_cyc > (uint64_t)(tailsec * Z80_CLOCK)) break;
        cpu.int_pending = irq_line;
        z80_step(&cpu);
        while (cpu.cyc >= next_ym) { ym_tick(); next_ym += 144; }
    }
    blk_flush();
    uint64_t total = found_loop ? end_t : now_samples();
    const char *why = found_loop ? "loop" : (stopped ? "stop" : "timeout");

    if (wav_mode) rf_catchup();
    if (wav_mode) {   /* trim silence, write 16-bit stereo WAV at the RF5C68 native rate */
        size_t a = 0, b = wavn;
        while (a < b && !wav[a]) a++;
        a &= ~(size_t)1;
        while (b > a && !wav[b - 1]) b--;
        b = (b + 1) & ~(size_t)1;
        uint32_t rate = RF_CLOCK / 384, n = (uint32_t)(b - a) * 2;
        uint8_t h[44]; memcpy(h, "RIFF", 4); wr32(h + 4, 36 + n); memcpy(h + 8, "WAVEfmt ", 8);
        wr32(h + 16, 16); wr16(h + 20, 1); wr16(h + 22, 2); wr32(h + 24, rate); wr32(h + 28, rate * 4);
        wr16(h + 32, 4); wr16(h + 34, 16); memcpy(h + 36, "data", 4); wr32(h + 40, n);
        FILE *o = fopen(argv[4], "wb"); fwrite(h, 1, 44, o); fwrite(wav + a, 2, b - a, o); fclose(o);
        printf("frames=%u end=%s\n", n / 4, stopped ? "stop" : "timeout");
        return 0;
    }

    /* ---- write VGM ---- */
    FILE *o = fopen(argv[4], "wb");
    uint8_t hdr[0x100]; memset(hdr, 0, sizeof hdr);
    memcpy(hdr, "Vgm ", 4);
    wr32(hdr + 0x08, 0x171);
    wr32(hdr + 0x2C, Z80_CLOCK | 0x40000000u | 0x80000000u);  /* dual YM3438 */
    wr32(hdr + 0x34, 0x100 - 0x34);
    wr32(hdr + 0x40, RF_CLOCK);
    fwrite(hdr, 1, 0x100, o);
    uint32_t pos = 0x100, loop_off = 0;
    uint64_t cur = 0;
    #define EMIT(b, n) do { fwrite(b, 1, n, o); pos += n; } while (0)
    for (size_t i = 0; i <= eixn; i++) {
        uint64_t t = i < eixn ? eix[i].t : total;
        if (found_loop && i == loop_ev) { /* make the loop point exact */
            if (loop_t > t) loop_t = t;
        }
        if (t > total) t = total;
        uint64_t target = (found_loop && i == loop_ev) ? loop_t : t;
        while (cur < target) {
            uint64_t d = target - cur; uint8_t w[3];
            if (d <= 16) { w[0] = 0x70 + (uint8_t)(d - 1); EMIT(w, 1); cur += d; }
            else { if (d > 65535) d = 65535; w[0] = 0x61; w[1] = d; w[2] = d >> 8; EMIT(w, 3); cur += d; }
        }
        if (found_loop && i == loop_ev) loop_off = pos;
        if (i == eixn) break;
        if (found_loop && eix[i].t >= end_t && i >= loop_ev && eix[i].t > loop_t) break;
        size_t len = (i + 1 < eixn ? eix[i + 1].off : evlen) - eix[i].off;
        EMIT(ev + eix[i].off, len);
    }
    while (cur < total) {
        uint64_t d = total - cur; if (d > 65535) d = 65535;
        uint8_t w[3] = {0x61, (uint8_t)d, (uint8_t)(d >> 8)}; EMIT(w, 3); cur += d;
    }
    uint8_t e = 0x66; EMIT(&e, 1);
    wr32(hdr + 0x04, pos - 4);
    wr32(hdr + 0x18, (uint32_t)total);
    if (found_loop) { wr32(hdr + 0x1C, loop_off - 0x1C); wr32(hdr + 0x20, (uint32_t)(total - loop_t)); }
    fseek(o, 0, SEEK_SET); fwrite(hdr, 1, 0x100, o); fclose(o);
    printf("samples=%llu loop_start=%llu loop_len=%llu end=%s\n",
           (unsigned long long)total, (unsigned long long)(found_loop ? loop_t : 0),
           (unsigned long long)(found_loop ? total - loop_t : 0), why);
    return 0;
}
