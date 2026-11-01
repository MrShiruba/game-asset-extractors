"""PCM data of the sound ROMs (RF5C68, 8-bit sign + 7-bit magnitude): the driver's sample table,
playback rates, raw files with their vgmstream description, and voice lines rebuilt from samples."""
import os, json
import numpy as np


# Voice/SFX commands are small MIDI sequences: each sample is a note, the pauses are delta times. All the
# pauses in this game are multiples of 64 MIDI ticks (77.8 ms). The exact start of a piece moves by up to
# ~0.7 ms with the state of the PCM streaming, so two commands with the same pieces and the same pauses
# counted in 64-tick steps are the same sound.
SEQ_TICK = 3431.5                  # 64 MIDI ticks, in 1/44100 s

# Playback step (RF5C68 FD register, 0x800 = 1:1 at 32552 Hz) the sound driver uses
# for each PCM sample, measured once by running every sound command in s32snd.
# Samples not listed use 704 (11186 Hz), the voice rate. For a sample used both as a sound
# effect and by the music, the sound effect's rate is kept (089, the fight-start cymbal: 1024
# in the SFX command, 1152 when the music plays it; the music keeps its own rate in its VGM).
PCM_STEP_DEFAULT = 704
# PCM nothing plays (sample 001, blocks no table points to): no rate in the game, 928 (14750 Hz) chosen by ear
PCM_STEP_UNUSED = 928
PCM_STEPS = {0: 960, 1: PCM_STEP_UNUSED, 2: 1024, 3: 960, 4: 960, 5: 960, 6: 960, 7: 960, 8: 960, 9: 960, 10: 960, 11: 960, 12: 960, 13: 1040, 14: 960, 15: 960, 16: 960, 17: 960, 18: 960, 19: 960, 20: 960, 21: 1296, 22: 1296, 89: 1024, 94: 1024, 95: 1024, 96: 928, 97: 928, 98: 928, 99: 672, 100: 928, 101: 928, 102: 928, 103: 928, 104: 928, 105: 928, 106: 928, 107: 928, 108: 928, 109: 928, 110: 928, 111: 928, 112: 928, 113: 928, 114: 1024, 115: 928, 116: 928, 117: 928, 118: 928, 119: 496, 120: 496, 121: 496, 122: 496, 123: 496, 124: 496, 125: 496, 126: 496, 127: 496, 128: 496, 129: 496, 130: 496, 131: 496, 132: 496, 133: 496, 134: 496, 138: 696, 139: 696, 140: 928, 141: 928, 142: 640, 143: 1024, 253: 1024, 254: 928}


def pcm_table(region):
    """sample table of the sound driver: 255 pointers at 0x7e51 -> 6-byte entries."""
    out = []
    for i in range(256):
        p = region[0x7E51 + 2 * i] | region[0x7E52 + 2 * i] << 8
        e = region[p:p + 6]
        if e[0] == 0xFF:
            break
        bank = (e[1] & 0x3F) | ((e[0] & 4) << 4) | ((e[0] & 3) << 7)
        out.append(bank * 0x2000 + (e[2] << 8) - 0xA000)
    return out


TXTH = """# vgmstream TXTH: raw RF5C68 PCM, 8-bit sign + 7-bit magnitude, as stored in the sound ROMs.
# The playback rate of each file is in .names.txt (the rate the game's sound driver uses).
codec = PCM8_SB
channels = 1
name_table = .names.txt
sample_rate = name_value
num_samples = data_size
"""


def rate_of(step):
    return round(12500000 * step / (384 * 2048))


def pcm_samples(region):
    """Every PCM sample of the sample table (end marker 0xFF removed), byte for byte as stored,
    plus the blocks of PCM data that no table points to."""
    starts = pcm_table(region)
    covered = np.zeros(len(region), bool)
    samples = []
    for i, s in enumerate(starts):
        e = region.index(b"\xff", s)
        covered[s:e + 1] = True
        step = PCM_STEPS.get(i, PCM_STEP_DEFAULT)
        samples.append({"index": i, "name": "sample_%03d" % i, "rom_offset": hex(s), "bytes": e - s,
                        "sample_rate": rate_of(step), "fd_step": step, "data": region[s:e]})
    unused = []
    a = 0x100000
    while a < len(region):
        if covered[a] or region[a] == 0xFF:          # samples are padded with 0xFF between them
            a += 1
            continue
        e = region.find(b"\xff", a)
        e = len(region) if e < 0 else e
        blk = region[a:e]
        if len(blk) >= 256 and len(set(blk)) > 4 and not covered[a:e].any():
            unused.append({"name": "unreferenced_%06x" % a, "rom_offset": hex(a), "bytes": len(blk),
                           "sample_rate": rate_of(PCM_STEP_UNUSED), "fd_step": PCM_STEP_UNUSED, "data": blk})
        a = e
    return samples, unused


def write_raw_folder(outdir, folder, items, what):
    """items: (name, bytes, sample_rate). Writes the .raw files and the vgmstream description."""
    if not items:
        return
    d = os.path.join(outdir, folder)
    os.makedirs(d, exist_ok=True)
    for name, data, _ in items:
        open(os.path.join(d, name + ".raw"), "wb").write(data)
    with open(os.path.join(d, ".raw.txth"), "w", newline="\n") as f:
        f.write(TXTH.replace("as stored in the sound ROMs", what))
    with open(os.path.join(d, ".names.txt"), "w", newline="\n") as f:
        f.write("# file: sample rate (Hz)\n" + "\n".join("%s: %d" % (n, r) for n, _, r in items) + "\n")


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


def export_samples_unsorted(region, outdir, log):
    """No C compiler: the sound commands cannot be run, so the samples cannot be sorted by table.
    Every sample is written as stored, in sample-table order."""
    samples, unused = pcm_samples(region)
    write_raw_folder(outdir, "samples-unsorted", [(s["name"], s["data"], s["sample_rate"]) for s in samples],
                     "as stored in the sound ROMs (not sorted: no C compiler to run the sound driver)")
    write_raw_folder(outdir, "unused", [(u["name"], u["data"], u["sample_rate"]) for u in unused],
                     "PCM data that no table of the sound program points to, as stored in the sound ROMs")
    write_json(os.path.join(outdir, "samples.json"),
               [{k: v for k, v in s.items() if k != "data"} for s in samples + unused])
    log("samples-unsorted: %d samples, unused: %d blocks" % (len(samples), len(unused)))


def note_channels(region, hdr):
    """MIDI channel of each note of a voice/SFX sequence, in order. These sequences are MIDI
    data: a header byte, then note-on events (0x9n note velocity, running status) each followed
    by a variable-length delta time, ended by FF 2F 00. In the dialogues (table 6) the first
    character's line is on channel 10 and the answer on channel 11. Returns None on anything else."""
    a, st, out = hdr + 1, None, []
    while region[a] != 0xFF:
        if region[a] & 0x80:
            st = region[a]; a += 1
        if st is None or st >> 4 != 9:
            return None
        out.append(st & 15)
        a += 2
        while region[a] & 0x80:
            a += 1
        a += 1
    return out


def build_line(region, events):
    """Original bytes of each piece, placed at the time the game starts it (silence = 0x80).
    A piece started on the channel that is still playing the previous one cuts it, as the
    RF5C68 does. Returns (bytes, step) or None if the pieces use different rates or overlap
    on different channels (they would have to be mixed)."""
    if len({e[1] for e in events}) != 1:
        return None
    step = events[0][1]
    rate = 12500000 * step / (384 * 2048)
    table = pcm_table(region)
    out, prev_ch = bytearray(), None
    t0 = events[0][2]
    for smp, _, t, ch in events:
        s = table[smp]
        data = region[s:region.index(b"\xff", s)]
        pos = int(round((t - t0) / 44100 * rate))
        if pos < len(out):
            if ch != prev_ch:
                return None
            del out[pos:]                      # restarted channel: previous piece is cut
        out += b"\x80" * (pos - len(out)) + data
        prev_ch = ch
    return bytes(out), step
