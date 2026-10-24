"""Audio: TON banks (sound effect and voice samples) and compressed .PCM voices.

Both are proprietary formats that vgmstream cannot read on its own, so the
samples are written as raw PCM (.raw) and each output folder gets a .txth that
describes them, which makes them playable in vgmstream without conversion.
"""
import os
import struct

from .lzss import try_decompress
from .util import iter_inputs, stem

SCSP_RATE = 44100
REFERENCE_KEY = 60      # key played by the game's sequences (checked in GKSE1, SEALL)
PCM_VOICE_RATE = 11025  # default rate for .PCM voices (KOJIN, YBT, END; checked by listening)
PCM_RATE_OVERRIDES = {  # files that use another rate (file name -> Hz)
    'BOOG_1.PCM': 22050,
}


def key_to_rate(base_note):
    return round(SCSP_RATE * 2 ** ((REFERENCE_KEY - base_note) / 12))


# ------------------------------------------------------------------- TON

def parse_ton(data):
    """Parse a TON bank. Return the list of layers, or None if it isn't one.

    Layout (big-endian u16 offsets at the start of the file):
      [0] mixer [1] velocity [2] PEG [3] PLFO [4..] voices
    Voice: 4 bytes (byte 2 = layer count - 1), then 32-byte layers that mirror
    the registers of an SCSP slot:
      +0 key low, +1 key high, +2 u16 (bit 4 = 8-bit PCM, bits 5-6 = loop mode,
      bits 0-3 = address high bits), +4 address low bits, +6 loop start (LSA),
      +8 loop end (LEA), +0x19 base note.
    The sample address is a direct offset into the file.
    """
    if len(data) < 16:
        return None
    first = struct.unpack_from('>H', data, 0)[0]
    if first < 10 or first % 2 or first > len(data) or first > 0x400:
        return None
    table = struct.unpack_from('>%dH' % (first // 2), data, 0)
    if list(table[:4]) != sorted(table[:4]) or table[0] != first:
        return None
    layers = []
    for vi, voff in enumerate(table[4:]):
        if voff + 36 > len(data):
            return None
        nlayers = struct.unpack_from('>b', data, voff + 2)[0] + 1
        if not 1 <= nlayers <= 16:
            return None
        for li in range(nlayers):
            o = voff + 4 + li * 32
            if o + 32 > len(data):
                return None
            w2, sa_lo, lsa, lea = struct.unpack_from('>HHHH', data, o + 2)
            sa = ((w2 & 0xF) << 16) | sa_lo
            pcm8 = bool(w2 & 0x10)
            nsamples = lea + 1
            nbytes = nsamples * (1 if pcm8 else 2)
            if sa + nbytes > len(data) + 2:
                return None
            layers.append(dict(voice=vi, layer=li, key_lo=data[o], key_hi=data[o + 1],
                               offset=sa, nsamples=nsamples, pcm8=pcm8,
                               loop=(w2 >> 5) & 3, loop_start=lsa,
                               base_note=data[o + 0x19]))
    return layers or None


def ton_sample_bytes(data, layer):
    n = layer['nsamples'] * (1 if layer['pcm8'] else 2)
    return data[layer['offset']:layer['offset'] + n]


# ---------------------------------------------------------------- output

COMMON = ['channels = 1', 'start_offset = 0', 'num_samples = data_size']


def write_folder_txth(out_dir, rows, comment):
    """Write a single .txth for the whole folder.

    rows: list of (file_name, codec, sample_rate, loop) where loop is None or
    (start, end). If every file shares the same settings and none loops, the
    .txth holds the values directly; otherwise it points to a .names.txt table
    (one line per file), read by vgmstream's name_table feature.
    """
    lines = ['# ' + l for l in comment.splitlines()]
    uniform = len({(c, r) for _, c, r, _ in rows}) == 1 and not any(lp for *_, lp in rows)
    if uniform:
        lines += ['codec = %s' % rows[0][1], 'sample_rate = %d' % rows[0][2]] + COMMON
    else:
        lines += ['name_table = .names.txt',
                  'codec = name_value1',
                  'sample_rate = name_value2'] + COMMON + [
                  'loop_start_sample = name_value4',
                  'loop_end_sample = name_value5',
                  'loop_flag = name_value3']
        table = ['# file: codec, sample rate, loop (0/1), loop start, loop end']
        for name, codec, rate, lp in rows:
            table.append('%s: %s, %d, %d, %d, %d' % (name, codec, rate, 1 if lp else 0,
                                                    lp[0] if lp else 0, lp[1] if lp else 0))
        with open(os.path.join(out_dir, '.names.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(table) + '\n')
    with open(os.path.join(out_dir, '.txth'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


# ------------------------------------------------------------- processing

def extract_ton(path, out_dir):
    data = open(path, 'rb').read()
    layers = parse_ton(data)
    if not layers:
        return 0
    name = os.path.basename(path).rsplit('.', 1)[0]
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for L in layers:
        fname = '%s_%02d' % (name, L['voice']) + ('_%d' % L['layer'] if L['layer'] else '') + '.raw'
        with open(os.path.join(out_dir, fname), 'wb') as f:
            f.write(ton_sample_bytes(data, L))
        rows.append((fname, 'PCM8' if L['pcm8'] else 'PCM16BE', key_to_rate(L['base_note']),
                     (L['loop_start'], L['nsamples']) if L['loop'] else None))
    write_folder_txth(out_dir, rows,
                      'Samples from TON bank %s.\n'
                      'sample_rate = 44100 * 2^((60 - base note) / 12)' % os.path.basename(path))
    return len(layers)


def extract_pcm_voice(path, out_dir):
    pcm = try_decompress(open(path, 'rb').read())
    if pcm is None:
        return None
    os.makedirs(out_dir, exist_ok=True)
    fname = os.path.basename(path).rsplit('.', 1)[0] + '.raw'
    with open(os.path.join(out_dir, fname), 'wb') as f:
        f.write(pcm)
    return fname


def extract_all(paths, out, log=print):
    """paths: game files and/or folders. The output mirrors their tree:
    GK_V.BIN -> out/GK_V/GK_V_00.raw..., KOJIN/GOKU18.PCM -> out/KOJIN/GOKU18.raw"""
    n_banks = n_samples = n_voices = 0
    voice_dirs = {}
    for p, rel in iter_inputs(paths):
        up = rel.upper()
        if up.endswith('.PCM'):
            d = os.path.join(out, os.path.dirname(rel))
            fname = extract_pcm_voice(p, d)
            if fname:
                rate = PCM_RATE_OVERRIDES.get(os.path.basename(rel).upper(), PCM_VOICE_RATE)
                voice_dirs.setdefault(d, []).append((fname, 'PCM8', rate, None))
                n_voices += 1
                log("  %-24s voice" % rel)
            else:
                log("  ! %s: unrecognized stream" % rel)
            continue
        if up.endswith(('.AIF', '.CPK', '.TSK')):
            continue
        k = extract_ton(p, os.path.join(out, stem(rel)))
        if k:
            n_banks += 1
            n_samples += k
            log("  %-24s TON bank, %d samples" % (rel, k))
    for d, rows in voice_dirs.items():
        write_folder_txth(d, rows,
                          'Decompressed .PCM voices (LZSS): signed 8-bit PCM.\n'
                          'KOJIN, YBT and END play at 11025 Hz; BOOG_1 plays at 22050 Hz.')
    log("%d TON banks (%d samples), %d .PCM voices -> %s" % (n_banks, n_samples, n_voices, out))
