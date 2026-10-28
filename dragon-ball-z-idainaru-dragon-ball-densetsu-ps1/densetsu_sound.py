#!/usr/bin/env python3
"""
densetsu_sound.py - sound extraction / reinsertion tool for
Idainaru Dragon Ball Densetsu (PlayStation, Japan, SLPS-00355).

The SOUND/*.B files are sequences of Sony VAB banks ("pBAV") stored in
fixed-size slots. This game pads each VAB header to a sector boundary
(0xC20 -> 0x1000) before the sample data, which generic tools do not expect.
This tool handles that and uses tables recovered from GAME.EXE to sort
the output (see README.md):

  CR.B    voice clips, sorted by character (from CHR_DATA/CRDD.B and the
          special-move / story scene scripts) and named by the voice ID
  ATB.B   battle SFX banks, named by the character(s) that load them
  CHSE.B  sound effects of the special moves (and story scenes), by
          scene number and character

COMMANDS

  extract  INPUT.B [INPUT.B ...] OUTDIR [--rate 11025] [--disc DIR]
      Writes every sample as a standard .vag file (original ADPCM data,
      no re-encoding) into OUTDIR/<file>/, plus manifest.json (used by
      rebuild) and index.csv (human-readable list). To sort CR.B voices,
      the disc files CHR_DATA/CRDD.B and CH_BIN*/ are read from DIR
      (default: the folder that contains SOUND/).

  rebuild  FOLDER ORIGINAL.B OUTPUT.B
      Reads the .vag files in FOLDER (edited or replaced) and rebuilds
      the .B: size tables and bank size updated, duplicate banks updated
      too, slot capacity checked. Untouched banks stay byte-identical,
      and the output file has the same size as the original.

  info     INPUT.B
      Lists banks and the free space left in each slot.

  scan     FOLDER [--align 16] [--min 48] [--extract DIR]
      Looks for PS1 audio in every file of a folder: signed containers
      (VAB, VAG, SEQ...) and headerless raw SPU-ADPCM.

To replace a sound: encode your WAV as mono VAG (11025 Hz recommended, e.g.
with psxavenc or MFAudio), overwrite the .vag with the same name, then run
rebuild. A longer sound is accepted as long as it fits in its slot
(see "info").
"""
import argparse, csv, hashlib, json, os, struct, sys

VAB_HDR = 0x20
PROG_TBL = 0x800
TONES_PER_PROG = 16
TONE_SIZE = 32
SECTOR = 0x800
DEFAULT_RATE = 11025

# ---------------------------------------------------------------------------
# Tables recovered from GAME.EXE (identical in VS.EXE, SP.EXE, TITLE.EXE...)
# ---------------------------------------------------------------------------

# Character table, GAME.EXE 0x8008897C: char[18] x 38 paths "\ATx\XXX.B;1".
# Character IDs are 1-based positions in this table.
CHARACTERS = ['GKN', 'GKS', 'S3', 'GHN', 'GHC', 'GSM', 'SS', 'GT', 'VG', 'VGS',
              'VGI', 'TRC', 'TRF', 'PC', 'KL', 'GX', 'VT', 'BU', 'VG', 'NP',
              'GW', 'GES', 'BT', 'RC', 'GD', 'FZ', 'SIX', 'SVN', 'ETN', 'NIN',
              'TWN', 'DB', 'SB', 'FB', 'CL', 'JR', 'VGI', 'TRA']

# ATB.B sector offset per character ID, GAME.EXE 0x800922C4 (u16[39]).
# Banks are 12 sectors (0x6000 bytes) apart, so bank = sector // 12.
ATB_SECTORS = [0, 0, 0, 0, 12, 12, 24, 24, 36, 48, 48, 48, 72, 60, 108, 120, 84,
               96, 312, 48, 132, 144, 156, 168, 180, 192, 204, 216, 228, 240,
               252, 264, 300, 324, 336, 276, 288, 48, 60]

# CHSE.B: sound banks of the scenes where gameplay freezes. GAME.EXE 0x800356F0
# picks scene n (1-based) from the character's ID; CH_BIN*/CH_nn.BIN is loaded
# with the same n. Scenes 1-53 are special moves, 54-63 story scenes.
# Special moves, up to 3 per character, played in rotation (GAME.EXE 0x800877C0,
# u8[3] per ID):
CHSE_SPECIAL_MOVES = [[1], [1, 2], [49, 1], [50, 3], [5], [4], [6], [7], [9], [18, 19], [18, 19],
               [18, 19], [13], [14, 15], [10, 11], [12], [16, 17], [41], [34, 35], [18, 19],
               [20], [21, 45], [22], [23], [24], [25], [42, 43, 44], [26, 48], [27], [28],
               [29], [30, 46], [33], [36, 37], [38, 39], [47, 31], [32], [18, 19], [14, 15]]
# Story scenes, once per stage (GAME.EXE 0x80087838, u8 bank + u8 stage per ID,
# stage 0-based):
CHSE_STORY_SCENES = {3: (54, 6), 6: (55, 5), 13: (56, 3), 14: (58, 2), 16: (57, 6),
                     17: (59, 7), 18: (63, 5), 25: (61, 1), 26: (60, 2), 36: (62, 4)}
# Cell Jr (JR, ID 36) -> 51, 52 or 53 depending on how many are in the team.
CHSE_SPECIAL = {51: 'JR-team-a', 52: 'JR-team-b', 53: 'JR-team-c'}


def chse_bank_owners():
    owners = {}
    for cid, banks in enumerate(CHSE_SPECIAL_MOVES):
        if cid == 0:
            continue
        for b in banks:
            owners.setdefault(b, [])
            if CHARACTERS[cid - 1] not in owners[b]:
                owners[b].append(CHARACTERS[cid - 1])
    for cid, (b, stage) in CHSE_STORY_SCENES.items():
        # the stage byte is 0-based (same counter as the CRDD.B block): 1 = STG2
        owners.setdefault(b, []).append(f'{CHARACTERS[cid - 1]}-stage{stage + 1}')
    for b, tag in CHSE_SPECIAL.items():
        owners.setdefault(b, []).append(tag)
    return owners


# CR.B: sector = start + slot * 34, with slot computed from the voice ID by
# GAME.EXE 0x800631D4. Eleven slots are skipped: they hold the end of long voices.
CR_SKIPS = [(278, 1), (494, 1), (1161, 1), (1162, 4), (1163, 1), (1284, 2), (1495, 1)]


def cr_slot_of_voice(vid):
    return vid + sum(n for limit, n in CR_SKIPS if vid >= limit)


# Scene script files, GAME.EXE 0x800870AC (char[27] x 64, index = scene n).
def scene_file(n):
    if n in (0, 8, 40):
        return None  # CH_NO.BIN (empty)
    if 51 <= n <= 53:
        return f'CH_BIN2/CH_32_{n - 50}.BIN'
    if 54 <= n <= 63:
        return f'CH_BIN3/IN_{n - 53:02d}.BIN'
    if n == 32:
        return 'CH_BIN2/CH_32_1.BIN'
    return f'CH_BIN{1 if n < 30 else 2}/CH_{n:02d}.BIN'


# Per-character special-move line, script opcode 0x32, GAME.EXE 0x800921D8 (u16[3] per ID).
# Bit 0x4000: the voice is followed by voice + 1.
CHARACTER_LINES = [None, (0x5d2, 0x5d3, 0x5d4), (0x5d2, 0x5d3, 0x5d4), (0x5d2, 0x5d3, 0x5d4),
               (0x5da, 0x5da, 0x5db), (0x5da, 0x5da, 0x5db), (0x5e0, 0x5e1, 0x5e2),
               (0x5e0, 0x5e1, 0x5e2), (0x5e6, 0x5e6, 0x5e7), (0x5ed, 0x5ee, 0x5ef),
               (0x5ed, 0x5ee, 0x5ef), (0x5ed, 0x5ee, 0x5ef), (0x5f9, 0x5fa, 0x5fb),
               (0x5f3, 0x5f3, 0x5f5), (0x60b, 0x60b, 0x60c), (0x610, 0x610, 0x611),
               (0x600, 0x601, 0x602), (0x606, 0x606, 0x606), (0x65e, 0x65f, 0x660),
               (0x5ed, 0x5ee, 0x5ef), (0x613, 0x613, 0x614), (0x4616, 0x4616, 0x619),
               (0x461d, 0x461d, 0x620), (0x4621, 0x4621, 0x624), (0x4629, 0x4629, 0x62c),
               (0x462f, 0x462f, 0x632), (0x636, 0x636, 0x637), (0x63a, 0x63b, 0x63c),
               (0x63d, 0x63d, 0x63e), (0x63f, 0x63f, 0x640), (0x644, 0x644, 0x645),
               (0x649, 0x649, 0x64a), (0x659, 0x659, 0x65a), (0x662, 0x663, 0x664),
               (0x666, 0x666, 0x666), (0x651, 0x652, 0x653), (0x655, 0x656, 0x657),
               (0x5ed, 0x5ee, 0x5ef), (0x5f3, 0x5f3, 0x5f5)]
ENDING_VOICES = [1493]  # ENDING.EXE 0x800117E0
# Scene voices whose speaker is not the scene's character (identified by ear).
# 1642: the whole Ginyu Force, in their group pose (IN_08.BIN).
SCENE_SPEAKER_OVERRIDES = {1642: 'GINYU_FORCE'}
# Voices no data file or code constant references, identified by ear.
# 1639-1641: Ginyu Force group lines with 3, 4 and 5 members.
UNREFERENCED_VOICES = {286: 'GKN', 1494: 'GKN', 1508: 'GT', 1509: 'GT', 1514: 'VG', 1520: 'TRF',
                       1521: 'TRF', 1524: 'TRF', 1528: 'TRC', 1545: 'PC', 1550: 'KL', 1560: 'GW',
                       1562: 'GW', 1567: 'GES', 1571: 'BT', 1576: 'RC', 1579: 'RC', 1585: 'GD',
                       1588: 'FZ', 1592: 'SIX', 1639: 'GINYU_FORCE', 1640: 'GINYU_FORCE',
                       1641: 'GINYU_FORCE'}
CR_VOICE_COUNT = 1643  # 1654 slots in CR.B minus the 11 used by long voices


# CRDD.B list owners use a different numbering: the 44-entry portrait list
# (CHR_DATA/OV_CHR_A.B). GAME.EXE 0x80091F6C maps each portrait to a voice
# group (= speaker), and 0x80091F98 gives each group's voice-ID range.
PORTRAIT_VOICE_GROUP = [0, 1, 2, 3, 4, 7, 1, 9, 2, 2, 12, 13, 7, 0, 1, 2, 14, 7, 5, 6, 8, 0, 0,
                        10, 11, 15, 16, 0, 0, 0, 17, 18, 0, 0, 1, 7, 18, 0, 2, 8, 0, 7, 16, 0]
VOICE_GROUP_RANGES = {1: (0, 296), 2: (296, 516), 3: (516, 725), 4: (725, 908), 5: (908, 919),
                      6: (919, 947), 7: (947, 1183), 8: (1183, 1195), 9: (1195, 1274),
                      10: (1274, 1292), 11: (1292, 1298), 12: (1298, 1333), 13: (1333, 1376),
                      14: (1376, 1408), 15: (1408, 1418), 16: (1418, 1451), 17: (1451, 1461),
                      18: (1461, 1475)}
# Fighters are identified by the one character never listed as their partner
# (nobody talks to themselves) and use the game's archive codes. Support
# characters have no name anywhere in the game data; they were identified by
# ear and use descriptive names.
VOICE_GROUP_SPEAKER = {1: 'GKN', 2: 'GHN', 3: 'PC', 4: 'KL', 5: 'KAMI', 6: 'KAIO', 7: 'VG',
                       8: 'TENSHINHAN', 9: 'TRF', 10: 'MR_SATAN', 11: 'ANNOUNCER', 12: 'GT',
                       13: 'TRC', 14: 'GX', 15: 'VIDEL', 16: 'KAIOSHIN', 17: 'KIBITO',
                       18: 'ROU_KAIOSHIN'}


def voice_group(portrait, voice):
    g = PORTRAIT_VOICE_GROUP[portrait] if portrait < len(PORTRAIT_VOICE_GROUP) else 0
    if not g:
        g = next((k for k, (lo, hi) in VOICE_GROUP_RANGES.items() if lo <= voice < hi), 0)
        if not g and 1475 <= voice < 1482:
            g = 16
    return g


def speaker_name(group):
    return VOICE_GROUP_SPEAKER.get(group, f'speaker_{group:02d}')


def char_name(cid):
    if 1 <= cid <= len(CHARACTERS):
        return CHARACTERS[cid - 1]
    return 'ANY' if cid == 0x40 else f'CHR{cid}'


def parse_crdd(path):
    """CHR_DATA/CRDD.B: per-stage battle dialogue lists (see README).
    Yields (stage, portrait_id, situation, partner_id, voice)."""
    d = open(path, 'rb').read()
    base = 0x801CA000  # load address (GAME.EXE 0x8005EAD4)
    for st in range(len(d) // 0x8000):
        blk = d[st * 0x8000:(st + 1) * 0x8000]
        p = struct.unpack_from('<I', blk, 0)[0] - base
        while 0 <= p <= len(blk) - 8:
            key, q = struct.unpack_from('<II', blk, p)
            p += 8
            if not key and not q:
                break
            q -= base
            for row in range(11):
                for e in range(16):
                    w = struct.unpack_from('<I', blk, q + row * 64 + e * 4)[0]
                    if w:
                        yield st + 1, key, row, w & 0x7F, (w >> 8) & 0xFFFF


def scene_script_voices(path):
    """Voice IDs played by script opcode 0x2F (GAME.EXE handler 0x8003EED8)."""
    d = open(path, 'rb').read()
    out = []
    for q in range(0, len(d) - 4, 2):
        if d[q] == 0x2F and d[q + 1] == 0:
            v = struct.unpack_from('<H', d, q + 2)[0] & 0x7FFF
            if 1482 <= v < CR_VOICE_COUNT and v not in out:  # special-move / story voice block
                out.append(v)
    return out


def voice_attribution(disc):
    """Return {voice: [(character, kind, detail), ...]} from the disc data files."""
    att = {}

    def add(v, who, kind, detail, sub=None, suffix=''):
        if 0 <= v < CR_VOICE_COUNT and not any(x[:3] == (who, kind, detail) for x in att.setdefault(v, [])):
            att[v].append((who, kind, detail, sub or kind, suffix))

    crdd = os.path.join(disc, 'CHR_DATA', 'CRDD.B')
    if os.path.exists(crdd):
        for st, key, row, partner, v in parse_crdd(crdd):
            g = voice_group(key, v)
            add(v, speaker_name(g), 'battle',
                f'stage {st}, partner {char_name(partner)}, situation {row}, portrait {key}, voice group {g}',
                f'battle/STG{st}', f'_{char_name(partner)}')
    for cid, ent in enumerate(CHARACTER_LINES):
        for raw in ent or ():
            v = raw & 0x3FFF
            add(v, char_name(cid), 'special', 'character line (all special moves)')
            if raw & 0x4000:
                add(v + 1, char_name(cid), 'special', 'character line, second part')
    owners = chse_bank_owners()
    for n in range(1, 64):
        rel = scene_file(n)
        p = os.path.join(disc, rel) if rel else None
        if p and os.path.exists(p):
            for v in scene_script_voices(p):
                who = SCENE_SPEAKER_OVERRIDES.get(v, owners.get(n, ['unknown'])[0].split('-stage')[0])
                kind = 'story' if n >= 54 else 'special'
                add(v, who, kind, f'{kind} scene {n} ({os.path.basename(p)}), speaker ' + ('identified by ear' if v in SCENE_SPEAKER_OVERRIDES else 'assumed = scene character'))
    for v in ENDING_VOICES:
        add(v, 'GKN', 'ending', 'ENDING.EXE (speaker identified by ear)')
    for v, who in UNREFERENCED_VOICES.items():
        if v not in att:
            add(v, who, 'unreferenced', 'not referenced by the game data or code; identified by ear')
    return att


def find_disc_root(path, explicit=None):
    if explicit:
        return explicit
    d = os.path.dirname(os.path.abspath(path))
    for cand in (os.path.dirname(d), d):
        if os.path.exists(os.path.join(cand, 'CHR_DATA', 'CRDD.B')):
            return cand
    return None


def atb_bank_owners():
    owners = {}
    for cid in range(1, len(ATB_SECTORS)):
        owners.setdefault(ATB_SECTORS[cid] // 12, [])
        name = CHARACTERS[cid - 1]
        if name not in owners[ATB_SECTORS[cid] // 12]:
            owners[ATB_SECTORS[cid] // 12].append(name)
    return owners


# Per-file layout. 'slot' is the fixed bank spacing used by the game.
PROFILES = {
    'CR.B': {'slot': 0x11000, 'kind': 'voice'},
    'CHSE.B': {'slot': 0x1F000, 'kind': 'scene'},
    'ATB.B': {'slot': 0x6000, 'kind': 'character'},
}


# ---------------------------------------------------------------------------
# VAB parsing
# ---------------------------------------------------------------------------

def find_banks(d):
    offs, i = [], 0
    while (i := d.find(b'pBAV', i)) >= 0:
        if i + 0x20 <= len(d):
            ps, ts, vs = struct.unpack_from('<HHH', d, i + 0x12)
            if 0 < ps <= 128 and vs <= 254 and ts <= 2048:
                offs.append(i)
        i += 4
    return offs


def bank_layout(d, o):
    ver, vid, total = struct.unpack_from('<III', d, o + 4)
    ps, ts, vs = struct.unpack_from('<HHH', d, o + 0x12)
    tones_off = o + VAB_HDR + PROG_TBL
    size_off = tones_off + ps * TONES_PER_PROG * TONE_SIZE
    hdr_end = size_off + 512
    vb = hdr_end
    aligned = o + ((hdr_end - o + SECTOR - 1) & ~(SECTOR - 1))
    if aligned != hdr_end and aligned <= len(d) and not any(d[hdr_end:aligned]):
        vb = aligned
    sizes = [struct.unpack_from('<H', d, size_off + 2 * k)[0] * 8 for k in range(vs + 1)]
    tones = {}
    for t in range(ps * TONES_PER_PROG):
        a = tones_off + t * TONE_SIZE
        vag = struct.unpack_from('<H', d, a + 22)[0]
        if 0 < vag <= vs and vag not in tones:
            tones[vag] = {'vol': d[a + 2], 'pan': d[a + 3], 'center': d[a + 4], 'fine': d[a + 5]}
    return dict(ps=ps, ts=ts, vs=vs, total=total, size_off=size_off,
                hdr_len=hdr_end - o, vb_off=vb - o, sizes=sizes, tones=tones)


def looks_like_adpcm(data, blocks=8):
    """Sanity check: the first blocks must have valid SPU-ADPCM headers."""
    for p in range(0, min(len(data), blocks * 16), 16):
        if not block_ok(data, p):
            return False
    return len(data) >= 16


def block_ok(d, p):
    h, f = d[p], d[p + 1]
    return (h >> 4) <= 4 and (h & 15) <= 12 and f in (0, 1, 2, 3, 4, 6, 7)


# ---------------------------------------------------------------------------
# VAG files
# ---------------------------------------------------------------------------

def vag_header(data_len, rate, name):
    return (b'VAGp' + struct.pack('>IIII', 0x20, 0, data_len, rate)
            + b'\0' * 12 + name.encode('ascii', 'replace')[:16].ljust(16, b'\0'))


def read_vag(path, orig_md5=None):
    """Return the ADPCM payload, or None if it is unchanged since extraction."""
    raw = open(path, 'rb').read()
    if raw[:4] == b'VAGp':
        size = struct.unpack_from('>I', raw, 12)[0]
        data = raw[48:48 + size] if size else raw[48:]
    else:  # raw ADPCM without header
        data = raw
    if orig_md5 and hashlib.md5(data).hexdigest() == orig_md5:
        return None
    if len(data) % 16:
        data += b'\0' * (16 - len(data) % 16)
    if len(data) // 8 > 0xFFFF:
        sys.exit(f'{path}: too long ({len(data)} bytes, max {0xFFFF * 8})')
    if not any(data[i + 1] & 1 for i in range(0, len(data), 16)):
        print(f'  warning: {os.path.basename(path)} has no end flag, appending an end block',
              file=sys.stderr)
        data += b'\0\x07' + b'\0' * 14
    return data


# ---------------------------------------------------------------------------
# Naming / sorting
# ---------------------------------------------------------------------------

def bank_naming(fname, offsets, d, disc=None):
    """Return {offset: (subfolder, base name, label, note)} for every bank."""
    prof = PROFILES.get(fname.upper())
    out = {}
    if prof and prof['kind'] == 'voice':
        att = voice_attribution(disc) if disc else {}
        if not att:
            print('  CR.B: disc data not found (CHR_DATA/CRDD.B, CH_BIN*), voices not sorted '
                  'by character; use --disc', file=sys.stderr)
        known = sorted(att)
        nslots = (len(d) + prof['slot'] - 1) // prof['slot']
        slot_to_voice = {cr_slot_of_voice(v): v for v in range(nslots)}
        for o in offsets:
            slot = o // prof['slot']
            if slot not in slot_to_voice:
                out[o] = ('unused', f'CR_slot{slot:04d}', f'slot {slot}', 'slot skipped by the game')
                continue
            v = slot_to_voice[slot]
            a = att.get(v)
            if a:
                who, kind, _, sub, suffix = a[0]
                note = '; '.join(f'{w} {k}: {det}' if w != who or k != kind else det for w, k, det, _, _ in a)
                out[o] = (f'{who}/{sub}', f'CR_{v:04d}{suffix}', f'voice {v}: {who} {kind}', note)
            elif att:
                prev = next((att[k][0][0] for k in reversed(known) if k < v), None)
                nxt = next((att[k][0][0] for k in known if k > v), None)
                guess = f'likely {prev} (between two {prev} voices)' if prev and prev == nxt else ''
                out[o] = ('_unattributed', f'CR_{v:04d}', f'voice {v}: not referenced', guess)
            else:
                out[o] = ('', f'CR_{v:04d}', f'voice {v}', '')
    elif prof and prof['kind'] == 'scene':
        owners = chse_bank_owners()
        for o in offsets:
            n = o // prof['slot'] + 1
            who = owners.get(n)
            if not who:
                folder, label = f'UNUSED_{n:02d}', f'scene {n} (never played)'
            elif n >= 54:  # 'S3-stage6' -> 'S3_STG6'
                tag = who[0].replace('-stage', '_STG')
                folder, label = f'STORY_{n:02d}_{tag}', f'story scene {n}: {tag}'
            elif n >= 51:
                tag = f'JR-x{n - 50}'
                folder, label = f'SPECIAL_{n:02d}_{tag}', f'special move {n}: {tag}'
            else:
                tag = '-'.join(who)
                folder, label = f'SPECIAL_{n:02d}_{tag}', f'special move {n}: {tag}'
            out[o] = (folder, f'CHSE_{n:02d}', label, '')
    elif prof and prof['kind'] == 'character':
        owners = atb_bank_owners()
        for o in offsets:
            b = o // prof['slot']
            who = owners.get(b)
            tag = '-'.join(who) if who else 'unassigned'
            out[o] = (f'ATB_{b:02d}_{tag}', f'ATB_{b:02d}', f'bank {b}: {tag}', '')
    else:
        stem = os.path.splitext(fname)[0].upper()
        for i, o in enumerate(offsets):
            sub = f'bank_{i:02d}' if len(offsets) > 1 else ''
            out[o] = (sub, f'{stem}_{i:02d}' if len(offsets) > 1 else stem, f'bank {i}', '')
    return out


def merge_shared_special_names(d, offs, names):
    """CHSE.B stores some special moves twice (e.g. the Kamehameha of GKN, S3,
    GHC and GSM). Only the first copy is extracted, so its folder gets the
    names of every character whose special move uses the same sounds."""
    owners = chse_bank_owners()
    groups = {}
    for o in offs:
        L = bank_layout(d, o)
        h = hashlib.md5(d[o:o + L['vb_off'] + sum(L['sizes'])]).hexdigest()
        groups.setdefault(h, []).append(o)
    for group in groups.values():
        first = group[0]
        folder, base, label, note = names[first]
        if len(group) < 2 or not folder.startswith('SPECIAL_'):
            continue
        n = first // PROFILES['CHSE.B']['slot'] + 1
        who = list(owners.get(n, []))
        for o in group[1:]:
            m = o // PROFILES['CHSE.B']['slot'] + 1
            if m <= 50:  # special moves; 51-53 are JR variants, 54+ story scenes
                who += [c for c in owners.get(m, []) if c not in who]
        tag = '-'.join(who)
        names[first] = (f'SPECIAL_{n:02d}_{tag}', base, f'special move {n}: {tag}', note)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def extract_one(path, outdir, rate, disc=None):
    d = open(path, 'rb').read()
    fname = os.path.basename(path)
    os.makedirs(outdir, exist_ok=True)
    offs = find_banks(d)
    names = bank_naming(fname, offs, d, find_disc_root(path, disc))
    if PROFILES.get(fname.upper(), {}).get('kind') == 'scene':
        merge_shared_special_names(d, offs, names)
    seen, banks, rows, n = {}, [], [], 0
    for idx, o in enumerate(offs):
        # a bank may run over the following slots: long CR.B voices use 2-5
        # slots, and the game skips those slots when numbering voices
        L = bank_layout(d, o)
        end = offs[idx + 1] if idx + 1 < len(offs) else len(d)
        sub, base, label, note = names[o]
        h = hashlib.md5(d[o:o + L['vb_off'] + sum(L['sizes'])]).hexdigest()
        entry = {'index': idx, 'offset': o, 'slot': end - o, 'label': label,
                 'hdr_len': L['hdr_len'], 'vb_off': L['vb_off'], 'vags': []}
        if L['vb_off'] + sum(L['sizes']) > end - o:
            entry['skipped'] = 'truncated (incomplete file?)'
        elif h in seen:
            entry['duplicate_of'] = seen[h]
            banks[seen[h]].setdefault('also_used_by', []).append(label)
            rows.append([label, '', f'duplicate of {banks[seen[h]]["label"]}', '', '', f'0x{o:X}'])
        else:
            pos = o + L['vb_off']
            samples = []
            for k in range(1, L['vs'] + 1):
                samples.append(d[pos:pos + L['sizes'][k]])
                pos += L['sizes'][k]
            if not all(looks_like_adpcm(s) for s in samples if s):
                entry['skipped'] = 'sample data not where expected (unsupported layout)'
            else:
                seen[h] = idx
                entry['folder'] = sub
                os.makedirs(os.path.join(outdir, sub), exist_ok=True)
                for k, data in enumerate(samples, 1):
                    fn = f'{base}.vag' if L['vs'] == 1 else f'{base}_{k:02d}.vag'
                    rel = os.path.join(sub, fn) if sub else fn
                    with open(os.path.join(outdir, rel), 'wb') as f:
                        f.write(vag_header(len(data), rate, os.path.splitext(fn)[0]))
                        f.write(data)
                    secs = round(len(data) / 16 * 28 / rate, 2)
                    t = L['tones'].get(k, {})
                    entry['vags'].append({'n': k, 'file': rel.replace(os.sep, '/'), 'size': len(data),
                                          'md5': hashlib.md5(data).hexdigest(), 'seconds': secs, **t})
                    rows.append([label, rel.replace(os.sep, '/'), note, secs, t.get('center', ''), f'0x{o:X}'])
                    n += 1
        if 'skipped' in entry:
            print(f'  {fname}: bank at 0x{o:X} skipped: {entry["skipped"]}', file=sys.stderr)
        banks.append(entry)
    man = {'source': fname, 'source_size': len(d), 'source_md5': hashlib.md5(d).hexdigest(),
           'rate': rate, 'banks': banks}
    with open(os.path.join(outdir, 'manifest.json'), 'w') as f:
        json.dump(man, f, indent=1)
    with open(os.path.join(outdir, 'index.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['bank', 'file', 'note', 'seconds', 'center_note', 'offset'])
        w.writerows(rows)
    dup = sum('duplicate_of' in b for b in banks)
    skip = sum('skipped' in b for b in banks)
    print(f'{path}: {len(banks)} banks ({dup} duplicates, {skip} skipped), {n} .vag -> {outdir}')


def cmd_extract(a):
    *files, out = a.paths
    if not files:
        sys.exit('usage: extract INPUT.B [INPUT.B ...] OUTDIR')
    for f in files:
        extract_one(f, os.path.join(out, os.path.splitext(os.path.basename(f))[0]), a.rate, a.disc)


def cmd_rebuild(a):
    man = json.load(open(os.path.join(a.folder, 'manifest.json')))
    d = bytearray(open(a.original, 'rb').read())
    if hashlib.md5(d).hexdigest() != man['source_md5']:
        print('warning: ORIGINAL.B is not the file that was extracted', file=sys.stderr)
    by_idx = {b['index']: b for b in man['banks']}
    cache, changed, errors = {}, 0, 0

    def load(v):
        if v['file'] not in cache:
            cache[v['file']] = read_vag(os.path.join(a.folder, v['file']), v.get('md5'))
        return cache[v['file']]

    for b in man['banks']:
        if 'skipped' in b:
            continue
        src = by_idx[b.get('duplicate_of', b['index'])]
        loaded = [load(v) for v in src['vags']]
        if all(x is None for x in loaded):
            continue
        o = b['offset']
        L = bank_layout(d, o)
        old = [bytes(d[o + L['vb_off'] + sum(L['sizes'][1:k]):][:L['sizes'][k]])
               for k in range(1, L['vs'] + 1)]
        new = [old[i] if x is None else x for i, x in enumerate(loaded)]
        need = L['vb_off'] + sum(map(len, new))
        if need > b['slot']:
            print(f'ERROR {b["label"]} (0x{o:X}): needs {need} bytes, slot is {b["slot"]} '
                  f'({need - b["slot"]} too many)', file=sys.stderr)
            errors += 1
            continue
        print(f'  {b["label"]}: ' + ', '.join(v['file'] for v, x in zip(src['vags'], loaded) if x is not None))
        for k, data in enumerate(new, 1):
            struct.pack_into('<H', d, L['size_off'] + 2 * k, len(data) // 8)
        struct.pack_into('<I', d, o + 0xC, L['hdr_len'] + sum(map(len, new)))
        blob = b''.join(new)
        d[o + L['vb_off']:o + b['slot']] = blob + b'\0' * (b['slot'] - L['vb_off'] - len(blob))
        changed += 1
    if errors:
        sys.exit(f'{errors} bank(s) too large, nothing written')
    open(a.output, 'wb').write(d)
    same = 'same size' if len(d) == man['source_size'] else 'SIZE CHANGED'
    print(f'{changed} bank(s) updated -> {a.output} ({len(d)} bytes, {same})')


def cmd_info(a):
    d = open(a.input, 'rb').read()
    offs = find_banks(d)
    names = bank_naming(os.path.basename(a.input), offs, d, find_disc_root(a.input))
    for idx, o in enumerate(offs):
        L = bank_layout(d, o)
        end = offs[idx + 1] if idx + 1 < len(offs) else len(d)
        used = L['vb_off'] + sum(L['sizes'])
        print(f'{idx:4d}  0x{o:08X}  samples={L["vs"]:2d}  used={used:6d}  slot={end - o:6d}  '
              f'free={end - o - used:6d}  {names[o][2]}')


# --- scan ------------------------------------------------------------------

SIGS = {b'pBAV': 'VAB (sound bank)', b'VAGp': 'VAG (single sound)', b'pQES': 'SEQ (sequenced music)',
        b'SEQp': 'SEQ (sequenced music)', b'pBDS': 'SDS', b'VAGi': 'interleaved VAG'}


def vab_ranges(d):
    out = []
    for o in find_banks(d):
        try:
            L = bank_layout(d, o)
            out.append((o, o + L['vb_off'] + sum(L['sizes'])))
        except struct.error:
            pass
    return out


def scan_raw(d, align, min_blocks, skip):
    found = []
    for phase in range(0, 16, align):
        p, start, n = phase, None, 0
        while p + 16 <= len(d):
            inside = next((e for s, e in skip if s <= p < e), None)
            if inside:
                p = inside + ((phase - inside) % 16)
                start = None
                continue
            if block_ok(d, p):
                if start is None:
                    start, n = p, 0
                n += 1
                if d[p + 1] in (1, 3, 7):
                    end = p + 16
                    while end + 16 <= len(d) and d[end + 1] == 7:
                        end += 16
                    s = start  # trim inactive lead-in, keep one zero block
                    while s < p and d[s] == 0 and d[s + 1] not in (4, 6):
                        s += 16
                    if s > start:
                        s -= 16
                        if any(d[s:s + 16]):
                            s += 16
                    nb = (p + 16 - s) // 16
                    act = sum(1 for q in range(s, p + 16, 16) if d[q])
                    if nb >= min_blocks and act > nb * 0.5 and len(set(d[s + 2:end:16])) > 8:
                        found.append((s, end))
                    start = None
                    p = end
                    continue
            else:
                start = None
            p += 16
    found.sort()
    merged = []
    for s, e in found:
        if not merged or s >= merged[-1][1]:
            merged.append((s, e))
    return merged


def cmd_scan(a):
    if a.extract:
        os.makedirs(a.extract, exist_ok=True)
    hits = 0
    for root, _, files in sorted(os.walk(a.folder)):
        for fn in sorted(files):
            if fn.endswith(('.py', '.md', '.json', '.csv', '.vag')):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, a.folder)
            d = open(path, 'rb').read()
            lines = [f'    {d.count(s):5d} x {s.decode()}  {desc}' for s, desc in SIGS.items() if d.count(s)]
            raw = scan_raw(d, a.align, a.min, vab_ranges(d))
            if raw:
                secs = sum((e - s) / 16 * 28 for s, e in raw) / a.rate
                lines.append(f'    {len(raw):5d} x raw headerless ADPCM (~{secs:.1f} s total)')
                for s, e in raw[:8]:
                    lines.append(f'            0x{s:08X}-0x{e:08X}  {(e - s) / 16 * 28 / a.rate:5.2f} s'
                                 + ('' if s % 16 == 0 else '  (unaligned: likely false positive)'))
                if len(raw) > 8:
                    lines.append(f'            ... {len(raw) - 8} more')
                if a.extract:
                    tag = rel.replace(os.sep, '_').replace('.', '_')
                    for s, e in raw:
                        body = d[s:e]
                        with open(os.path.join(a.extract, f'{tag}_{s:08X}.vag'), 'wb') as f:
                            f.write(vag_header(len(body), a.rate, f'{s:08X}') + body)
            if lines:
                hits += 1
                print(f'{rel}  ({len(d)} bytes)')
                print('\n'.join(lines))
    print(f'\n{hits} file(s) containing audio.')
    print('Not covered: compressed audio, XA audio interleaved in .STR files (use jPSXdec).')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    e = s.add_parser('extract', help='extract .vag files')
    e.add_argument('paths', nargs='+', metavar='INPUT.B... OUTDIR')
    e.add_argument('--rate', type=int, default=DEFAULT_RATE)
    e.add_argument('--disc', metavar='DIR', help='disc root (default: parent of the SOUND folder); '
                   'used to sort CR.B voices by character')
    r = s.add_parser('rebuild', help='reinsert .vag files into a .B')
    r.add_argument('folder'); r.add_argument('original'); r.add_argument('output')
    i = s.add_parser('info', help='list banks and free space')
    i.add_argument('input')
    c = s.add_parser('scan', help='search a folder for PS1 audio')
    c.add_argument('folder')
    c.add_argument('--extract', metavar='DIR')
    c.add_argument('--min', type=int, default=48, help='minimum blocks (48 = ~0.12 s at 11025 Hz)')
    c.add_argument('--align', type=int, default=16, choices=[1, 2, 4, 8, 16])
    c.add_argument('--rate', type=int, default=DEFAULT_RATE)
    a = p.parse_args()
    {'extract': cmd_extract, 'rebuild': cmd_rebuild, 'info': cmd_info, 'scan': cmd_scan}[a.cmd](a)


if __name__ == '__main__':
    main()
