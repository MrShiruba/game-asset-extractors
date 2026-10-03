# DreamMix TV World Fighters – .zb extractor

An extractor for the `.zb` archives from **DreamMix TV World Fighters** (ドリームミックスTV ワールドファイターズ), the crossover fighting game released in 2003 in Japan only by Hudson Soft, Konami and Takara (developed by Bitstep), on **GameCube** and **PlayStation 2**.

Almost all of the game's data (characters, stages, textures, animations, effects, text, sounds) is packed into a single archive, `scfight.zb`, with an **encrypted** file table. This script decrypts it and extracts every file, with its original name and folder layout.

A single Python script, no dependencies, and it works for both consoles.

---

## Supported versions

| Console | Game ID | Archive | Files extracted | Contents |
|---|---|---|---|---|
| GameCube | `GKWJ18` | `scfight.zb` | 1902 | models, textures, animations, effects, parameters, text, MusyX sound bank |
| PlayStation 2 | `SLPM-65384` | `SCFIGHT.ZB` | 2034 | same data, with the PS2 sound formats |
| PlayStation 2 | `SLPM-65384` | `IRXZ.ZB` | 19 | system modules (IOP `.irx`: pad, memory card, sound, USB…) |

Both consoles use **exactly the same archive format**. Only the encryption keys differ, and the script reads them from each archive's header.

Other versions (such as the PS2 *Hudson the Best* re-release, `SLPM-65980`) have not been tested, but they very likely use the same format.

---

## Requirements

- **Python 3.6 or later** (Windows, macOS, Linux)
- No modules to install
- No executable needed (`main.dol` / `SLPM_653.84`): the decryption algorithm is built into the script

---

## Getting the archives

You need your own copy of the game.

**GameCube**

Get `scfight.zb` from the disc.

**PlayStation 2**

Copy `SCFIGHT.ZB` and `IRXZ.ZB` from the disc.

---

## Usage

```sh
python zb_extract.py <archive> [-o output_folder] [--list] [--keep-prefix]
```

| Option | Effect |
|---|---|
| `-o`, `--output` | output folder (default: the archive name without its extension) |
| `-l`, `--list` | show the file table without extracting |
| `--keep-prefix` | keep the full original path (`/home/project/ScFight/...`) |

Examples:

```sh
# GameCube
python zb_extract.py scfight.zb -o gc

# PS2
python zb_extract.py SCFIGHT.ZB -o ps2
python zb_extract.py IRXZ.ZB -o ps2_irx

# List the contents without extracting
python zb_extract.py scfight.zb --list
```

The `--list` output shows, for each file: compression (`z` = zlib, `-` = stored), uncompressed size, stored size, offset in the archive, and the original path.

---

## Extracted layout

The paths in the archive are the developers' original paths (`/home/project/ScFight/GCN/masterdata/...` on GameCube, `/home/project/ScFight/masterdata/...` on PS2). By default the script strips this prefix, so both versions give the same layout:

```
masterdata/
├── char/        playable characters, one folder per character (2-letter code)
│   └── si/      e.g. Simon Belmont: si1-4.cs (models/costumes), si.as (animations), *.db (moves, hitboxes…)
├── stage/       stages (models, lights, cameras, collisions)
├── effect/      visual effects (.efo, .eff, .txd)
├── cpu/         AI behaviour
├── sprite/      2D interface (.txd, .png, .db)
├── font/        text and messages (.msg)
├── param/       game parameters
├── misc/        miscellaneous objects and items
├── sound/gcn/   GameCube: MusyX sound bank
├── sound/ps2/   PS2: sound banks and sequences
├── bgm1/ps2/    PS2: headers for the music streams
├── debug/       debug fonts and cursors
└── savemisc/    save data (icon…)
```

`IRXZ.ZB` gives `program/modules/*.irx`.

---

## Formats of the extracted files

The script extracts the files **as they are in the archive**, with no conversion. For reference:

| Extension | Format | Notes |
|---|---|---|
| `.cs` | RenderWare 3.x | a texture dictionary (custom chunk `0x23`) followed by a standard Clump (`.dff`) |
| `.txd` | RenderWare | the same texture dictionary (`0x23` chunk containing standard RwImage `0x18` chunks: 4/8-bit palettised or 32-bit images, plus mipmaps) |
| `.as` | RenderWare | animations (chunk `0x1B`) |
| `.png` | PNG | stored as-is in the archive (debug and loading screens) |
| `.db`, `.efo`, `.eff` | text | parameters, effects and sprites, in a readable `{ key value }` syntax |
| `.msg` | binary | message tables (`MSG\0` signature) |
| `.pool` `.proj` `.samp` `.sdir` `.song` | MusyX | GameCube sound bank (samples in `.samp`, directory in `.sdir`) |
| `.hd` / `.bd` | Sony | PS2 sound banks (header + ADPCM data) |
| `.sq` | Sony | PS2 music sequences |
| `.mih` | — | headers for the PS2 `.MIB` music streams |
| `.irx` | ELF | PS2 IOP modules |

### Other files on the disc (outside the archives)

| Console | Files | Contents | Readable with |
|---|---|---|---|
| PS2 | `TOKUTEN.BIN` | 20 MiB of padding (one ~25 KB random block repeated), never used by the game | — |

---

## Archive format

All integers are **big-endian**, including on PS2.

### Header (0x20 bytes, plaintext)

| Offset | Type | Description |
|---|---|---|
| 0x00 | u32 | magic `0x0131A36E` (= 20030318, a date) |
| 0x04 | u32 | version `0x32` |
| 0x08 | u32 | number of files |
| 0x0C | u32 | TOC size (the TOC runs from 0x20 to 0x20 + size) |
| 0x10 | u32 | key seed: high 16 bits = A, low 16 bits = B |
| 0x14 | u32 | key seed: K |
| 0x18 | u32 | timestamp (time_t) |
| 0x1C | u32 | timestamp (duplicate) |

### TOC entry (encrypted), repeated for each file

| Type | Description |
|---|---|
| cstring | path; each character is XORed with the low byte of the keystream, unless it already equals that byte (so the result is never `\0`). The terminating `\0` is not encrypted. |
| u32 ^ K | flags: low byte `'z'` (0x7A) = zlib, `'n'` = stored |
| u32 ^ K | uncompressed size |
| u32 ^ K | stored size |
| u32 ^ K | absolute offset of the data in the archive |
| u32 | unknown (plaintext, always 0) |
| u32 | unknown (plaintext, always 0) |
| cstring | second string, encrypted like the path (always empty) |

Every encrypted byte or word advances the keystream by **one step**, in reading order.

### Keystream

Two small shift registers (A and B, 15 bits) feed a 32-bit accumulator K:

```
A = seed >> 16
B = seed & 0xFFFF
K = key_k

step():
    bit = ((A & 0x0008) == 0x0008) XOR ((A & 0x4000) == 0x4000)
    A   = (2*A + (1 - bit)) & 0x7FFF
    bit = ((B & 0x0004) == 0x0004) XOR ((B & 0x4000) == 0x4000)
    B   = (2*B + (1 - bit)) & 0x7FFF
    A   = 5*A + 1
    B   = 5*B + 1
    K  ^= A | (B << 15)
    return K
```

- To decrypt a 32-bit value: `value ^ step()`
- To decrypt a character: `c ^ (step() & 0xFF)`, unless `c == (key & 0xFF)`

### File data

The data is **not encrypted**. Each file is either stored as-is (`'n'`) or compressed as a standard zlib stream (`'z'`; the game embeds zlib 1.1.3).

### Where this comes from

The format was reverse-engineered from the GameCube executable (`main.dol`, GKWJ18), in the `hi_fileio.c` module:

| Address | Role |
|---|---|
| `0x801119CC` | archive initialisation (`/scfight.zb`) |
| `0x80110918` | TOC reading and decryption |
| `0x80208688` | table of shift-register constants |

The PS2 executable (`SLPM_653.84`) references `/scfight.zb` and `/irxz.zb` the same way.

---

## Disclaimer

- This project is **not affiliated** with Hudson Soft, Konami, Takara, Bitstep, Nintendo or Sony.
- **No game data** (archives, extracted files, executables, disc images) is included or distributed here. To use the script, you need your own copy of the game.
- The script is an independent implementation, written from scratch from the reverse engineering of the archive format for interoperability purposes. It contains no code from the game.
- All trademarks and characters belong to their respective owners.

## License

This project is released under **The Unlicense** (public domain): you can use, modify and redistribute it freely, without asking permission or crediting the author. See the `LICENSE` file.
