# dd_extract — High School DxD (3DS) asset extractor

Asset extractor for **High School DxD** on Nintendo 3DS (Kadokawa Games, 2013, Japan only).

It only handles the formats that **no existing tool can open**. Everything else in the RomFS can already be read with the usual tools (see below).

## Usage

You need an already extracted RomFS (the `ExtractedRomFS` folder) and Python 3. Nothing else from the cartridge is needed: no ExeFS, no `code.bin`.

For PNG output:

```
pip install numpy pillow
```

Then:

```
python dd_extract.py ExtractedRomFS
```

Everything is written to an `out/` folder next to `ExtractedRomFS` (or to the folder given as a second argument: `python dd_extract.py ExtractedRomFS my_folder`). `out/` mirrors the RomFS folder layout. The RomFS itself is never modified, and running the script again simply overwrites `out/`.

## What gets extracted

| Source (RomFS) | Output |
|---|---|
| `data/event.enc` | `out/data/event/…`: 795 `.evt` scripts at their original paths (`main/M0000.evt`, `battle/B0000.evt`…), names taken from `data/event/eventFileListTbl.dat`, plus a `.txt` with the dialogue of each script (speakers, lines, choices, labels) |
| `data/npc/CTR/bustup/BU_*.enc` | `out/data/npc/CTR/bustup/BU_*/`: `_00.bin` (layout) + textures as `.ctx` and `.png` |
| `data/table.enc`, `data/RTM.enc` | `out/data/table/`, `out/data/RTM/`: `.bin` data tables |
| `data/texture/CTR/title.enc`, `efc00.enc` | `out/data/texture/CTR/<archive>/`: textures as `.ctx` and `.png` |
| `data/texture/**/*.ctx` | `.png` at the same path under `out/` |
| `se/se.acb` | `out/se/`: 189 `.bcwav` files named after their cues + `list.txt` (sample rate, duration, loop points) |
| `text/*.bin` | `out/text/`: UTF-8 `.txt`, one string per line |
| `data/event/flag.dat`, `tutorial.dat` | `out/data/event/flag.txt`, `tutorial.txt` (see [Notes](#notes)) |

## Already readable with other tools

| Files | Tool |
|---|---|
| `sound/bgm.acb` + `bgm.awb` | [vgmstream](https://github.com/vgmstream/vgmstream) |
| `movie/*.moflex` (Mobiclip) | [FFmpeg](https://ffmpeg.org/) |
| `.bcwav` files produced by this script | vgmstream |
| `*.bcfnt`, `*.shbin` | standard 3DS tools |

## Repository layout

```
dd_extract.py        entry point: walks the RomFS and writes the out/ folder
dd_formats/
  enc.py             .enc archives
  lzo.py             LZO1X decompression
  ctx.py             .ctx textures -> RGBA image
  acb.py             CRI ACB/@UTF tables, CWAV waveforms in an embedded AWB
  text.py            text/*.bin string tables
  event_data.py      data/event/flag.dat and tutorial.dat
  evt.py             .evt scripts: command parser and dialogue export
```

Each module in `dd_formats/` can also be imported on its own.

## Formats

### `.enc` archives
Despite the extension, these are neither encrypted nor signed. Little endian:

```
u32 entry count
then, for each entry:
  u32 stored size   (bit 31 set: LZO1X-compressed)
  u32 final size
  u32 offset from the start of the file
```

Compression is standard **LZO1X** (found in `code.bin`, function at `0x1bdcf4`). An entry of size 0 is empty.

The entries of `event.enc` match, in order, the names in `data/event/eventFileListTbl.dat` (64-byte records, space-padded ASCII).

### `.ctx` textures
0x40-byte header followed by PICA200 data:

```
0x00  "CTX 10\0\0"
0x08  u32 width, u32 height
0x10  u32 width, u32 height (copy)
0x18  u32 0x0DE1 (GL_TEXTURE_2D)
0x1C  u32 GL format  (0x675A = ETC1, 0x675B = ETC1A4, 0x6752 = RGBA)
0x20  u32 GL type    (0xFFFFFFFF for compressed formats)
0x24  u32 data size
0x40  data
```

Formats seen in the game: ETC1 and ETC1A4 for almost everything, RGBA8 and RGBA4 (`0x6752` with type `0x1401` / `0x8033`) for a few effect textures. The data uses the usual 3DS tiling: 8×8 tiles, 4×4 ETC blocks in Z-order, little-endian 64-bit blocks. In ETC1A4, 8 bytes of 4-bit alpha come before each color block. **Unlike most 3DS games, images are stored upright**, with no vertical flip.

### Bust-up portraits `BU_*.enc`
Each archive has 11 fixed slots:

| Entry | Contents |
|---|---|
| 00 | layout, 14 × u16: `?, ?, chest x, y, w, h, eyes x, y, w, h, mouth x, y, w, h` |
| 01 | base body (512×256), with a hole where the chest and face go |
| 02 | animated chest: 4 frames in a grid (empty if the character has none) |
| 03–10 | up to 8 expressions: 3 stacked eye frames (blink) + 3 mouth frames in the next column |

Character codes: `AKN` Akeno, `ASA` Asia, `ISI` Issei, `KNK` Koneko, `RAS` Rias, `YUT` Yuuto (Kiba), `S##` side characters and close-ups.

### `.evt` scripts
An 8-byte header, then a sequence of commands: `u32 opcode, u32 payload size, payload`. All 795 scripts parse with no bytes left over. Text is null-terminated Shift-JIS:

| Opcode | Meaning |
|---|---|
| `0x32` | speaker name |
| `0x34` | one line of dialogue |
| `0x36` | end of the message box |
| `0x26` | choice offered to the player |
| `0xEE` / `0xEF` | label / jump to a label |
| `0x71`, `0x56`, `0x59`… | load or show a portrait (`BU_*.enc`) |
| `0x7A`, `0x7C`… | load or show a background (`BG_*.ctx`) |
| `0x35` | play a sound effect (`u32` cue number from `se/se.h`) |
| `0x112` | play a movie (`AM_*.moflex`) |

A few `conversation/` and `training/` scripts (e.g. `C010000`, `T010000`) only contain development placeholders such as `"C010000.txt"開始` ("start of C010000.txt").

### `se/se.acb`
CRI Atom ACB (Atom Craft 1.30) with an embedded AWB (`AFS2`). Its waveforms use **EncodeType 9 = CWAV** (DSP-ADPCM, 32,728 Hz), which vgmstream does not support inside an ACB. The script writes them out unchanged as `.bcwav`, named through `CueNameTable → CueTable → SynthTable → WaveformTable`.

Prefixes: `ESE` ambience (all looping), `NSE` sound effects, `SSE` UI sounds. The `VRD_` sounds come from an outside sound library (4-digit numbering up to 1359) whose origin is unknown. Only 5 of the 80 are ever played (`VRD_NSE_0194`, `0252`, `1256`, `VRD_ESE_0064`, `0180`, all from event scripts); the code itself only plays `DD_` cues. An audio comparison with the 1,513 sounds of *Wizardry XTH* (PS2) found no match.

### `text/*.bin`
`u32` string count, then one 16-byte entry per string. The first `u32` of each entry is the absolute offset of a null-terminated Shift-JIS string.

### `data/event/flag.dat`
107 records of 74 bytes: flag name (17 bytes, ASCII) + comment (57 bytes, Shift-JIS). Same flags as `eve_flag.h`, with a description of each one (character events, *Dress Break* unlocked, result of each of the 58 story battles…).

### `data/event/tutorial.dat`
`u32` page count, `u32` offset of each page. A page is an index of `u16` line offsets followed by null-terminated Shift-JIS lines. `@3r`…`@0r` and `@4r`…`@0r` are color codes.

### `data/table.enc` and `data/RTM.enc`
Not converted (game data tables), but identified:

| Entry | Contents |
|---|---|
| `table_00` | 59 records × 280 bytes: battles (opponent name, background, portraits used) |
| `table_01` | the hero's default name (兵藤 一誠) and starting values |
| `table_02` | Evil Piece types (unset, Rook, Knight, Queen) with stat multipliers |
| `table_03` | 315 records × 44 bytes of numeric data |
| `table_04` | 117 records × 36 bytes: CG gallery (top/bottom screen `EG_*.ctx` pair + ID) |
| `table_05` | 71 records × 16 bytes: movie list (`AM_*.moflex`) |
| `table_06` | 77 records × 72 bytes: character names |
| `table_07` | 36 records × 72 bytes: heroine names with IDs |
| `RTM_01` | 856 rectangles (x, y, w, h) on the 320×240 bottom screen, probably touch areas |
| `RTM_00`, `RTM_02`, `RTM_04` | 32-entry index tables (first entry / count per screen) for `RTM_01` and `RTM_03` |
| `RTM_03` | 806 records × 8 bytes of numeric data |

## Notes

The game is built on the engine of an older Wizardry-style dungeon crawler, and leftovers of it remain in the RomFS:

- `data/event/tutorial.dat` is **the full tutorial of *Wizardry XTH 2*** (ウィザードリィ エクス2), not of DxD: 56 pages about creating students (学徒), forming parties, the academy (学府), alchemy, spells, and exploring "roads" such as the Novice Road (ノービスロード) and Hoto Road (ホトロード). It is most likely unused.
- The first 9 flags of `flag.dat` come from that game (`PROLOGUE` = "entrance ceremony event finished", `OPNING` = "party formed after the entrance ceremony"), followed by `DD_TEST` ("DxD test flag added") and then the DxD flags.
- `code.bin` still references PSP images from that engine (`emotion_01.gim`…`emotion_12.gim`).
- `data/startDebugInfo.txt` still holds dungeon-crawler debug switches: traps off, infinite spells, permanent light spell (`MILWAN`), all dungeons open, no random encounters, free movement in dungeons.

## Disclaimer

No game files are included in this repository. Use your own copy of the game.
