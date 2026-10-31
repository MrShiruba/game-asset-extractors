# dbz-arcade-ripper

Asset ripper for Banpresto's two **Dragon Ball Z** arcade fighting games (Konami hardware):

- **Dragon Ball Z** (1993): MAME set `dbz` or `dbza`
- **Dragon Ball Z 2 Super Battle** (1994): MAME set `dbz2` (see [the DBZ2 section](#dragon-ball-z-2-super-battle))

The game is detected automatically from the files in the zip. For the first game (`dbz.zip`), you get:

| Target | What you get |
|---|---|
| `samples` | **Every voice and sound effect** (shouts, hits, explosions…) of the OKI M6295 chip: one **VGM** per sample (original ADPCM data, lossless) |
| `music` | The **16 music tracks** as **VGM** (lossless) |
| `sprites` | **Complete frames** of the 10 fighters with **all their palettes** (normal, effects, Kaioken…, P1 and P2); **effects, projectiles, texts (JP/EN win quotes, HUD), select-screen portraits, credits** (spectators are in `stages/`) |
| `stages` | **One folder per stage** (9): both 1024×512 layers (background + foreground), the **tiles** used (coloured, ROM order), the **tile animations** (Tenkaichi Budokai announcer, crowd, seagull, waves, lightning…) and the stage's **spectators** |
| `screens` | The **fixed screens** in colour: fight **HUD**, logos (Banpresto, Cobra Team / Magical Formation, DRAGON BALL Z), copyright, **select screen** background and frames, **hi-score table**, every fighter's **ending pictures** (+ JP and EN texts), **test mode** menus |
| `rawsprites` | The whole raw sprite ROM in grayscale (unassembled pieces) |
| `tiles` | **Complete** raw dump of the tile ROMs (K056832 8×8 and K053936 16×16), ROM order, grayscale (a tile on its own has no colour; coloured versions are in `stages/` and `screens/tiles/`) |
| `palettes` | Every palette found in the program (image + JSON) |

> ⚠️ No ROMs are provided here. Use your own dump. The extracted assets remain the property of their rights holders (Bird Studio / Shueisha, Toei Animation, Bandai Namco).

## Installation

Python 3.8+:

```bash
pip install -r requirements.txt
```

All images are **indexed PNGs**: every pixel keeps its original colour number (0–15, 0 = transparent) with the game
palette attached, so palettes can be swapped losslessly (Aseprite, GIMP, Photoshop…).

VGM files play in **VGMPlay** or in **foobar2000** with a VGM plugin ("VGM Input" or "Game Emu Player").
⚠️ vgmstream does **not** play VGM (it is a chip register log, not an audio stream).

Loops are handled automatically by these players. To make a WAV from the command line, use `vgm2wav`
(part of [libvgm](https://github.com/ValleyBell/libvgm)):

```bash
vgm2wav --loops 3 --fade 0 music_0a.vgm music_0a.wav   # intro + 3 passes of the loop, no fade
vgm2wav --loops 2 --fade 5 music_01.vgm music_01.wav   # intro + 2 loops + 5 s fade-out
```

For a game engine (intro once, then endless loop): export with `--loops 1 --fade 0` and set the loop to
`loop_start` → `seconds` from `sounds_index.json`.

## Usage

```bash
python dbz_arcade_rip.py dbz.zip                    # extract everything to ./dbz_rip
python dbz_arcade_rip.py dbz2.zip                   # DBZ2: extract everything to ./dbz2_rip
python dbz_arcade_rip.py dbz.zip samples sprites    # only voices/sound effects + sprites
python dbz_arcade_rip.py path/to/rom_folder -o output music
python dbz_arcade_rip.py --help
```

Aliases: `voices`, `sfx` → `samples`; `sounds` → `music`; `hud` → `screens`; `sprite` → `sprites`.

Useful options:

- `--no-frames`: sheets only, no PNG per frame
- `--no-p2`: no player-2 colour sheets (first game)
- `--strict`: refuse ROMs whose CRC does not match

Run time: ~1 min for the graphics, ~2 min for the music (pure Python emulation).

## Output (DBZ 1993)

```
dbz_rip/
├── samples/            oki_001.vgm … oki_104.vgm + index.json
├── music/              music_01.vgm … music_10.vgm
├── sounds_index.json
├── sprites/
│   ├── characters/
│   │   ├── 00_goku/
│   │   │   ├── frames_normal/000.png …     (one frame per file, normal palette)
│   │   │   ├── frames_special/…            (special moves)
│   │   │   ├── sheet_normal_p1.png         (P1 sheet)
│   │   │   ├── sheet_normal_p2.png         (player-2 colours)
│   │   │   ├── sheet_normal_p1_kaioken.png (Goku and SSJ Goku only)
│   │   │   ├── palettes.png                (the 4 palettes loaded per player: P1 v0–v3 then P2 v0–v3)
│   │   │   └── frames.json                 (ROM address, anchor, size of every frame)
│   │   └── 01_vegeta/ … 07_frieza_stage1/ 08_frieza_stage2/ 09_goku_super_saiyan/
│   ├── common/                     (shared sprites, not the fighters)
│   │   ├── effects/                (common palette) + effects/by_fighter/<fighter>/sheet_v1.png, sheet_v2.png
│   │   ├── goku_parts/ shadows/
│   │   ├── projectiles/<fighter>/ effects_2/<fighter>/   (each fighter's colours, + sheet_p2.png)
│   │   ├── win_quotes/ hud_text/ credits/ credits_2/
│   │   ├── portraits/<fighter>/idle.png, selected.png
│   │   └── shared_palettes_by_stage.png
│   └── raw_blocks/
├── stages/
│   └── stage0/ … stage8/
│       ├── back.png, front.png           both 1024×512 layers
│       ├── tiles_back.png, tiles_front.png   tiles used, coloured, ROM order
│       ├── animations/<layer>_<k>/       00.png, 01.png… + sheet.png
│       ├── spectators/<k>/               spectators (sprites) of the stage
│       └── stage.json                    music, ROM addresses, position and order of the animations
├── screens/            hud.png, title_logo.png, select_*.png, hiscore_ranking.png, ending_*.png, test_*.png
│   ├── tiles/            8×8 tiles used by each screen, coloured, ROM order
│   ├── faces/            small select / hi-score faces (<fighter>_p1.png, _p2.png)
│   └── glyphs/           tile blocks: fonts, STAGE, FIGHT!, GAME OVER, kanji names, big digits
│                         (`_nocolour` = colour chosen case by case by the code, left in grayscale)
├── tiles/
└── palettes/
```

Samples keep their slot number in the OKI chip; the game plays them with sound command `0x80 + number`
(listed in `index.json`). Missing numbers are "blank" slots (5 ms of silence) separating the sample groups
(one group per fighter). Samples 100 to 104 are the music's percussion.

## How it works (DBZ 1993)

Everything was found by reading the MAME driver (`src/mame/konami/dbz.cpp`) and disassembling the 68000 and Z80 programs.

**Sound.** The sound board is a Z80 + YM2151 + OKI M6295. The 68000 sends one byte to the Z80 (latch + NMI).
- `0x80–0xFF`: plays OKI sample `cmd & 0x7F`. **Every voice and sound effect of the game goes through this.**
- `0x01–0x10`: FM music (the game uses `0x0B–0x11`). `0x11` = stop.
- `0x12–0x7F`: never sent by the game; note sequences without instruments (silent on their own). Can be recorded with `--commands 0x12-0x7f` out of curiosity.

For the music, the script **emulates the Z80** (pure Python emulator included, `dbz_arcade_rip/z80.py`) with the YM2151
timers, logs every write to the YM2151 and the OKI, then writes a VGM (with the OKI ROM included, so the percussion plays).
Looping tracks get a **native VGM loop**: the file holds the intro then the loop once, and the player repeats it forever,
like the arcade board. The loop point is found when the sound driver comes back to a state already seen (Z80 RAM +
YM2151 registers), then moved back as long as the music played is identical.
The jingles (`0x0c`–`0x0e`) end normally. Details are in `sounds_index.json`.

**Sprites.** The sprite ROM (K053246/K053247) holds 16×16 4 bpp tiles; a W×H hardware sprite addresses its sub-tiles
in Morton (Z) order. Frames are described in the 68000 program:

- fighter table at `0x5AEE` (10 × 32 bytes: normal frame bank at +4, special-move bank at +0x14);
- a bank starts with a table of long pointers (high byte = number of pieces);
- a frame = 1 header word + N × 3 words: `tile code`, `X | flipX<<13 | log2(width)<<14`, `Y | flipY<<13 | log2(height)<<14`
  (centre coordinates, Y upwards), routine `0x801C`;
- player palettes: table `0x1F856`, entry `20 + 2×fighter` (P1) and `21 + 2×fighter` (P2), 16 xRGB555 colours.

**Fighter palettes (v0–v3).** For each player, the game loads 4 consecutive palettes from the `0x1F856` table pointer
(routine `0x5CAC`). Use found in the code:
v0 = the fighter; v1 = most of their effects (auras, sparks: relative colour +1, table `0xB1E0` and object scripts);
v2 = a few effects (+2) and the **Kaioken** of Goku / SSJ Goku (command `0x6?02` in their animation scripts,
6 animations); v3 = no use found.

**Sprite colours.** Through the K053251, a sprite uses palette `colour & 0x1F` of the first palette block. In a fight
(routine `0x5CAC`): 0–3 = P1 fighter, 4–7 = P2 fighter, 8–19 = shared stage palettes (table `0x2056E`, indexed by the
stage number at `0x486434`). Portraits are made of two layers (palettes 0 and 1 of the select-screen pair).
Spectators come from table `0xCEAA` (per stage).

**Stages.** Table `0xB7D00` (16 bytes per stage): compressed maps of the two K053936 rotate/zoom layers (64×32 cells
of 16×16, RLE on long words, decompressor at `0x5C72`); palettes at `0x21D18`. Tile animations: table `0xD0D44`
(per stage, 18-byte records: layer, x, y, size, timing group, frame list), applied by routine `0x5136`.

**Fixed screens.** K056832 chip (pages of 64×32 8×8 tiles). Same compressed maps (routine `0x5C3A`); register
`0x4CC033` selects the page written, which sets the layer and therefore the palette block (192+ or 224+). Each screen
routine loads its palette right next to its map. Endings: tables `0xA9C1C` (JP) / `0xA9C6C` (EN), palettes `0x1EBBC`.

**Samples.** Standard OKI table at the start of the ROM (127 entries of 8 bytes), 4-bit OKI ADPCM at 8 kHz (1.056 MHz clock, pin 7 high).

## Known limitations (DBZ 1993)

- Frieza exists as two fighters: `frieza_stage1` fights with his arms crossed (no hands, as in the anime) during
  "STAGE-1"; from "STAGE-2" on, the game replaces him with `frieza_stage2`, in a real fighting stance (code `0x3086`,
  counter `0x48648A`; at the same time stage 6 becomes stage 8).
- The two layers of a stage are delivered separately: in game they scroll and zoom independently.
- Shared effects are exported with stage 0's palettes (the other stages are in `shared_palettes_by_stage.png`).
- Fixed screens are exported as stored: a whole 512×256 page. The arcade board only shows the left 384×256;
  the right part may hold tiles never visible in game (e.g. a grey strip on Gohan's ending).
- Animation scripts (frame order and timing) are not decoded (not needed for sheets).
- At the loop point, the YM2151's internal LFO is not reset (same as on the arcade board): the second pass may differ
  very slightly from the first; this is inherent to the chip.

## Dragon Ball Z 2 Super Battle

Same team, same board, same sound driver: `python dbz_arcade_rip.py dbz2.zip` (MAME set `dbz2`; the bootleg's
`dbz2bl/` folder in a merged zip is ignored). The same targets exist:

| Target | What you get |
|---|---|
| `samples` | 88 OKI samples as **VGM** (voices and sound effects; samples 100–116 except 113 are the music's percussion) |
| `music` | The **19 tracks/jingles** (commands `0x01–0x13`) as **VGM** with native loop |
| `sprites` | The **416 frames** of each of the 10 fighters (SSJ Goku, Gohan, Vegeta, Trunks, Mr. Satan, Piccolo, No.20, No.18, No.16, Cell) with their **4 colour sets**; the shared sprite bank (832 frames: effects, ROUND/FIGHT!/WIN texts, select screen, stage and ending props…) sorted by where the game shows it |
| `stages` | One folder per stage (**22**: the 10 stages + their round variants + the final stage) with its **2 views** (ground / sky), both zoom layers, the tile **animations**, the **sprites placed on the stage** (crowd, birds, clouds…), the tiles used |
| `screens` | Every other tilemap, **named**: `ending_<fighter>_NN` (ending pictures and texts, NN = order of appearance, `_jp`/`_en` for texts), `ending_common_NN` (shared by several endings), `quote_<fighter>_NN_jp/_en` (quotes), `quote_window_*`, `select_background_*`, `hiscore_*`, `difficulty_select_*`, `congratulations_easy/normal/hard`, `a_challenger_shows_up`, logos, test mode, HUD… |
| `rawsprites`, `tiles`, `palettes` | Same as for the first game |

```
dbz2_rip/
├── samples/  music/  sounds_index.json
├── sprites/
│   ├── characters/00_goku/ … 09_cell/
│   │   ├── sheet_colour1.png … sheet_colour4.png   full sheet, one file per colour set
│   │   ├── frames/000.png …                       one frame per file (colour set 1)
│   │   ├── palettes.png                           4 sets × 8 palettes
│   │   └── frames.json
│   └── common/                    shared sprite bank (not the fighters' moves: those are in characters/)
│       ├── effects_<fighter>/     effects seen thrown by that fighter only (its colours)
│       ├── effects_shared/        effects seen with several fighters: one sheet per fighter
│       ├── fight/                 ROUND, FIGHT!, WIN, 1P WIN, TIME BONUS, PUSH START, Satan statues…
│       ├── select_screen/         names, faces, cursors of the select screen
│       ├── stageNN/               props placed on the stage (crowd, birds, cars, dinosaurs…)
│       ├── ending_<fighter>/      sprites seen during that fighter's ending
│       ├── unknown/               never seen during emulation: grayscale
│       └── common.json            frame → ROM address, colour and where it comes from
├── stages/stage00/ … stage21/
│   ├── ground_back.png, ground_front.png, sky_back.png, sky_front.png   (1024×512)
│   ├── tiles_<view>_<layer>.png
│   ├── animations/<view>_<k>/ 00.png… + sheet.png
│   ├── sprites/<view>_<k>/    sprites placed on the stage
│   └── stage.json             rounds using it, music, map codes, palettes, animation timing
└── screens/
    ├── fixed_layer/        fixed 8×8 tile layer (K056832 chip): texts, HUD, menus, pictures
    ├── zoom_layer_back/    back rotate/zoom layer (K053936 "PSAC" chip)
    ├── zoom_layer_front/   front rotate/zoom layer
    │                       files NNN_name.png (NNN = map number in the game) + tiles/
    └── screens.json
```

DBZ2 fighter PNGs have **128 colours** (8 palettes of 16): each piece of a frame picks its own palette
(body, hair, effects…). Pixel index = `palette × 16 + colour`, and colour 0 of every palette is transparent.

### How it works (DBZ2)

- **Fighters**: table `0x59AC` (10 × 32 bytes, frame bank at +4, 416 entries). A frame = 1 header word then
  **8-byte** pieces: attributes (size, flips), **colour offset** (0–7), tile code, Y, X (routine `0x854A`).
  A word with bit 15 clear starts a second group of pieces (aura / attached effect, drawn with its own priority).
- **Colours**: 4 sets of 8 palettes per fighter, table `0x4FB38` (routine `0x5AEC`); the set is chosen on the select
  screen (variables `0x48768C`/`0x48768E`), a mirror match forces a different one. In a fight, sprite palettes:
  0–7 P1, 8–15 P2, 16–21 common (`0x4F5A0`), 22–24 stage (`0x4F640`).
- **Maps**: `trap #15` (`0x150A`) loads a map by code `type << 14 | number` through `0x529A8` (type 0 = K056832,
  1 = back zoom layer, 2 = front zoom layer); every call is followed by a `trap #12` (`0x1498`, table `0x540FC`)
  with **the same code** for the palette. A map is a whole page (64×32) or a **patch** (x, y, width) drawn over a page;
  same RLE as DBZ1.
- **Stages**: `0x44C2` gives the stage loaded for each base stage and round (some stages change palette or scenery
  between rounds); `0x540C` gives the maps of both views ("ground" in rounds 1 and 3, "sky" in rounds 2 and 4,
  variable `0x487768`); animations `0x4C678`; stage sprites `0x10CD4`; music = command `0x01 + base stage`.
- **Objects**: scripts `0x10F36` (interpreter `0xCC40`).
- **Screen names**: endings, quotes, select background and logos come from the program's tables (ending scripts
  `0x569C8`, quotes `0xFD2E`/`0xFF5E`…); the others (`sky_day`, `wasteland`, `shenron_*`, `clouds_night_*`…) are named
  after what they show. A single map (`fixed_layer/030`) has no name.

### DBZ2 shared sprite colours: how they were found

Unlike the first game, the colour of the shared-bank sprites is almost never written in a table: it depends on who
draws the sprite (the fighter throwing the effect, the select screen, a cut-scene…). To avoid guessing, I **ran the
game's 68000 program** in an emulator (attract mode, select screen, fights with thousands of random inputs, the 10
endings, in English and Japanese) and recorded, for every frame drawn, which palette the colour RAM held at that moment,
then found that palette in the ROM. The result is the table `dbz_arcade_rip/dbz2/objpal.py` (frame → ROM address of the
palette, or "fighter colour", plus where the frame was seen, which gives the folder names of `sprites/common/`).
The script itself stays 100% static: it reads the palettes from your ROM at those addresses.

About **440 frames out of 832** get their real colour this way. The others were never shown on screen during these
sessions (rare moves, exploding scenery pieces, Japanese versions of some texts…): they are delivered **in grayscale**
(`*_nocolour.png`, original 0–15 indices), like the uncoloured glyphs of the first game. `common.json` tells where each
frame's colour comes from.

### Known limitations (DBZ2)

- "Fighter colour" sheets use colour set 1 of the fighters using them.
- `effects_<fighter>` means "only seen with that fighter during my sessions": a rare effect of another fighter may
  never have shown up, so there can be a few misattributions. `fight` mixes the fight texts with a few fixed-colour
  sparks and explosions.
- `screens/` maps are coloured with the palette of the same number (as the game does); a few patches are meant to be
  drawn over another picture and are not very meaningful on their own.

## License

Project code: public domain ([Unlicense](https://unlicense.org/), see `LICENSE`). Do whatever you want with it.
