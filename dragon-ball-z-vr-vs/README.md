# dbzvrvs_rip — asset ripper for Dragon Ball Z: V.R.V.S. (Sega System 32, 1994)

Takes the MAME `dbzvrvs.zip` ROM set and extracts sprites, backgrounds, music, sound effects and voices.
The audio folders follow the tables of the game's sound driver (`tableN-<content>`), so every file says where it
comes from.

## Usage

```
python3 dbzvrvs_rip.py dbzvrvs.zip output_folder
```

To extract only some parts, add any of `sprites`, `backgrounds`, `music`, `sounds` (tables 2/4/6, instruments, unused):

```
python3 dbzvrvs_rip.py dbzvrvs.zip output_folder sprites music
```

The full run takes about one minute.

### Requirements
- Python 3.8+ with `numpy` and `Pillow` (`pip install numpy pillow`)
- A C compiler (`gcc` or `clang`) for music and sound commands. The script compiles the sound-board emulator
  `dbzvrvs/s32snd/s32snd.c` automatically (Linux: `build-essential`, macOS: `xcode-select --install`, Windows: MSYS2/MinGW or WSL).
  Without a compiler, sprites and backgrounds are still extracted, and the PCM samples are written unsorted
  (`samples-unsorted/`), since sorting them needs the sound commands to be run.

### Code layout

| File | Role |
|---|---|
| `dbzvrvs_rip.py` | command line: loads the zip, runs each part |
| `dbzvrvs/romset.py` | ROM list with CRCs, zip loading, program and sound memory regions |
| `dbzvrvs/sprites.py` | sprite table, animation records, palettes (normal and alternate), sprite PNGs |
| `dbzvrvs/tilemaps.py` | tile-layer screens, scripts outside the table, unused tiles, text layer and fonts |
| `dbzvrvs/soundboard.py` | builds and runs the sound-board emulator, VGM/WAV helpers |
| `dbzvrvs/pcm.py` | PCM sample table, playback rates, `.raw` + vgmstream files, voice lines rebuilt from samples |
| `dbzvrvs/sounds.py` | music (table 1) and sound commands (tables 2/4/6) exported by table |
| `dbzvrvs/dialogues.py` | table 6: when each dialogue is played, who says each line, the folder's README |
| `dbzvrvs/audit.py` | `coverage.txt` |
| `dbzvrvs/s32snd/` | the sound-board emulator in C (`s32snd.c`) and its Z80 core (`z80.c`, MIT licence) |

Why a compiler: music and sound effects are not stored as audio. They are sequences that the Z80 sound CPU plays
in real time on the FM and PCM chips, so they can only be captured by running that program. A Z80 written in Python
would take hours; in C it takes seconds.

## Output

| Folder | Contents |
|---|---|
| `sprites/<group>/NNNN_<name>.png` | 2114 sprites, RGBA with the in-game palette and transparent background |
| `sprites/_sheets/<group>.png` | one sheet per group (gok, veg, han, pic, tra, ozz, hij, eff, title, …) |
| `sprites/<group>_alt/NNNN_<name>.png`, `_sheets/<group>_alt.png` | the 756 fighter sprites in the alternate palette the game gives the second player of a mirror match (orange Goku, blue Gohan, green Trunks, green Vegeta, pink Piccolo; Ozotto has none) |
| `sprites/_palettes.png`, `fighter_palettes.json` | each fighter's palettes: 4 normal, 4 alternate, 1 special (one row per fighter: Goku, Gohan, Trunks, Vegeta, Piccolo, Ozotto) |
| `sprites/sprites.json` | index, developer name, size, bpp, colour bank, palette source |
| `backgrounds/screen_SSSSS_pageNN.png` | tile-layer screens: stage backgrounds, Ozotto's defeat cut-scene, ROUND 1/2/3, GAME OVER, speech bubbles (RGBA, one image per layer page) |
| `backgrounds/patch_SSSSS_pageNN.png` | tile-layer scripts the code runs directly (outside the screen table): partial updates drawn over a screen, e.g. the frame of the WARNING screen and animated cloud steps |
| `backgrounds/unused_tiles.png` | the 107 tiles no script places (top rows of stage pictures), one row per run of consecutive tiles; palette guessed from the nearest used tile |
| `backgrounds/text_warning_greyscale.png` | the pre-title WARNING screen (text layer), greyscale: see limitations |
| `backgrounds/text_layer_characters.png` | the 512 characters of the text layer after the game's font set-up (fonts, gauges, HUD pieces), greyscale |
| `backgrounds/text_font_1bpp_A9ED6.png` | the 1bpp font with drop shadow, as the game expands it (most of it is later overwritten in character RAM), greyscale |
| `backgrounds/backgrounds.json`, `_sheet.png` | script/page of each image (duplicates listed with `same_as`), and an overview sheet |
| `table1-music/t1_NNN.vgz` | the 27 music commands (`t1_000` = Track 01), VGM 1.71 (2× YM3438 + RF5C68), loop point set, GD3 tag |
| `table1-instruments/sample_NNN.raw` | the 27 samples only the music plays (drum kit, instruments); Sound Resource does not take these |
| `table1-voice-samples/sample_NNN.raw` | 12 voice samples the music plays on their own (Track 27, the credits, `t1_026`) that no command plays alone; `README.txt` in the folder lists the lines each one is also part of |
| `table2-sfx/t2_NNN.raw` | sound effects: one file per command, exactly what the command plays |
| `table4-voices/t4_NNN.raw` | voice lines: one complete line per command |
| `table6-dialogues/t6_line_NNN-NNN.raw` | dialogue lines (fight intros, win quotes). A table 6 command chains two lines; a line comes back in several commands (e.g. Goku's 042+043 in `t6_006`…`t6_010`), so each is written once and named after the samples it is made of; `table6.json` gives the lines of every command |
| `table6-dialogues/README.txt` | what the numbers in the names mean, who says each line and when the game plays it |
| `table6-voice-samples/sample_NNN.raw` | each voice sample the table 6 lines are made of, on its own (copies of the pieces, for reference) |
| `unused/` | PCM data nothing plays: `sample_001` (in the sample table, never started) and 3 `unreferenced_*` blocks no table points to |
| `tableN-*/tableN.json` | every command of the table: the file(s) holding its sound, the samples it starts, their rate. A command whose sound is identical to one already written points to that file instead of a copy; `same_as` = the table gives it the same sound data as another command |
| `samples.json` | every PCM sample: ROM offset, size, rate, `role` (sfx, voice, instrument, never played, unreferenced data), what plays it (`played_by`), its own file if the game plays it alone (`file`), the files it is heard in (`heard_in`) |
| `.raw.txth`, `.names.txt` (in each folder) | vgmstream description of the `.raw` files: codec and per-file sample rate |

### Players
- **`.vgz`** (music): the files use two YM3438 chips plus an RF5C68, so they need a libvgm/VGMPlay-based player:
  VGMPlay, foobar2000 with the **foo_input_vgm** component, Winamp **in_vgm**, or `vgm2wav` from libvgm.
  Game Music Emu (and players built on it) only handles basic Mega Drive/Master System VGMs and will not play these
  correctly.
- **`.raw`** (sound effects, voices, samples): **vgmstream** (foobar2000 component, Winamp plugin or `vgmstream-cli`), through the
  `.raw.txth` file in the same folder. Keep `.raw.txth` and `.names.txt` next to the samples: they start with a dot,
  so Linux and macOS hide them by default.

Sprite groups use the developers' prefixes: `gok` Goku, `veg` Vegeta, `han` Gohan, `pic` Piccolo, `tra` Trunks,
`ozz` Ozotto, `hij` bonus-stage characters, `eff` effects.

## Technical notes

### Sprites
- **Descriptor table:** 0x000300 in the V60 program (`epr-16543` + `epr-16542a`), 2116 × 16 bytes:
  width, height and address bits 16-19, bank bits, low address in 32-bit words.
- **Names:** 0x02B246, 2115 pointers to developer names.
- **Sprite ROM:** rebuilt like MAME's `ROM_LOAD64_WORD`: 4 ROMs interleaved by 16-bit words, in two 8 MB halves.
- **8bpp detection:** the address gap to the next descriptor is `h·ceil(w/4)` words instead of `h·ceil(w/8)`. This finds 35 images.
- **Palettes:** 16-word palettes in the alternate System 32 colour format `xBGRBBBBGGGGRRRR`, where the R/G/B
  least-significant bits are in bits 12-14. Word 0 is `ffff` (the transparent slot). One palette = one colour bank.
  A sprite object holds a palette id (= colour bank << 4, e.g. 0xE52); the palette allocator at 0x9ACEE copies
  its 16 colours straight from ROM into a free bank of palette RAM: `0xAE3DA + 2·id` for ids below 0x1800,
  `0xAD3DA + 2·id` above (so banks 0x200–0x368 = `0xB13DA + 32·(bank − 0x200)`).
- **Fighter palettes:** the routine 0x84639 takes each fighter's palette ids from three tables of pointers indexed
  by character (0 Goku, 1 Gohan, 2 Trunks, 3 Vegeta, 4 Piccolo, 5 Ozotto), 4 ids each: 0x87851 normal, 0x87869
  alternate (when the per-player byte 1/11 of work RAM is 0: the second player of a mirror match), 0x87881 special
  (object flags 0x6E and 0x72 set; not exported as images). Sprites whose colour bank is one of a fighter's normal
  banks are also exported with the matching alternate bank.

- **Sprite → palette:** the colour bank comes from the 16-byte animation-frame records at 0x8740–0x2B240:
  `[sprite, attributes, dx, dy, ?, colour bank, 0, 0]`. Examples: Goku 0xDF, Vegeta 0xE5, Gohan 0xE2, Trunks 0xE8,
  Piccolo 0xD5, Ozotto 0xD8. `palette_source` in `sprites.json` says how each sprite got its palette:
  - `anim`: its most common bank in the animation records.
  - `family`: the sprite also appears with a rare bank (a flash or attract-mode palette, e.g. `gok_d_g_d1`); its
    character's usual palette is used instead.
  - `name:<sprite>`: no record uses the sprite; it takes the palette of the sprite with the most similar developer
    name (e.g. `jumpup_p_n4a` → `jumpup_p_m4c`).
  - `group hint:<group>`: a whole group no record uses, recoloured like another group (`icycle` → `ice2`).
  - `neighbour:<sprite>`: nothing better; palette of the nearest sprite index. **These 24 are guesses**
    (groups `doku`, `effstar`, `setuyaji`, `newhex`, `timewaku`, `dummy`).
- **Index 15:** handled as in MAME. If a sprite uses it only on the first or last pixel of a 32-bit word,
  it is a transparency / end-of-line code; otherwise it is a real colour.

### Tile layers (backgrounds)
- **Tiles:** `mpr-16545` / `mpr-16544` interleaved by bytes (MAME `ROM_LOAD16_BYTE`), 16384 tiles of 16×16 4bpp
  (MAME `bgcharlayout`).
- **Screens:** 8-byte headers at 0x25EB4–0x26083 in the program, `{script address | screen id << 24, video RAM destination}`,
  run by the routine at 0xA78D2. The screen id selects the tile bank (`id & 3`) and the palette set
  (table at 0xB551A: ROM source + word count, loaded at colour banks 0x180+).
- **Scripts:** a byte code interpreted at 0xA791B that writes tile entries into video RAM pages (32×16 tiles):
  bytes < 0x80 = dictionary entry, 0x80 = set position, 0x83/0xA7 = relative move, 0x86/0x89/0x8C = runs
  (same / +1 / −1), 0x8F = bytes with a fixed high byte, 0x92 = raw entries, 0x95 = raw entries added to the
  dictionary, 0x98 = clear pages, 0x9B/0x9E/0xA1/0xA4 = vertical runs, 0xAA = end.
- **Tile entry:** bits 0-12 tile, bit 14 flip X, bit 15 flip Y. Colour bank = palette set + `(entry >> 7) & 0x3F`
  (the mixer uses palette base 0x1800 and shift 3 for these layers).
- **Scripts outside the table:** the code also runs scripts directly: 0xA5AEC (WARNING screen, called at 0xA5BA9),
  0xAE0F4–0xAE310 (a 4-step animation cycled by 0x870EB through the tables 0x87282/0x87292), 0xAE21A/0xAE372
  (0x87147). They only rewrite part of a page, so they are exported as `patch_*` images, with the palette set of the
  screens that use the same tiles. Three of the animation steps only contain solid filler tiles and give no image.
- **Text layer:** 8×8 4bpp characters at 0x31C000. The routine 0xA9336 expands a 1bpp font (0xA9ED6, drop shadow
  in colour+1) and a 2bpp one (0xADBB6), then copies 9 blocks of 4bpp characters (0xAA2D5–0xADBD6).
- Each video RAM page is exported on its own: the game shows several layers on top of each other (e.g. Ozotto
  over the speed-line background) with scrolling, so a finished screen is a stack of these images.

### Sound
- **Driver:** the Z80 program (`epr-16541`) contains the whole sequencer.
- **Commands:** sent through shared RAM: `E700` = code, `E701` = table.
  - Table 0: stops and fades.
  - Table 1: 27 music tracks.
  - Table 2: sound effects (36 commands). Table 4: voice lines (146). Table 6: dialogues (78), two characters' lines chained.
  - Tables 3 / 5 / 7: the same commands for player 2. Run in the emulator, they start the same samples at the same
    rates, timing and pan as tables 2 / 4 / 6, so they are not exported (they would only be copies).
- **Music loops:** each track is a playlist of single-track MIDI-like parts. The loop is detected when the playlist jumps back
  to a position it has already played.
- **Emulator:** `dbzvrvs/s32snd/s32snd.c` emulates the Z80 together with the YM3438 timers, the sound IRQ controller and the ROM banking
  from MAME's `segas32.cpp`, and logs every chip write to VGM.
  PCM is streamed by the Z80 into RF5C68 RAM, so it appears in the VGM as RAM-write data blocks (type 0xC0).
- **PCM storage:** voices, SFX and instrument samples are raw 8-bit RF5C68 PCM (sign + 7-bit magnitude) in `mpr-16540/39/38`,
  each one terminated by `0xFF` and padded to a 256-byte page. The driver's sample table is at 0x7E51 in `epr-16541`
  (6 bytes per entry: bank high, bank low, start page, …).
  The playback rate is not stored with the sample: the sequence sets it through the FD register
  (voices: 704 → 11190 Hz). The rates the game uses are embedded in `dbzvrvs/pcm.py` (`PCM_STEPS`) and written to `.names.txt`.
  vgmstream's `PCM8_SB` codec decodes this format (same family as the Sega CD's RF5C164), so the samples are kept as-is
  instead of being converted to WAV.
- **Sound commands vs samples:** the ROMs only store PCM samples. A voice/SFX command is a short sequence that
  starts one or more of them on the RF5C68 with a rate, volume and pan. The script runs every command in the
  emulator, logs which sample starts when, at which rate and on which channel, and writes the result as one `.raw`
  rebuilt from the original bytes (see below). The game pans these sounds to the side of the player who triggered
  them; the files are mono, so pan is not kept. If a command ever mixed pieces at different rates or on several
  channels at once, it would be logged to VGM instead (`tN_NNN.vgz`); this game has none.

## Notes on the audio
- **Numbers in file names:** `tN_NNN` is the command number in table N of the sound driver; `sample_NNN` and the
  numbers in `t6_line_NNN-NNN` are the game's own sample numbers (position in the driver's sample table at 0x7E51
  in `epr-16541`): `t6_line_026-027` is the line made of samples 026 then 027. `samples.json` gives the ROM offset of
  each sample, and `table6-dialogues/README.txt` lists every line with who says it and when; each sample a line is made of is in
  `table6-voice-samples/`.
- **One file per command, no duplicates.** Each `t2_`/`t4_`/`t6_` file is exactly what that command plays.
  Identical audio is written once (tables processed in the order 2, 4, 6); the `tableN.json` of a command that
  reuses it points to the existing file. Tables 3/5/7 (player 2) play exactly the same as 2/4/6 and are not exported.
- **Voice lines are stored in pieces.** The ROM holds every piece of voice once (no two samples share data); many
  lines are split into phrases and names played one after the other with a pause (e.g. 三秒で塵にしてやるぜ = 090,
  ガキが = 088). The file of such a command is the original bytes of each piece placed at the moment the game starts
  it (silence = 0x80), all at the same native rate: lossless, nothing resampled. A piece is not written on its own
  unless the game plays it alone somewhere; `samples.json` lists the files it is heard in (`heard_in`).
- **A piece restarted on the same PCM channel cuts the previous one** (as the RF5C68 does): e.g. the charged
  かめはめ (`t4_109`) plays か, め, は, め every 0.7 s on one channel, each syllable cut by the next; the file keeps
  exactly that.
- **Rates come from the commands.** The same sample can be played at another rate than the music uses: the
  fight-start cymbal `t2_010` is sample 089 at 16276 Hz.
- **Instruments vs sound effects** are told apart by what plays them: a sample only the music starts is an
  instrument (`table1-instruments/`). 143 and 253 are only used by track 27 (`t1_026`); listening confirms they are instruments.
- **Track 27** (credits) plays character voices over the music. The VGM keeps them, since they are in the game's own
  sequence for that command. The 12 that no command plays alone are also written in `table1-voice-samples/`.
- **When the dialogues play:** the fight code sends table 6 commands from two places: the fight intro (0x82A43,
  table 0x830ED indexed by 6 × player 1's character + player 2's) and the end of the match (0x99436, tables 0x99535
  when player 1 won and 0x9957D when player 2 won). So command = 16 × A + B for the intro of A (1P) vs B (2P), and
  16 × winner + 6 + loser after the match (Ozotto's wins: 16 × loser + 12), with 0 Goku, 1 Gohan, 2 Trunks,
  3 Vegeta, 4 Piccolo, 5 Ozotto. `table6-dialogues/README.txt` and `table6.json` (`situation`) give it for every line and command;
  commands 013–015, 029–031, 045–047, 061–063 and 077 are never sent.
- **Who speaks:** at the intro the 1P character speaks first, except against Ozotto who always speaks first (seen
  in the game); at the end the winner speaks first, except when Ozotto wins (the loser first). With these rules
  every line gets one and the same speaker in all the commands that play it; `table6-dialogues/README.txt` and `speakers` in
  `table6.json` give it.
- **Dialogues** (table 6): the game stores no line, only samples. Each command is a small MIDI sequence: every
  sample is a note, the pauses are delta times, the first character's line is on MIDI channel 10 and the answer on
  channel 11. E.g. `t6_006` = channel 10: 042 043, channel 11: 044 045 046 047 048. The script writes one file per
  channel (= one line), each line once, named after its samples: `t6_line_042-043.raw`.
  Some lines come back in other commands with a pause 64 MIDI ticks (78 ms) longer or shorter between their
  pieces: the delta time stored in the sequence differs (e.g. 073 then 041: 640 ticks in `t6_001`, 704 in
  `t6_013`–`t6_016`), with no rule, the delays being set by hand per command. The line is the same samples, so it is
  written once, with the pauses most commands use; the 13 commands that use another pause are marked
  `pause_differs_from_file` in `table6.json`, and `starts_s` gives the start of every piece for each command.
  E.g. `t6_line_071-072.raw` = Majin Ozotto's まさか、この私が (ending), two samples on one channel.
- **Timing:** all pauses are multiples of 64 MIDI ticks (77.8 ms); the exact start of a piece moves by up to
  ~0.7 ms with the PCM streaming, so commands with the same pieces and the same pauses are treated as the same
  sound (the first one is written).
- **Unused:** sample 001 is in the driver's sample table but nothing starts it; the 3 `unreferenced_*` blocks are
  PCM data no table points to. The game gives them no rate; they are set to 14750 Hz, chosen by ear.
- Playback rates are the ones the sound driver sets (`fd_step`); the driver never changes the pitch of a voice
  while it plays.

## Coverage report
Every run ends with `coverage.txt`: for each ROM, the share of real data (filler excluded) that the extracted
files account for, plus the list of known gaps. With the MAME `dbzvrvs` set it reads:

- sprite ROM: 100% of the data in exported sprites (24 sprites with a guessed palette)
- tile ROM: 100% (98.9% placed by screen scripts, 107 tiles in `unused_tiles.png`)
- program data ROM (`epr-16543`): 99.5% of the non-filler bytes in identified structures (the rest: a 0x300-byte
  block before the sprite table and sparse flag tables, no graphics)
- PCM ROMs: 100% (samples in the table folders and `unused/`)
- sound program: 27/27 music commands, 33/33 musical parts

## Known limitations
- Sprites use their default palette, plus the fighters' alternate palette in the `<group>_alt/` folders. The special fighter palette
  (table 0x87881) and other flash palettes are only in `_palettes.png` / the palette ROM.
- 24 sprites have a guessed palette (`palette_source` = `neighbour:…`, see above). No animation record and no code
  refers to them (`effstar_hoshi`, `doku`, `setuyaji`, `timewaku`, `dummy`, `newhex`): they are unused in the game,
  so their real colours cannot be checked.
- The pre-title WARNING screen and the text-layer fonts are in **greyscale**. The WARNING screen is drawn on the
  text layer (strings at 0xA5874, `u16 position, colour, ASCII text`, printed by 0xA9599). The text layer reads
  palette banks 0x1C0 and up (mixer register 0x20 = 0x7F, set from the table at 0x80516; WARNING uses colours 0x1C0,
  0x1C1, 0x1C8), but no ROM table loads these banks and no code writing them was found, so the pens are drawn as a
  grey ramp.
- The 3 `unreferenced_*` PCM blocks lie between samples 143 and 253 (two track-27 instruments), and `sample_001`
  between instruments 000 and 002. Nothing plays them, so their rate is unknown: 14750 Hz was chosen by ear.
- Background layers are exported page by page, not combined into finished screens.

## Licence
This project is released under the Unlicense (public domain), except `dbzvrvs/s32snd/z80.c` and `z80.h`, the Z80
core by Nicolas Allemand, which stay under the MIT licence (`dbzvrvs/s32snd/LICENSE-z80.txt`, to be kept with them).

## Credits
- Z80 core: superzazu/z80 (MIT licence, see `dbzvrvs/s32snd/LICENSE-z80.txt`).
- Hardware details: MAME `segas32.cpp` and `rf5c68.cpp` (BSD-3-Clause, Aaron Giles, Olivier Galibert); the RF5C68
  model in `s32snd.c` follows the behaviour of `rf5c68.cpp`.
