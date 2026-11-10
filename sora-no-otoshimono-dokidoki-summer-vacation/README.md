# Sora no Otoshimono: DokiDoki Summer Vacation – .ptd extractor

An extractor for the `.ptd` (PETA) archives of **Sora no Otoshimono: DokiDoki Summer Vacation** (そらのおとしもの -ドキドキサマーバケーション-, **PSP**, `ULJM05639`).

Generic ADX rippers can pull the voice files out of `voice_adx.ptd`, but only as numbered blobs. This tool reads the archive's own (encrypted) file table, so every file comes out with its **original name and path**, in its **original format**.

It also unpacks the game's own container formats (animations with embedded textures, the system sound bank, fonts and scripts) into files that standard tools can open.

## Requirements

- **Python 3.6 or later**, no modules to install
- You need your own copy of the game: copy `PSP_GAME/USRDIR/res/` from the disc

## Usage

```
python3 ptd_extract.py [-h] [-o OUT] [-l] [--keep-case] ptd [ptd ...]
```

| Argument | Description |
|---|---|
| `ptd [ptd ...]` | One or more `.ptd` archives to extract (at least one is required) |
| `-o`, `--out OUT` | Output directory (default: `out`) |
| `-l`, `--list` | List the contents without extracting anything |
| `--keep-case` | Keep file names in UPPERCASE, as stored in the archive (default: lowercase) |

### Examples

Extract everything from the game:

```bash
python3 ptd_extract.py PSP_GAME/USRDIR/res/res.ptd PSP_GAME/USRDIR/res/voice_adx.ptd
```

Extract only the voices into a `voices/` directory:

```bash
python3 ptd_extract.py PSP_GAME/USRDIR/res/voice_adx.ptd -o voices
```

List the contents of an archive:

```bash
python3 ptd_extract.py -l PSP_GAME/USRDIR/res/res.ptd
```

### Output

Paths are rebuilt from the archive's directory table, for example:

```
out/res/sound/voice/vo000/sv000_000010.adx
out/res/commu/00_card/ca0000_m.gim
out/res/__pack__/common.ptd
```

With `--keep-case`, the same file would be `out/RES/SOUND/VOICE/VO000/SV000_000010.ADX`. The contents are identical; only the name changes. Lowercase is the default because that is how the game's executable refers to its files.

## What gets extracted

- **Everything.** There is no filter. Both `res.ptd` (~1,800 files) and `voice_adx.ptd` (~7,000 ADX voice clips) are fully supported.
- **Original formats.** Standard formats are never converted: ADX stays ADX, GIM stays GIM. Use your usual tools afterwards (e.g. vgmstream for ADX and VAG, GimConv or Noesis for GIM).
- **Nested archives.** `res.ptd` contains further PETA archives under `res/__pack__/`. They are written out as-is **and** their contents are extracted too, whether the nested archive is stored or YKLZ-compressed. Their files go to the paths stored in their own table, not under `__pack__/`: for example `__pack__/subscript.ptd` holds `res/script/sc/ending_out.sos`, which is written to `out/res/script/sc/ending_out.sos`.
- **Container compression is removed.** Most files in `res.ptd` are wrapped in the game's own LZSS compression (`YKLZ`). This is a storage layer, not a file format, so it is always undone. Without that step the files would be unreadable.

If a file fails to decompress, the tool prints a `!` warning and writes the raw data instead of stopping.

## Conversions

The formats that only this game uses are also unpacked automatically, **next to** the original file, which is always kept:

| File | Output | What it is |
|---|---|---|
| `.fab`, `.fsb` | `<name>_tex/*.gim` | 2D animations (`FANM`) and menu scenes (`FSCN`). The GIM textures stored inside are written out under their original names. |
| `.vgp` | `<name>_vag/<name>_NNN.vag` | Headerless sound bank (`res/1st/sysse.vgp`: 31 system sounds), split into standard `VAGp` files |
| `.tfp` | `<name>.png` + `<name>.txt` | Bitmap font: glyph atlas (64 glyphs per row) and an index → character table |
| `.sos` | `<name>.txt` | Compiled script: decrypted string table (dialogue, character names, voice and sprite paths), one `OFFSET<TAB>text` line per string, line breaks written as `\n` |

Notes:

- Texture names are read from the file's own name table. A name can be a relative path: `ending_a/ed_a.fsb` lists `..\bg.tm2`, an embedded copy of the ending background. Only the file name is kept (`ed_a_tex/bg.gim`), so nothing is ever written outside the `_tex` folder. If two textures of one file end up with the same name, the next ones get `_dup2`, `_dup3`… If the name table does not match the embedded textures, the tool prints a `!` warning and uses `tex_NN`.
- Some `.fab` files embed nothing and only reference external `.gim` files; nothing is written for those. The textures embedded in `img/ch/*.fab` are identical to the `.gim` files next to them.
- The animation and layout data in `.fab` / `.fsb` (sprite positions, frames) is not decoded yet.
- The `.vgp` sample rate is not stored in the file; it is always 44100 Hz, which is written in the VAG headers.
- Scripts and layouts name their assets with other extensions than the files on disc: `.ogg` for audio, `.anm` for animations, `.tm2` for textures. The executable rewrites the last three characters of the path when it loads the file (module addresses, i.e. `EBOOT.BIN` file offset − `0xA0`):
  - `0x5941c`–`0x59d98`, script sound command: the path is copied, and if it is at least 3 characters long its end is overwritten with `adx`. The executable contains no `ogg` string at all.
  - `0x55018`–`0x55078`: a `.anm` path becomes `.fab`.
  - `0x55418`–`0x55710`: a `.tm2` path becomes `.gim`.

  So `..\..\..\sound\bgm\bgm001.ogg` loads `res/sound/bgm/bgm001.adx`, and `..\..\..\img\ch\ch010a_s.anm` loads `res/img/ch/ch010a_s.fab`.

## Project layout

```
ptd_extract.py      command-line tool (extraction + options)
ptdlib/
  peta.py           PETA archive reader and table cipher
  yklz.py           YKLZ (LZSS) decompression
  fab.py            FANM / FSCN embedded textures
  vgp.py            VGP sound bank -> VAG
  tfp.py            T2FP font -> PNG + character map
  sos.py            SOS script string table
  convert.py        dispatch by file extension
  util.py           output helpers (files, minimal PNG writer)
```

Keep the `ptdlib/` folder next to `ptd_extract.py`. Each module can also be imported on its own, for example:

```python
from ptdlib import sos
for offset, raw in sos.strings(open('sc00001.sos', 'rb').read()):
    print(hex(offset), raw.decode('cp932'))
```

## Format notes

The PETA and YKLZ details were reverse-engineered from the game's `EBOOT.BIN` (archive loader around `0x62d4`–`0x6a6c`, decompressor at `0x78c0`). The other formats were worked out from the data files themselves. They are documented here in case someone wants to write a repacker or an editor. All values are little-endian unless stated otherwise.

### PETA archive

#### Header (`0x120` bytes)

| Offset | Type | Description |
|---|---|---|
| `0x00` | char[4] | Magic `PETA` |
| `0x04` | u32 | Size of header + table (table ends here) |
| `0x08` | u32 | Total archive size |
| `0x0C` | u32 | Table offset (always `0x120`) |
| `0x10` | u32 | File count |
| `0x14` | u16 | Directory count |
| `0x16` | u8 | Table is encrypted (1) or plain (0) |
| `0x20` | u8[256] | Substitution key |

#### Table encryption

For each byte of the table, with `i` being its position counted from `0x120`:

```
plain[i] = key[(cipher[i] ^ -i) & 0xFF]
```

The top-level archives are encrypted; the nested `__pack__` archives are not. The same cipher is used for the string tables of `.sos` scripts.

#### Table layout

The first u32 of the decrypted table is the offset of the file entries.

**Directory entries** (`0x50` bytes each, starting at `0x120`):

| Offset | Type | Description |
|---|---|---|
| `0x00` | u32 | Offset of file entries |
| `0x04` | u32 | Index of the first file in this directory |
| `0x08` | u32 | Number of files in this directory |
| `0x10` | char[64] | Directory path, e.g. `RES/SOUND/VOICE/VO000` |

**File entries** (`0x40` bytes each, sorted by name within a directory):

| Offset | Type | Description |
|---|---|---|
| `0x00` | u32 | Data offset (relative to the start of the archive) |
| `0x04` | u32 | Stored size |
| `0x08` | u8 | Compressed (`YKLZ`) flag |
| `0x10` | char[48] | File name, e.g. `SV000_000010.ADX` |

Data is aligned to `0x800` (one UMD sector) in the top-level archives.

### YKLZ compression

| Offset | Type | Description |
|---|---|---|
| `0x00` | char[4] | Magic `YKLZ` |
| `0x06` | u8 | 1 = compressed, 0 = stored |
| `0x07` | u8 | Bit split `b` (length uses the top `b - 8` bits) |
| `0x08` | u32 | Decompressed size |
| `0x10` | … | Compressed data |

The data is a plain LZSS stream. A flag byte is read MSB first, and each bit controls one token:

- `0`: copy one literal byte.
- `1`: read two bytes `b0`, `b1`, with `s = b - 8`:
  - `length = (b0 >> s) + 3`
  - `distance = ((b0 & ((1 << s) - 1)) << 8 | b1) + 1`
  - copy `length` bytes from `distance` bytes back in the output.

### SOS script (`.sos`)

| Offset | Type | Description |
|---|---|---|
| `0x00` | u8[4] | Magic `87 4C 74 68` |
| `0x04` | u32 | Version (`2`) |
| `0x08` | u32 | Bytecode offset (`0x140`) |
| `0x0C` | u32 | File size |
| `0x10`–`0x24` | u32[6] | Section offsets |
| `0x18` | u32 | String table offset (the table runs to the end of the file) |
| `0x40` | u8[256] | Substitution key |

The bytecode is **not** encrypted. Only the string table is, with the PETA cipher, `i` being counted from the start of the string table. Strings are NUL-terminated Shift-JIS (CP932); the bytecode refers to them by their offset in the table (u16 arguments).

### FANM / FSCN (`.fab` / `.fsb`)

| Offset | Type | Description |
|---|---|---|
| `0x00` | char[4] | Magic `FANM` (animation) or `FSCN` (scene) |
| `0x04` | u32 | File size |
| `0x0C` | u32 | Offset of the first embedded texture |
| `0x1C` | u32 | Texture name table: one u16 per texture, offset into the names below |
| `0x20` | u32 | Texture names, NUL-terminated Shift-JIS (the table ends here) |

The embedded textures are complete GIM files (`MIG.00.1PSP`), stored back to back in the same order as the names. The size of each GIM is its u32 at `+0x14` plus `0x10`. The list also contains references to other animations (`*.anm`, loaded as `.fab`): they have no embedded data and must be skipped when pairing names with textures. Texture names usually end in `.tm2` (sometimes `.gim`) and can be relative Windows paths such as `..\00_name\name_000.tm2`. Files with names but no embedded GIM only reference external textures. Element names in `.fsb` scenes are Shift-JIS (e.g. `選択1`, `非選択1`).

### T2FP font (`.tfp`)

| Offset | Type | Description |
|---|---|---|
| `0x00` | char[4] | Magic `T2FP` |
| `0x04` | u32 | Character code table offset |
| `0x08` | u16 | Glyph count |
| `0x0A` | u8 | Glyph width |
| `0x0B` | u8 | Glyph height |
| `0x10` | u32 | Palette offset (RGBA8888) |
| `0x14` | u32 | Glyph data offset |

The code table holds one u16 per glyph: values below `0x100` are single bytes (ASCII / half-width katakana), others are Shift-JIS pairs (`0x8140` = `　`). Glyphs follow each other with no padding; pixels are packed LSB first, with `bpp = glyph size × 8 / (width × height)`. `debugfnt.tfp` has 3,900 glyphs of 12×12 at 1 bpp.

### VGP sound bank (`.vgp`)

Raw PSP-ADPCM (VAG) data with no header: 16-byte frames, sounds stored back to back. Each sound ends with a frame whose flag byte (`+1`) is `1`, followed by an end-marker frame `00 07 77 77 …`. Zero frames pad between sounds. The tool writes each sound as a standard VAG file: a `VAGp` header (big-endian: version `0x20`, data size, sample rate, name), a leading zero frame, the original frames, then the end marker.

## Disclaimer

- This project is **not affiliated** with the publishers or developers of the game.
- **No game data** is included or distributed here: you need your own copy of the game.
- The script is an independent implementation, written from the reverse engineering of the
  file format for interoperability purposes. It contains no code from the game.
