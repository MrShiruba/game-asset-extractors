# ptd_extract

Extractor for the `.ptd` (PETA) archives of **Sora no Otoshimono: DokiDoki Summer Vacation** (PSP, `ULJM05639`).

Generic ADX rippers can pull the voice files out of `voice_adx.ptd`, but only as numbered blobs. This tool reads the archive's own (encrypted) file table, so every file comes out with its **original name and path**, in its **original format**.

## Requirements

- Python 3.6+
- No third-party dependencies

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
- **Original formats.** Nothing is converted: ADX stays ADX, GIM stays GIM, and so on. Use your usual tools (e.g. vgmstream for ADX, GimConv for GIM) afterwards.
- **Nested archives.** `res.ptd` contains further PETA archives under `res/__pack__/`. They are written out as-is **and** their contents are extracted too.
- **Container compression is removed.** Most files in `res.ptd` are wrapped in the game's own LZSS compression (`YKLZ`). This is a storage layer, not a file format, so it is always undone. Without that step the files would be unreadable.

If a file fails to decompress, the tool prints a `!` warning and writes the raw data instead of stopping.

## Format notes

These details were reverse-engineered from the game's `EBOOT.BIN` (archive loader around `0x62d4`–`0x6a6c`, decompressor at `0x78c0`). They are documented here in case someone wants to write a repacker.

### Header (`0x120` bytes, little-endian)

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

### Table encryption

For each byte of the table, with `i` being its position counted from `0x120`:

```
plain[i] = key[(cipher[i] ^ -i) & 0xFF]
```

The top-level archives are encrypted; the nested `__pack__` archives are not.

### Table layout

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

## License

Do whatever you want with this script. The game data belongs to its respective owners; only use this on a copy of a game you own.
