# idainaru-densetsu-ps1-sound

Sound extraction and reinsertion for **Idainaru Dragon Ball Densetsu**
(偉大なるドラゴンボール伝説, PlayStation, Japan, SLPS-00355).

- Extracts every voice clip and sound effect as standard `.vag` files, with the
  original ADPCM data and no re-encoding.
- Sorts the output with tables recovered from the game: every voice of `CR.B`
  is filed under the character who says it (battle lines, special-move lines,
  story-scene lines), and the `ATB.B` / `CHSE.B` banks are named after the
  characters and special moves that use them.
- Rebuilds the `.B` archives from edited or replaced `.vag` files, so you can
  put modified sounds back into the game.

Single Python 3 file, no dependencies. No game data is included: you need your
own copy of the disc.

## Usage

```bash
# extract (one subfolder per archive); run it on a copy of the full disc file tree:
# CR.B voices are sorted using CHR_DATA/CRDD.B and CH_BIN*/ (found automatically
# next to SOUND/, or pass --disc DIR)
python3 densetsu_sound.py extract SOUND/CR.B SOUND/CHSE.B SOUND/ATB.B SOUND/ABTL.B SOUND/CURSOR.B out

# replace a sound: overwrite e.g. out/CR/GKN/battle/STG1/CR_0005_GHN.vag with your own VAG (mono, 11025 Hz)
python3 densetsu_sound.py rebuild out/CR SOUND/CR.B CR_new.B

# free space per bank (a replacement may be longer than the original if it fits)
python3 densetsu_sound.py info SOUND/CR.B

# look for audio anywhere on the disc
python3 densetsu_sound.py scan path/to/disc_files
```

Each extracted folder contains:

- `manifest.json`, which `rebuild` needs. Do not edit it.
- `index.csv`, a list of the files with their bank, duration and offset. For
  `CR`, it also gives every place a voice is used: stage, partner character and
  situation for battle lines, scene number for special-move and story lines.

The rebuilt file keeps the original size, so it can be swapped into the ISO with
mkpsxiso, CDmage or a similar tool. Banks you did not touch stay byte-identical.

To encode WAV files to VAG, use a tool such as psxavenc or MFAudio. To listen to
`.vag` files, use vgmstream or foobar2000 with the vgmstream plugin.

## Output layout

```
out/
  CR/       GKN/battle/STG1/CR_0005_GHN.vag   battle line: speaker / stage / voice ID + partner
            GKN/special/CR_1482.vag           line said during a special move
            VT/story/CR_1489.vag              line said during a story scene
            GKN/unreferenced/CR_0286.vag      voice no game data refers to (identified by ear)
            KAIO/battle/ …                    support characters (Kaio-sama, Mr. Satan, Videl…)
            GKN/ending/CR_1493.vag            the one voice played by the ending (Goku)
  ATB/      ATB_00_GKN-GKS-S3/ …              battle SFX, one bank per character group
  CHSE/     SPECIAL_01_GKN-GKS-S3-GHC-GSM/ …  sound effects of each special move, named
                                              after every character who uses them
  ABTL/ CURSOR/                               common battle SFX, menu sounds
```

`BGM.B` (music: SEQ + instrument samples) uses a different layout and is not
supported yet.

## File formats

All `SOUND/*.B` files are sequences of Sony **VAB** banks (`pBAV`), placed in
fixed-size slots:

| File | Slot size | Content |
|---|---|---|
| `CR.B` | 0x11000 (34 sectors) | 1654 slots, 1643 banks with 1 sample each: voices (long ones span several slots) |
| `CHSE.B` | 0x1F000 (62 sectors) | 63 banks with 3 to 5 sound effects each, many duplicates |
| `ATB.B` | 0x6000 (12 sectors) | 29 battle SFX banks |
| `ABTL.B`, `CURSOR.B` | — | 1 bank each |

What differs from a standard VAB: the sample data (VB) does not follow the header
directly at `0xC20`. The header is zero-padded to the next sector boundary, so
the samples start at `0x1000`. Generic VAB extractors read from `0xC20` and
produce misaligned samples.

Samples are mono SPU-ADPCM at **11025 Hz**. Every tone has center note 60, so
the game plays them at their native rate.

## Findings from GAME.EXE

The executables carry no per-sound names. The game addresses sounds only by
number. The same code and tables appear in `GAME.EXE`, `VS.EXE`, `SP.EXE`,
`TITLE.EXE`, `SELECT.EXE` and `ENDING.EXE` (addresses below are for `GAME.EXE`).

### CR.B: voice ID to slot (`0x800631D4`)

```
sector = CR.B start + slot * 34
slot   = id + (id>=278) + (id>=494) + (id>=1161) + 4*(id>=1162)
            + (id>=1163) + 2*(id>=1284) + (id>=1495)
```

Voice IDs go from 0 to 1642. The 11 skipped slots (278, 495, 1163, 1165-1168,
1170, 1292-1293, 1505) hold the end of voices longer than 34 sectors: the voices
in slots 494, 1162, 1164, 1169, 1291 and 1504 run over the next 1 to 4 slots.
A replacement can use all the space up to the next bank (see `info`).

Voices are played by direct ID (`0x800655C8`). The IDs come from three places,
which `extract` reads to sort the voices (see "Where voice IDs come from" below).

The executable also contains an unused table that picks a random voice by
"group and type" (`0x80091F6C` / `0x80091F98`). It is never called.

### ATB.B: character to SFX bank (`0x800922C4`)

There is one `u16` sector offset per character ID. `bank = sector / 12`.
Character IDs are 1-based positions in the archive name table at `0x8008897C`
(38 entries of `char[18]`, `\AT1\GKN.B;1` and so on).

| Bank | Characters | Bank | Characters |
|---|---|---|---|
| 0 | GKN, GKS, S3 | 15 | RC |
| 1 | GHN, GHC | 16 | GD |
| 2 | GSM, SS | 17 | FZ |
| 3 | GT | 18 | SIX |
| 4 | VG, VGS, VGI | 19 | SVN |
| 5 | TRF, TRA | 20 | ETN |
| 6 | TRC | 21 | NIN |
| 7 | GX | 22 | TWN |
| 8 | VT | 23 | CL |
| 9 | PC | 24 | JR |
| 10 | KL | 25 | DB |
| 11 | NP | 26 | BU |
| 12 | GW | 27 | SB |
| 13 | GES | 28 | FB |
| 14 | BT | | |

Character codes are the game's own archive names (Japanese names, since the
game was only released in Japan):

| Code | Character | Code | Character |
|---|---|---|---|
| GKN, GKS, S3 | Son Goku (base, Super Saiyan, Super Saiyan 3) | GD | Guldo |
| GHN, GHC | Son Gohan (teen, kid) | FZ | Freeza |
| GSM, SS | Son Gohan (Great Saiyaman, Super Saiyan) | SIX, SVN, ETN, NIN, TWN | Jinzouningen 16, 17, 18, 19, 20 |
| GT | Son Goten | CL | Cell |
| GX | Gotenks | JR | Cell Junior |
| VG, VGS, VGI | Vegeta (base, Super Saiyan, Majin) | DB | Dabura |
| TRF, TRA | Mirai Trunks (future, adult) | FB | Majin Buu (Zen, fat) |
| TRC | Trunks (kid) | SB | Majin Buu (Aku, Super) |
| VT | Vegetto | BU | Majin Buu (Junsui, Kid) |
| PC | Piccolo | GW | Ginyu |
| KL | Kuririn | GES | Jheese |
| NP | Nappa | BT, RC | Butta (Burter), Recoome |

### CHSE.B: special moves and story scenes (`0x800356F0`, `0x80064D70`)

```
sector = CHSE.B start + (n - 1) * 62     with 1 <= n <= 63
```

These are the scenes where gameplay freezes. The game picks scene `n` from the
character's ID, then loads CHSE bank `n` (its sound effects) and
`CH_BIN*/CH_nn.BIN` (its script) **with the same number**. Scenes 1-53 are
special moves (checked by listening: 1 Kamehameha, 2 Genki-dama, 18 Big Bang
Attack, 43 a Frieza attack), 54-63 are story scenes.

| Banks | Table in GAME.EXE | Meaning |
|---|---|---|
| 1-50 | `0x800877C0`, `u8[3]` per character | special moves, 1 to 3 per character, played in rotation |
| 51-53 | hard-coded, character `JR` | variants depending on how many Cell Jr are in the team |
| 54-63 | `0x80087838`, `u8 bank, u8 stage` per character (stage 0-based: 1 = STG2) | story scene, played once on one stage |

The script file for each scene comes from the path table at `0x800870AC`
(`char[27]` x 64): scenes 1-50 load `CH_nn.BIN`, 51-53 load `CH_32_1..3.BIN`, and
54-63 load `CH_BIN3/IN_01..IN_10.BIN`. Scenes 0, 8 and 40 load `CH_NO.BIN`, which
matches the missing `CH_08.BIN` and `CH_40.BIN` on the disc.
18 banks are byte-identical copies, so they are extracted once (`index.csv`
lists them): 3, 4 and 6 (the Kamehameha of S3, GHC and GSM) are copies of 1, so
the folder is `SPECIAL_01_GKN-GKS-S3-GHC-GSM`; 51-53 are copies of 32 (Cell Jr),
the 10 story scenes 54-63 copies of 2, and the unused 8 and 40 copies of 1.

### Where voice IDs come from

**1. Battle dialogue: `CHR_DATA/CRDD.B` (voices 0-1481).** This file holds one
32 KB block (16 sectors) per stage. The stage number at `0x1F80012C` is the
same one that loads `STG/STGnMD.B` and `STGnTX.B` (`0x80067A64` -> `0x80041640`),
so block `i` belongs to `STG(i+1)`; the output folders are named `STG1`-`STG8`.
The block is loaded at `0x801CA000` (`0x8005EAAC`). The first word of each block points to
a table of `(portrait ID, pointer)` pairs, one list per speaker on that stage.
Each list has 11 rows (battle situations) of 16 `u32` entries:

```
bits  0-6   partner character ID (0x40 = any); bit 7 = already played
bits  8-23  voice ID (CR.B)
bits 24-31  line index
```

An entry plays only if the partner character is present (`0x8005D86C`). Rows 0-4
are generic lines (partner "any", filed as `_ANY`); rows 5-10 have one line per
partner. A main character therefore has 20 to 70 lines per stage.

The list owner is **not** a character ID from the archive table. It is an index
into the 44-entry portrait list (`CHR_DATA/OV_CHR_A.B`, loaded by `0x8005EB38`).
The table at `0x80091F6C` maps each portrait to a voice group, i.e. a speaker,
and the table at `0x80091F98` gives each group's voice IDs per stage. The code
that reads these two tables is never called, but the data matches `CRDD.B`
exactly. For example, portraits 1, 6, 14 and 34 are all group 1 (voices 0-295).

Fighters are named after the one character never listed as their partner
(nobody talks to themselves), then checked by listening. Support characters have
no name anywhere in the game data (its text is stored as graphics); they were
identified by listening. Note that Nappa has no battle lines: group 5 is
Kami-sama, who never addresses Nappa.

| Group | Voices | Speaker | Group | Voices | Speaker |
|---|---|---|---|---|---|
| 1 | 0-295 | GKN (Son Goku, all forms) | 10 | 1274-1291 | MR_SATAN |
| 2 | 296-515 | GHN (Son Gohan, all forms) | 11 | 1292-1297 | ANNOUNCER (Cell Game commentator) |
| 3 | 516-724 | PC | 12 | 1298-1332 | GT |
| 4 | 725-907 | KL | 13 | 1333-1375 | TRC |
| 5 | 908-918 | KAMI | 14 | 1376-1407 | GX |
| 6 | 919-946 | KAIO (Kaio-sama) | 15 | 1408-1417 | VIDEL |
| 7 | 947-1182 | VG (Vegeta, all forms) | 16 | 1418-1450, 1475-1481 | KAIOSHIN |
| 8 | 1183-1194 | TENSHINHAN | 17 | 1451-1460 | KIBITO |
| 9 | 1195-1273 | TRF | 18 | 1461-1474 | ROU_KAIOSHIN |

**2. Special-move and story scripts: `CH_BIN*/*.BIN` (voices 1482-1642).** Each script is a list of
16-bit commands: the low byte is the opcode (51-entry table at `0x80087950`).

- Opcode `0x2F` (`0x8003EED8`) plays the voice whose ID is in the next word
  (`& 0x7FFF`).
- Opcode `0x32` (`0x8003F058`) plays the current character's own special-move line
  from the table at `0x800921D8` (3 `u16` per character: two alternating lines
  and one variant). Bit `0x4000` means the line continues with voice `ID + 1`.

The speaker of an opcode `0x2F` voice is not stored; the tool assumes it is the
scene's character unless the per-character table says otherwise. For example,
`IN_08.BIN` (Guldo's story scene) plays the lines of all five Ginyu Force
members, and voice 1642 is the whole group speaking (filed under `GINYU_FORCE`).

**3. Ending:** `ENDING.EXE` plays voice 1493 only (`0x800117E0`), said by Goku.

23 voices are referenced by none of these, nor by any constant in the
executables. They were identified by listening and are filed under
`CR/<speaker>/unreferenced/`; 1639-1641 are Ginyu Force group lines (3, 4 and 5
members) and go to `CR/GINYU_FORCE/`. They may be played by code not traced yet,
or be unused.

File names start with the source archive in upper case (`CR_`, `CHSE_`, `ATB_`,
`ABTL_`, `CURSOR_`), followed by the voice ID or bank and sample number.

## Other audio on the disc

- **CD audio tracks.** The disc image has 20 tracks. Track 1 is the data; tracks
  2-20 are standard CD audio (Red Book), so they are not files and tools such
  as jPSXdec do not list them. Tracks 11-18 (0:55 each) are the narrator
  between the 8 stages; the others are music and jingles. Any CD audio player
  or ripper reads them from the `.cue` (foobar2000, for example).
- **`SOUND/BGM.B`**: sequenced music (SEQ) and its instrument samples, stored in
  a different layout. Not supported yet.
- **`MOVIE/*.STR`**: the opening and logo videos, with their own audio; use
  jPSXdec on the `.bin/.cue` image.
- The `scan` command found no other audio: the character archives (`AT1/`,
  `AT2/`) and the other folders contain no samples.

## Status and limitations

- Extraction and sorting were checked on the full disc; voices and special
  moves were checked by listening.
- `rebuild` produces a consistent, same-size file (an unmodified rebuild is
  byte-identical), but **it has not been tested in the game yet**. Keep
  replacements no longer than the original and test in an emulator first.
- The meaning of the 11 battle situations (`situation` in `index.csv`) is not
  decoded.
- The speaker of story-scene voices is assumed to be the scene's character
  (marked "speaker assumed" in `index.csv`); corrections go in
  `SCENE_SPEAKER_OVERRIDES` in the script.
