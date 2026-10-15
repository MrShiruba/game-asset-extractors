# Kanokon Esuii (PS2) Extractor

Extraction tool for **Kanokon Esuii** (かのこん　えすいー) on PlayStation 2 (SLPM-55041).

It unpacks the game's proprietary `.DAT` archives and converts their contents into usable files: images to PNG, scripts to readable Japanese text, the game font to a PNG sheet, and the sound bank to WAV.

The `.AFS` archives (voices, BGM, sound effects) and the `.PSS` movies use standard formats that existing tools already handle, so this tool does not cover them.

## Features

| Archive | Content | Output |
|---|---|---|
| `BG.DAT` | Backgrounds, CGs, logos | PNG |
| `BG2.DAT` | Gallery thumbnails | PNG |
| `CHARA.DAT`, `CHARA2.DAT` | Character sprites | PNG (with transparency) |
| `SYSTEM.DAT` | UI screens, font, voice length table | PNG, font sheet PNG, CSV |
| `SCRIPT.DAT` | Game scripts (SC3) | `.sc3` + `.txt` (decoded Japanese text) |
| `SOUND.DAT` | Sony sound bank | `.sq` / `.hd` / `.bd` + one WAV per sample |

## Requirements

- Python 3.8+
- [Pillow](https://pypi.org/project/Pillow/): `pip install pillow`

## Usage

First, copy the files from the game disc (or extract them from your ISO). The root of the disc looks like this:

```
BG.DAT  BG2.DAT  CHARA.DAT  CHARA2.DAT  SCRIPT.DAT  SOUND.DAT  SYSTEM.DAT
BGM.AFS  SE.AFS  VOICE.AFS  OP01.PSS  ED01.PSS  SLPM_550.41  MODULES/ ...
```

Put `kanokon_extract.py` and `charset.txt` in the same folder, then run:

```bash
# All .DAT files found in the folder that contains them (the disc root)
python3 kanokon_extract.py /path/to/disc_files extracted

# Or a single archive
python3 kanokon_extract.py /path/to/disc_files/CHARA.DAT extracted
```

- First argument: the folder containing the `.DAT` files (or a single `.DAT` file).
- Second argument: the output folder (default: `extracted`).

Options:

- `--jobs N`: number of worker processes (default: one per CPU core)

Files keep their index in the archive as their name (`00042.png`). The game stores no file names inside the `.DAT` archives.

### Output

```
extracted/
├── BG/        00000.png ...
├── BG2/       00000.png ...
├── CHARA/     00000.png ...
├── CHARA2/    00000.png ...
├── SCRIPT/    00000.sc3, 00000.txt ...
├── SOUND/     sound.sq, sound.hd, sound.bd, samples/sample_00_32000Hz.wav ...
└── SYSTEM/    00000.png ..., 00014_font.png, 00079_voice_lengths.csv
```

### Script text

Each `.txt` file has one line per string, separated by tabs:

```
0000	たゆら	「……で、まあ民家や畑があったから、どうやら\nここは無人島じゃあなさそうだ」
0001		ビーチで鉢合わせしたぼくらは、さっそくお互\nいの情報を交換し合っていた。
```

The columns are: string index, speaker (empty for narration), text. `\n` marks an in-game line break, and `[cN]` a colour change.

### Voice length table

If `VOICE.AFS` sits in the same folder as the `.DAT` files, `00079_voice_lengths.csv` also gets the file name and duration of each voice. Without it, the CSV only lists the sample counts.

## Format documentation

Everything below was reverse-engineered from the game executable (`SLPM_550.41`).

### DAT archives

- The header is a table of `uint32` pairs: `(offset, size)`.
  - `offset` is in 0x800-byte sectors, **relative to 0x8000**, because the first 32 KiB hold the table area.
  - `size` is in 0x400-byte (1 KiB) units.
- The table ends at the first `(0, 0)` pair after entry 0.
- The executable gives the archive IDs in this order: `bg`=0, `chara`=1, `system`=2, `script`=3, `sound`=4, `bg2`=5, `chara2`=6.

### CPS images

CPS is an image format inherited from KID's engine (Ever17 and others), modified by 5pb. for PS2.

```
0x00  char[4]  "CPS\0"
0x04  u32      packed size
0x08  u16      version (0x68)
0x0A  u16      0x0100
0x0C  u32      unpacked size (+8)
0x10  char[4]  "bmp\0"
0x14  u16      width
0x16  u16      height
0x18  u16      bpp (unreliable, see below)
0x1A  u16      flag
0x20  ...      obfuscated, then compressed data (from 0x28)
```

**Obfuscation.** This is KID's scheme, with three changes:

- It starts at 0x20.
- It covers only the first 4 KiB.
- An 8-word key table is added to the keystream.

The last dword of the file, minus `0x7534682`, gives `v_off`. The seed is `dword[v_off] + v_off + 0x3786425`. For each dword `i` from 0x20 onwards, except the one at `v_off`:

```
data[i] -= packed_size + seed + KEYTAB[k];   k = (k + 1) & 7
seed     = seed * 0x41C64E6D + 0x9B06
```

`KEYTAB` (written word by word in scattered places of the init code):

```
2623A189 146FD8D7 8E6F55FF 1F497BCD 1BB74F41 0EB731D1 5C031379 64350881
```

**Compression.** This is KID's RLE, unchanged (literals, single-byte runs, repeated blocks, 10-bit back-references). Decompression starts at 0x28, and the output size is `unpacked size - 8`.

**Pixel data.** The game sends the decompressed data to the GS (the PS2's graphics processor) as-is:

- **8 bpp**: a 256-entry RGBA palette (1024 bytes) in the PS2 **CSM1** order (entries 8–15 and 16–23 of each 32-entry block are swapped), followed by one byte per pixel.
- **32 bpp**: RGBA.
- In both cases alpha uses the PS2 range (`0x80` = opaque).

The header bpp field is wrong for some images (BG logos are direct colour but flagged as 8 bpp), so the tool infers the format from the unpacked size.

### SC3 scripts

The text format is the one of 5pb.'s SC3 engine.

- **Header**: `"SC3\0"`, string table offset, end of the string table, then the label table.
- **Strings** use these control codes:

| Code | Meaning |
|---|---|
| `01` … `02` | speaker name |
| `00` | line break |
| `03` | end of line |
| `04 xx` | colour |
| `FF` | end of string |
| `>= 0x80` | 2-byte glyph index: `((b0 & 0x7F) << 8) \| b1` |

- **Glyph indexes** point into the game font, not into any standard encoding. `charset.txt` maps glyph index → Unicode character.
- **Useful bytecode instructions:**

| Instruction | Meaning |
|---|---|
| `10 01 <layer> <n>` | display background `n` from BG.DAT (layers 1, 2) |
| `10 05 <layer> <n>` | display sprite `n` from CHARA.DAT (layers 0x10–0x80) |
| `01 10 <t> <voice> … <u16 string id> 01 11 00` | dialogue line; when `t = 3`, `<voice>` is the index in VOICE.AFS |

### Font

`SYSTEM.DAT` entry 14 holds the font: 2432 glyphs of 24×24 pixels at 4 bpp, with the high nibble as the left pixel and no header.

The order is:

1. ASCII, full-width alphanumerics and punctuation;
2. small kana and circled numbers;
3. hiragana and katakana in standard order, from glyph 0x15F;
4. kanji, in a game-specific order.

`charset.txt` was built by matching every glyph against rendered Japanese fonts (Noto Sans CJK, IPAGothic). The doubtful matches were then checked by eye. A few rare or near-identical glyphs (曰/日, 十/＋) may still be wrong: corrections are welcome.

### SOUND.DAT

This archive holds a standard Sony PS2 sound bank.

- Entry 0 begins with a small header: `u32 SQ size`, `u32 BD size`, `u32 HD size`, then padding up to 0x80.
- The **SQ** (sequence), **BD** (ADPCM samples) and **HD** (bank header) follow, in that order.
- The HD's `Vagi` table gives each sample's BD offset, **sample rate** (32000, 37800 or 44100 Hz in this bank) and loop flag. The tool uses it to write each sample at its correct rate.

[VGMTrans](https://github.com/vgmtrans/vgmtrans) lists Sony's PS2 sequence and bank format among its supported formats. It may be able to open `sound.sq` / `.hd` / `.bd` to export MIDI + SF2.

### Voice length table

`SYSTEM.DAT` entry 79 lists one `u32` per voice: the sample count of each ADX file in `VOICE.AFS`, in archive order. The last 5 entries of `VOICE.AFS` are actually sound effects and have no length in the table.

## Credits

- KID CPS obfuscation and RLE algorithm: based on [e17p](https://github.com/dsp2003/e17p) (Ever17 tools, GPL).
- MIPS disassembly with [Capstone](https://github.com/capstone-engine/capstone).

## Disclaimer

This project contains no game data. You need your own copy of the game. Kanokon Esuii and all related assets belong to their respective owners.
