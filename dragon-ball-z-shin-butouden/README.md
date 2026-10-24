# Dragon Ball Z: Shinbutouden – audio extraction

Python script that extracts the **sound effects and voices** of **Dragon Ball Z: Shinbutouden** (Sega Saturn, 1995, Bandai, T-13302G) from the game's internal files.

It reads two proprietary formats:

- **TON banks** (`GK_V.BIN`, `SEALLV.BIN`, `WV_GOK.BIN`...), the sample banks of the Saturn sound driver;
- **`.PCM` voices** (`KOJIN/`, `YBT/`, `END/`, `BOOG_1.PCM`), compressed with a custom LZSS.

Each sample is written as raw PCM (`.raw`). Each output folder gets **a single `.txth`** that makes all of its `.raw` files playable in [vgmstream](https://github.com/vgmstream/vgmstream) without conversion. The script only does what vgmstream can't do on its own: reading TON banks and decompressing the voices.

This repository contains **no game data**. Extract the files from your own dump first.

## Requirements

Python 3.8 or newer, no external dependencies (Linux, WSL, macOS, Windows).

## Usage

```bash
python3 dbzsb.py iso/ sounds/                      # the whole game folder
python3 dbzsb.py iso/GK_V.BIN iso/KOJIN sounds/    # a few files / folders
```

The output mirrors the game's tree. For example, `GK_V.BIN` gives `sounds/GK_V/GK_V_00.raw`, `GK_V_01.raw`..., and `KOJIN/GOKU18.PCM` gives `sounds/KOJIN/GOKU18.raw`. Files that aren't audio are skipped.

Within a TON bank, samples don't all share the same sample rate or format (8 or 16-bit), and some loop. In that case the folder's `.txth` points to a `.names.txt` table (vgmstream's `name_table` feature) with one line per file. Voice folders don't need one, since all their voices share the same settings.

## Audio content of the game

| Files | Content |
|---|---|
| `XX_V.BIN` (`GK_V`, `VJ_V`...) | Character voices during fights |
| `WV_XXX.BIN` | Victory lines, followed by the World Tournament announcer calling the winner (some announcer lines are shared by every character) |
| `KOJIN/*.PCM` | Pre-fight lines, which change with the opponent |
| `YBT/Pxx.PCM` | Character select voices (two per character) |
| `YBT/MC_*.PCM` | World Tournament announcer: intro, rounds, results, character names |
| `END/EDPCM*.PCM` | Story mode ending voices |
| `SEALLV.BIN` | Common sound effects |
| `TENKASEV.BIN` | World Tournament crowd |
| `HAI_*V.BIN` | Stage ambience |
| `SE1V.BIN`, `STSEV.BIN`, `STBGMV.BIN`, `ST_OPV.BIN`, `TTV.BIN`, `SELCTV.BIN`, `*ENDV.BIN`, `TEN_OPNV.BIN`, `TEN_ENDV.BIN` | Instrument samples for the sequenced music |
| `SZ_V.BIN`, `WV_SUZ.BIN`, `BOOG_1.PCM` | Unused character "SUZ" (see below) |

### Character codes

The game lists its characters in the same order in every table (`LOAD.BIN`, `DRAGON.BIN`, `DBTIT.BIN`, `OPTION.BIN`). Reading those tables side by side gives each character's files:

| # | Character | Voices | Victory | `KOJIN/` | `YBT/P` (select) | `YBT/MC_` (name) |
|---|---|---|---|---|---|---|
| 0 | Son Goku | `GK_V` | `WV_GOK` | `GOKU` | `1C`, `1D` | `20` |
| 1 | Son Goku (Super Saiyan 3) | `GK_V` (shared) | `WV_GO3` | `GOK3` | `0C`, `0D` | `21` |
| 2 | Son Gohan | `GH_V` | `WV_GHN` | `GOHA` | `0E`, `0F` | `22` |
| 3 | Son Goten | `GT_V` | `WV_GTN` | `GOTE` | `12`, `13` | `23` |
| 4 | Majin Vegeta | `VJ_V` | `WV_VEJ` | `MBEJ` | `32`, `33` | `24` |
| 5 | Trunks | `TR_V` | `WV_LTR` | `TRAN` | `1E`, `1F` | `25` |
| 6 | Trunks (kid) | `CT_V` | `WV_STR` | `CTRA` | `2E`, `2F` | `26` |
| 7 | Gotenks | `GS_V` | `WV_GTK` | `GOKS` | `14`, `15` | `27` |
| 8 | Piccolo | `PC_V` | `WV_PIC` | `PIKK` | `20`, `21` | `28` |
| 9 | Kuririn | `KR_V` | `WV_KRI` | `KURI` | `1A`, `1B` | `29` |
| 10 | Tenshinhan | `TN_V` | `WV_TEN` | `TENS` | `30`, `31` | `2A` |
| 11 | Kame Sennin | `KM_V` | `WV_KAM` | — | `18`, `19` | `2B` |
| 12 | Zarbon | `ZB_V` | `WV_ZBN` | `ZABO` | `34`, `35` | `2C` |
| 13 | Recoome | `RC_V` | `WV_REC` | `RIKU` | `22`, `23` | `2D` |
| 14 | Ginyu | `GN_V` | `WV_GNW` | `GINY` | `0A`, `0B` | `2E` |
| 15 | Freeza | `FR_V` | `WV_FRE` | `HURI` | `04`, `05` | `2F` |
| 16 | Android 18 | `18_V` | `WV_18G` | `18GO` | `08`, `09` | `30` |
| 17 | Android 16 | `16_V` | `WV_16G` | `16GO` | `06`, `07` | `31` |
| 18 | Cell | `SL_V` | `WV_SEL` | `CELL` | `2A`, `2B` | `32` |
| 19 | Kaiōshin | `KI_V` | `WV_KAI` | `KAIO` | `16`, `17` | `33` |
| 20 | Dabura | `DB_V` | `WV_DBR` | `DARB` | `02`, `03` | `34` |
| 21 | Majin Boo | `BO_V` | `WV_BOO` | `NBOO` | `00`, `01` | `35` |
| 22 | Super Boo | `SB_V` | `WV_SBO` | `SBOO` | `28`, `29` | `36` |
| 23 | Mr. Satan | `ST_V` | `WV_STN` | — | `26`, `27` | `37` |
| 24 | Great Saiyaman | `SI_V` | `WV_SAI` | `GSMA` | `24`, `25` | `38` |
| 25 | Son Goku (kid) | `SG_V` | `WV_SGK` | — | `2C`, `2D` | `39` |
| 26 | Gogeta | `GJ_V` | `WV_GJT` | `GOJI` | `10`, `11` | `3A` |
| 27 | SUZ (unused) | `SZ_V` | `WV_SUZ` | — | — | — |

### Unused content

- **SUZ**, a 28th character (black hair, yellow gi, Goku's moveset), has sprites (`SZK.BIN`), voices (`SZ_V`), sound effects and victory lines (`WV_SUZ`), but no select voice, announcer name, portrait or pre-fight lines.
- **`BOOG_1.PCM`** ("つまらないぞ！") is only loaded by `SUZUOP.BIN`, together with `SUZU.DAT`. The intro (`OPEN.BIN`) has a branch that would launch `SUZUOP.BIN`, but the mode value that selects it is never set, so it can't be reached.
- **`CPKTST.BIN`** is a video test program that refers to `DBZCPK.CPK` and `DBZCPK2.CPK`, two files that aren't on the disc.

## Sample rates

- **TON banks**: the rate is derived from each sample's base note (see [FORMATS.md](FORMATS.md)).
- **`.PCM` voices**: the files don't store their rate. `KOJIN/`, `YBT/` and `END/` play at **11,025 Hz**, and `BOOG_1.PCM` at **22,050 Hz** (both checked by listening). Exceptions to the default are listed in `PCM_RATE_OVERRIDES` in `dbz_shinbutouden/audio.py`.
