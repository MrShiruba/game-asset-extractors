# Super Dragon Ball Z – GAME.DAT extractor

An extractor for **Super Dragon Ball Z** (超ドラゴンボールZ, PlayStation 2, `SLPS-25642`),
the fighting game developed by Arika and released by Bandai in 2005.

The game keeps almost all its data in one big file, `GAME.DAT`, whose file table is in a
separate, obfuscated file, `INFO.DAT`. This script decodes the table and extracts every
file with its original name and folder layout.

The folder also holds a vgmstream configuration file to play the game's sound banks.

---

## Requirements

- **Python 3.6 or later**, no modules to install
- [vgmstream](https://vgmstream.org), to play the sound banks

---

## Getting the files

You need your own copy of the game. Copy `INFO.DAT` and `GAME.DAT` from the disc.

---

## Usage

```sh
python3 sdbz_extract.py INFO.DAT GAME.DAT [-o output_folder] [--list] [--dump-toc file]
```

| Option | Effect |
|---|---|
| `-o`, `--out` | output folder (default: `out`) |
| `--list` | show the file table (offset, size, name) without extracting |
| `--dump-toc` | also write the decoded `INFO.DAT` to a file, for study |

Examples:

```sh
python3 sdbz_extract.py INFO.DAT GAME.DAT -o out
python3 sdbz_extract.py INFO.DAT GAME.DAT --list
```

Files are written **as they are stored**, with no conversion, under their original paths
(for example `sqm/gameover.ams`). Entries pointing outside `GAME.DAT`, or with an empty
name, are skipped with a warning.

---

## Sound banks (`.ase`)

The `.ase` files are Arika sound banks: several mono PS-ADPCM sounds in one file.
vgmstream cannot open them by itself, so this folder provides `.ase.txth`, a description of
the format for vgmstream.

1. Copy `.ase.txth` into the folder holding the `.ase` files (keep the name as it is, with
   the leading dot).
2. Open any `.ase` file with vgmstream (or a player using it, such as foobar2000 with the
   vgmstream component). Each sound of the bank is a subsong.

Format of an `.ase` bank:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | u32 | version (100) |
| 0x04 | u32 | number of sounds |
| 0x08 | u32 | size of the sound data |
| 0x0C | N x 8 bytes | per sound: u32 SPU2 pitch, u32 offset in the sound data |
| end - data size | ... | mono PS-ADPCM sound data, up to the end of the file |

The sample rate of a sound is `pitch x 48000 / 4096`.

---

## INFO.DAT format

`INFO.DAT` is a table of 48-byte (0x30) entries. Reverse-engineered from the disc's IOP
module `ARKD_DVD.IRX`.

**Entry 0** (header):

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | 16 bytes | key, in plain text: `` `www.arika.co.jp `` |
| 0x2C | u32 | number of files |

**Obfuscation**: every byte from offset 0x10 on is encoded. To decode the byte at
position `pos`:

```
b = swap_nibbles(b)
b = ~b
b = b - key[(pos - 16) % 16]
```

The driver only decodes the table when the first byte of the file is not zero.

**Entries 1 to n** (one per file):

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | ASCIIZ | file path, e.g. `sqm/gameover.ams` |
| 0x24 | u32 | start sector in `GAME.DAT` (2048-byte sectors) |
| 0x28 | u32 | size in sectors (rounded up) |
| 0x2C | u32 | size in bytes |

---

## Disclaimer

- This project is **not affiliated** with Arika, Bandai Namco or Sony.
- **No game data** is included or distributed here: you need your own copy of the game.
- The script is an independent implementation, written from the reverse engineering of the
  file format for interoperability purposes. It contains no code from the game.

## License

This project is released under **The Unlicense** (public domain). See the `LICENSE` file
at the root of the repository.
