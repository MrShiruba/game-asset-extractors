# Excitebike: World Rally – archive extractor

An extractor for the `.res`, `.trk` and `.car` archives of **Excitebike: World Rally**
(**WiiWare**), the motocross game developed by Monster Games and released by Nintendo in
2009.

The game stores its assets in `0TSR` archives, compressed with QuickLZ, and keeps their
file tables apart in a separate archive, `tocres.res`. This script reads those tables and
extracts every file of every archive, with its original name, sorted by file type.

---

## Requirements

- **Python 3.6 or later**, no modules to install

---

## Getting the files

You need your own copy of the game. A WiiWare game is a WAD file; its data is in the
content `00000002.app`, which is a U8 archive. Unpack the WAD, then unpack
`00000002.app` with a Wii tool: you get a folder holding `tocres.res` and the `.res`,
`.trk` and `.car` archives. That folder is the input of the script.

---

## Usage

```sh
python3 ebwr_extract.py <input_folder> [output_folder]
```

| Argument | Meaning |
|---|---|
| `input_folder` | folder holding `tocres.res` and the archives |
| `output_folder` | where files are written (default: `<input_folder>/_extracted`) |

Example:

```sh
python3 ebwr_extract.py 00000002_app_out out
```

Every `.res`, `.trk` and `.car` archive of the folder is extracted in one run, except
`tocres.res` itself. Archives without a file table in `tocres.res` are skipped with a
warning.

---

## Extracted layout

```
out/
└── <archive name>/          e.g. UICommon.res/
    ├── <type>/              one folder per file type, as stored in the archive
    │   └── <file name>
    └── misc/                files without a type
```

Files are written **as they are stored**, with no conversion: only the archive
compression is undone.

---

## Formats

All integers are little-endian.

### `0TSR` archive

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | char[4] | magic `0TSR` |
| 0x20 | u32 | number of files |
| 0x24 | u32 | size of the data, uncompressed |
| 0x28 | u32 | size of the data, compressed (equal to the previous one when not compressed) |
| 0x80 | ... | data |

Compressed data is a series of `PMCr` blocks, each one followed by a QuickLZ stream:

| Offset in the block | Type | Meaning |
|---|---|---|
| 0x00 | char[4] | magic `PMCr` |
| 0x08 | u32 | size of the compressed stream |
| 0x10 | ... | QuickLZ level 3 stream |

The decompressed blocks, put end to end, give the data of the archive.

### File tables (`.toc`)

`tocres.res` is itself a `0TSR` archive. It holds one `.toc` file per archive, named after
it (`UICommon.toc` for `UICommon.res`). A `.toc` starts with a 0x20-byte header, followed
by one 0x28-byte entry per file, then by the file names:

| Offset in the entry | Type | Meaning |
|---|---|---|
| 0x00 | u32 | offset of the name, from the end of the entries |
| 0x04 | char[4] | file type, stored reversed |
| 0x08 | u32 | unknown |
| 0x0C | u32 | size |
| 0x10 | u32 | offset in the decompressed data |
| 0x14 | u32 | hash |

`tocres.res` uses the same entries, without the 0x20-byte header.

---

## Disclaimer

- This project is **not affiliated** with Nintendo or Monster Games.
- **No game data** is included or distributed here: you need your own copy of the game.
- The script is an independent implementation, written from the reverse engineering of the
  file format for interoperability purposes. It contains no code from the game.

## License

This project is released under **The Unlicense** (public domain). See the `LICENSE` file
at the root of the repository.
