# Fate/tiger colosseum — extraction tools

Tools and documentation to extract and study the files of **Fate/tiger colosseum**
(PSP, 2007, cavia / TYPE-MOON / Capcom, product code ULJM05266).

> **No game files are included.** This repository only contains scripts and documentation.
> You need your own copy of the game.

## Requirements

- Python 3.8+ (no external dependencies)
- The contents of your ISO (extracted with 7-Zip, UMDGen, …), in particular
  `PSP_GAME/USRDIR/BUILDED.BND`

## Quick start

```bash
python3 fate_tiger.py all path/to/PSP_GAME/USRDIR/BUILDED.BND
```

This extracts every file (nested archives included) to `extracted/`, then dumps the story
dialogue to `script_text/` and script listings to `script_asm/`. You get 6324 files in `extracted/prj/tiger/data/builded/…`
with their original names and folder layout. Expect about 1 GB of disk space.

## Commands

```bash
# List the contents of an archive
python3 fate_tiger.py list BUILDED.BND

# Extract (nested BNDs included by default)
python3 fate_tiger.py extract BUILDED.BND -o extracted
python3 fate_tiger.py extract BUILDED.BND --no-recursive     # top level only
python3 fate_tiger.py extract BUILDED.BND --drop-nested      # contents only, not the inner .bnd files

# Dump dialogue from the .pac scripts
python3 fate_tiger.py text extracted/prj/tiger/data/builded/script -o script_text

# Disassemble the .pac scripts (command names taken from the game itself)
python3 fate_tiger.py disasm extracted/prj/tiger/data/builded/script -o script_asm
```

Excerpt of `disasm` output:

```
001318  setMessageLabel                               0x256d0 "(dialogue line)"
001320  cmd_mov                                       i[0], 1
001334  cmd_mov                                       i[1], 1766
001348  cmd_call                                      ->0x2a0e4
```

`text` writes, for each `story_main_*_jp.pac`, a readable `.txt` and a `.csv` (UTF-8, opens in Excel / LibreOffice)
with the speaker, the `.at3` voice file and the Japanese text of each line:

```
[skw] 10SBW/skw100060.at3
(dialogue line, one line per row)
```

## Opening the extracted files

| Files | Tool |
|---|---|
| `.at3`, `.vag`, `.phd`/`.pbd` (audio) | [vgmstream](https://github.com/vgmstream/vgmstream), foobar2000 + vgmstream |
| `.gmo` (3D models), `.gim` (textures) | [Noesis](https://richwhitehouse.com/index.php?content=inc_projects.php), GimConv |
| `.pmf` (movies) | PMF tools / ffmpeg |
| everything else | see [`docs/formats.md`](docs/formats.md) |

## Research status

Details for each format are in [`docs/formats.md`](docs/formats.md).

Every file type in the archive is identified and documented. Collisions, walls, precompiled
models, particle effects and move lists were checked on every file of their type; the script
format on a sample of scripts. Two small things remain: words 6 and 7 of the move-list action records, which the game never
reads (checked with PPSSPP memory breakpoints), and the exact role of a few particle-stage fields.
`docs/formats.md` marks them.

Contributions are welcome, for example converters (GMP or COL to OBJ, EFFECT2 viewer) built from the documentation.

## Layout

```
fate_tiger.py      command-line entry point
tools/
  bnd.py           BND archive reader / extractor
  pac_text.py      dialogue extraction from .pac scripts
  pac_disasm.py    .pac script disassembler
  pac_opcodes.json command names (from the game's EBOOT)
docs/
  formats.md       file format documentation
  pac_opcodes.md   full list of script commands
```

## Legal

Fate/tiger colosseum © TYPE-MOON / Capcom / cavia. Fan project, not affiliated with the rights
holders. Do not publish game files.
