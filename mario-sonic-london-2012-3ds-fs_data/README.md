# mslondon2012extract

All-in-one extractor for **Mario & Sonic at the London 2012 Olympic Games**
(Nintendo 3DS). One command turns the game's `fs_data.cpk` into a tree of
**native game files**, sorted by category and named after the game's own
internal names.

```
python mslondon2012extract.py fs_data.cpk
```

- Native formats only: nothing is converted (no WAV, no PNG). The few extra
  files written are byte-for-byte copies (`.bcres` inside `.swif`) or plain
  readable copies of the game texts (`.txt`).
- No dependencies: standard Python 3.8+ only.
- Tested on the Japanese, European and American releases (0 problems).

No game data is included in this repository. You need your own dump of the
game and its extracted RomFS (`fs_data.cpk` is at the root of the RomFS).

## Usage

```
python mslondon2012extract.py fs_data.cpk [-o OUTPUT_DIR] [options]
```

| Option | Effect |
|---|---|
| `--mode sorted` | (default) categories and readable names |
| `--mode raw` | numbered tree exactly as stored in `fs_data.cpk` |
| `-o DIR` | output folder (default: `fs_data_extracted`) |
| `-j N` | number of worker processes (default: all CPU cores) |
| `--names FILE` | use another names list instead of `mslondon2012/names.csv` |
| `--keep-cpk` | also keep every nested `.cpk` as is |
| `--no-sound` | skip the sound bank step (ACB/AWB pairing, cue list) |
| `--no-unwrap` | do not write the extra `.bcres` / `.txt` copies |

The `mslondon2012/` folder must stay next to `mslondon2012extract.py`.
A full extraction takes 1 to 4 minutes depending on the version.

## Output (sorted mode)

```
fs_data_extracted/
  sound/        1427_bgm_swim_back.acb + .awb, 1588_voice_bowser_jr.acb + .awb ...
  models/       3D models (.bcres) and their .stat
  animations/   skeletal / texture / visibility animations (.bcres)
  textures/     textures (.swif + the .bcres inside), one sub-folder per language
  layouts/      2D screen layouts (.swif)
  scenes/       cameras, lights, fog, colour tables (.bcres)
  fonts/        .bcfnt, one sub-folder per language
  text/         game texts (.bin + readable .txt), one sub-folder per language
  data/         story mode shot lists
  collision/    .coli
  other/        everything else (shader, empty placeholders, flags table)
  index.csv     sorted path -> path in raw mode
  report.txt    file types, every cue with its waveforms, problems
```

Every file of the CPK ends up somewhere; `index.csv` maps each sorted file
back to its number in `fs_data.cpk` (`files/1428/0000.adx` in raw mode).

File names are `<number>_<internal name>.<ext>`, e.g.
`textures/fr/1940-0004_fr_aqubr0.bcres` = entry 4 of the nested CPK 1940,
a texture the game calls `fr_aqubr0`. The number keeps the game's order.

### Languages

Localised releases store each language as a block of entries (JP: `jp` only;
EU: `en fr it ge sp du`; US: `en fr sp`). Textures, layouts, texts and fonts
are put in a sub-folder per language (`ge` = German, `sp` = Spanish,
`du` = Dutch). The language comes from the screen (nested CPK) or language
block a file belongs to, not from its name alone: localised blocks keep a
few textures with their original `jp_*` names. Shared files stay at the root
of their category.

## Sound

The game uses CRI ADX2 (early 3DS version, ACB format 0.81):

- **Memory banks** (sound effects): one `.acb` holding the cue names and the
  waveforms (BCWAV). Open the `.acb` with vgmstream.
- **Streamed banks** (music, voices): an `.acb` (cue names) plus an `.awb`
  holding the waveforms (ADX). In this old version the AWB is a CPK; the
  extractor writes it as `<bank>.awb` next to `<bank>.acb`. **Open the `.awb`**
  with vgmstream: it reads the cue names from the `.acb` of the same name.
- `1534_atom_config.acf` is the global sound configuration (categories, buses,
  DSP effects). It holds no audio.

Each ACB is paired with its streamed AWB automatically: the AWB is one of the
following CPKs (not always the next one: 1566 -> 1569, 1574 -> 1577), chosen by
sample rate, channel count and length of every waveform.

`report.txt` lists every cue and the waveforms it plays, e.g.
`1402.acb/Kick_Left.bcwav: waveform 1, 16364 Hz, 1 ch, pan -200`
(stereo sounds are stored as two mono waveforms panned left and right).

Players: [vgmstream](https://github.com/vgmstream/vgmstream) (CLI, foobar2000
plugin, Winamp plugin...).

## names.csv

`fs_data.cpk` stores no file names, only numbers. Sound banks are named from
`mslondon2012/names.csv`:

```
# file;name;confidence;note;check
1588;voice_bowser_jr;sure;BWJ;B_Suc
```

| Column | Meaning |
|---|---|
| file | entry number in `fs_data.cpk` |
| name | name used in sorted mode (`bgm_`, `se_`, `voice_`...) |
| confidence | `sure`, `probable` or `unknown` |
| note | how the name was found |
| check | first waveform name of the bank (sorted), from its cues |

The `check` column protects against releases numbered differently: if the
bank found at that number does not match, it is left unnamed and the report
says so. The sound banks have the same numbers in the JP, EU and US releases.

How the names were found:

- music: from the cue names (`Swim_Back`, `Archery_Team`...);
- sound effects: matched to events from their cue names (`Gong_Start` =
  boxing, `Whinny` = equestrian...) and the order of the game's event codes;
- voices: by ear, then confirmed by the bank order, which follows the
  characters' internal codes (`AMY`, `BLZ`, `BWJ`, `BWS`... and Japanese names
  for Mario enemies: Kuribo, Teresa, Heiho, Jugemu, Kinopio...).

Corrections are welcome: edit `names.csv` and open a pull request, ideally
moving `probable` / `unknown` lines to `sure`.

Other files need no list: textures, models, animations and layouts are named
after the names stored inside them; texts and fonts after the screen they
belong to.

## Formats

| Format | Content |
|---|---|
| `.cpk` | CRI archive. `fs_data.cpk` uses an ITOC table (numbers only); nested CPKs use TOC or ITOC. CRILAYLA compression is decompressed. |
| `.acb` / `.awb` / `.acf` | CRI ADX2 sound banks / waveform banks / configuration |
| `.adx`, `.bcwav` | waveforms (CRI ADX, Nintendo DSP-ADPCM) |
| `.bcres` | Nintendo CGFX: models, textures, animations, cameras, lights |
| `.swif` | Sega 2D graphics container. Texture SWIF: `SWTD` block wrapping a complete CGFX (written next to it as `.bcres`). Layout SWIF: `SWTL` (texture names) + `SWPR` (parts, positions, animations), no image data. |
| `.stat` | small `STAT ... END` table found with each graphics package; `0000.stat` is a per-file flags table of the CPK |
| `.bin` (text) | message table: u16 count, u16 flags, u32 offsets, UTF-16LE strings with `[Cn]` colour tags. A UTF-8 `.txt` copy is written next to it. |
| `.bin` (data) | story mode shot lists (`01_01`, `01_07_panA`...), named after the episode scene that follows them |
| `.bcfnt` | Nintendo CFNT fonts: one main font per language, and per-screen glyph subsets for the text next to them |
| `.coli` | collision data |
| `.dvlb` | PICA200 shader |

Recommended tools for `.bcres`: Ohana3DS Rebirth, SPICA.

## Code layout

| Module | Role |
|---|---|
| `mslondon2012extract.py` | command line, steps, report |
| `cpk.py`, `crilayla.py`, `utf.py` | CRI CPK archives, compression, @UTF tables |
| `extract.py` | step 1: recursive extraction |
| `filetypes.py` | file type detection from contents |
| `acb.py`, `sound.py` | step 2: ACB parsing, cue -> waveform resolution, AWB pairing |
| `swif.py`, `cgfx.py`, `text.py` | SWIF, CGFX table of contents, message tables |
| `sort.py`, `names.py`, `names.csv` | step 3: sorted mode |

## Credits

- CRI formats: thanks to the [vgmstream](https://github.com/vgmstream/vgmstream)
  project, used as the reference to check the sound bank handling.
- Character and event information: [Super Mario Wiki](https://www.mariowiki.com/).
