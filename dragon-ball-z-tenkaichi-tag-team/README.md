# ttt-unpack

Extractor for `PSP_GAME/USRDIR/PACKFILE.BIN` of **Dragon Ball Z Tenkaichi Tag Team**
(PSP: Japanese release *Dragon Ball Tag VS* ULJS00311, US ULUS10537, EU ULES01456).

It unpacks every entry of the PACKFILE (14097 entries, with their nested archives) into
sorted folders and gives every file a descriptive name: characters, stages, voices by
line, effects, menus, story mode... How each format works is written in
[FORMATS.md](FORMATS.md).

Plain Python 3 (tested with 3.11, 3.12 and 3.13), no dependencies. You need your own copy of the game:
`PACKFILE.BIN` is in `PSP_GAME/USRDIR/` of the UMD image.

## Usage

```bash
python3 ttt_unpack.py PACKFILE.BIN                 # extracts to packfile_out/
python3 ttt_unpack.py PACKFILE.BIN out --txt --png  # to out/, with .txt and .png too
python3 ttt_unpack.py --help
```

Options: `--txt` (also write what the tool decodes as text: text tables, move lists, story scripts, camera moves and unlock lists as `.txt`, `character/character_stats.csv`; off by default), `--png` (also write one PNG sheet next to every image file: .tex, .rhg, .map, .fb; off by default), `--no-unpack` (keep archives as one `.pak`).

## Output

Entries are sorted by category, and entries the PACKFILE keeps side by side stay in the
same folder: a translated entry is stored 6 times in a row (jp, en, es, fr, de, it), so
the 6 copies sit together in the folder of their screen, the language at the end of
their name (`menu/free_battle/00024_free_battle_jp/` ... `00029_free_battle_it/`; `find
-name '*_fr*'` lists one language). An archive stays whole in its folder. Characters have their official names, as the
game shows them (`piccolo`, `frieza_final_form`, `super_buu_gohan_absorbed`...: tttpack/
official.py), and the abbreviations of the entry list (sm_, sfx_, rnd_, ex_...) are
replaced by words (`_sounds`, `_render`, `_portrait`, `_map_object`, `_fusion`, `_prop`...).
By default the output holds only the game's files. Files the tool derives (decoded text with `--txt`, PNG images with `--png`) are written next to the original.

```
packfile_out/
  unnamed.txt                        files that have no descriptive name yet, counted by folder
  index.csv                          every entry (all 14097; the empty ones have the type
                                     "empty" and no path, no file is written for them:
                                     e.g. 01430, the 4th costume slot of a character that
                                     has 3): index, offset, sizes, type, output path,
                                     internal name of the character it belongs to (GOKU_3...)
  audio/battle_voice/FFFFF_<character>/NNNNN_LLL_<line>.at3   battle voices, 70 x 126 lines
  audio/battle_common/               battle sounds / jingles stored as audio
  audio/battle_intro/NNNNN_LLL_<speaker>_with_<partner>.at3   pre-battle dialogue
                                     between the two characters of a tag team
  audio/story/epXX/NNNNN_LLL_<speaker>.at3   story mode lines of the 31 episodes
                                     (speakers checked by ear: tttpack/data/story_speakers.txt)
  audio/story/shared/FFFFF_<character>[_to_opponent|_to_partner]/   story lines shared by
                                     all episodes (lines to the opponent / to the partner)
  audio/title/                       title screen voices
  music/NNNNN_bgmXX_<name>.at3       21 music tracks (stereo, 44100 Hz)
  character/fighters/FFFFF_<character>/   a roster character: its 4 files (NNNNN_<character>_1..4:
                                     one costume each, with model, textures, animations,
                                     parameters, effects, interface) and its sound bank (_sounds)
                                     (FFFFF = first entry of its block, roster order)
  character/render/                  the 70 character renders (NNNNN_<character>_render)
  character/extra/                   fusion / Potara cut-scenes (_fusion), props of special
                                     moves (_prop: rock, golden dragon, ghosts, candy...),
                                     stored just before the characters (1389..1426)
  character/character_stats.csv      (--txt) one row per character: Blast 1 / Blast 2 / ultimate names,
                                     damage, guarded damage, Ki and Blast stock costs, ki blast
                                     damage, health, Ki, multipliers (see tttpack/params.py)
  stage/FFFFF_<stage>/               a battle stage: data, sound bank
  stage/backgrounds/                 14091..14095: backgrounds of 5 stages (kept apart, as
                                     the game stores them after the renders)
  battle/                            battle interface (13261..13266, 6 languages) and the
                                     battle sound bank (13267)
  story_mode/                        the Dragon Walker (story mode):
    scripts/                         chapter scripts (.bbq + their story as .txt; parts _2 / _3
                                     are board data), battle scripts (.gscf), other scripts;
                                     dragon_walker/13934_dragon_walker_script = the stage list (Stage00..32:
                                     ch00 = 13271..13273, ch01..ch31, credits = 13367..13369),
                                     if_01..if_10 (13370..13399) = 10 empty chapters it never
                                     launches (probably the "Stage01 if".."Stage31 if" it names);
                                     the developers' scripts, stored in the same block:
                                     13269 debug menu (unlock everything, clear stages, jump
                                     to any screen), 13268 battle test, 13400 mini-game test,
                                     13270 SYS_TEST (empty)
    board/                           the boards, pieces and objects on them
    minimaps/                        the mini-maps (14016..14019)
    chapter_texts/                   first text set (1193..1378): chapter texts, 6 languages
    texts/                           second text set (13734..13931): per language, common
                                     texts, the 31 chapters (with their scripts in the EU /
                                     US releases) and the credits
    sounds/                          sound banks of the boards and the common one
    portraits/                       faces of the dialogue boxes
    screens/                         frames and artwork of the screens, chapter titles,
                                     backgrounds of the stages in the story (13984..13993)
    dragon_walker/                   13932..13936, the story mode screen: its module (.elf),
                                     archive, script and two small scripts, like a menu screen
    tutorial/, effects/
    ui/                              menus and results, UI and game over (6 languages)
  menu/<screen>/                     a menu screen: its program module (_module.elf), archive
                                     and script (_script.bbq); screens: title (with the install data screen, 10, 11 and 15: the title module loads it),
                                     main, settings, free_battle, battle_selection (with
                                     battle_100, survival, score_rank), training, multiplayer,
                                     customize (with the 6 language copies of their archives).
                                     menu/ also holds the menu sound bank and
                                     10 sound effects stored as audio (ready, fight, finish,
                                     score...: the same sounds as audio/battle_common/04425..04434, kept
                                     twice as the game does)
  system/                            the 6 system archives (00000_system_jp .. 00005_system_it:
                                     interface texts, fonts, icons, game tables), boot screen
                                     (module, encrypted .pgd and the same decrypted:
                                     _decrypted.dat, logos, script)
  program/                           program modules (.elf) of no known screen
  padding/14096.padding              68 MiB of random bytes used by nothing: UMD filler
  other/                             anything else
```

Inside these folders:

```
  NNNNN_<name>/                      an archive, unpacked: NNNNN_KKK_<part name>.<type>
                                     (KKK = part number; sub-archives are sub-folders,
                                     e.g. character/fighters/01427_goku/01427_goku_1/01427_490_skill_001/)
  NNNNN_<name>.<type>                an entry that is a single file (bbq, gscf, tbl, elf...)
  ..._KKK.tex + .png                 texture: raw .tex plus (--png) one PNG (a file with several images
                                     or palettes gives one sheet with all of them side by side)
  ..._KKK.tbl + .txt                 text table: raw .tbl plus (--txt) the decoded text ("id<TAB>text",
                                     with the ids used by the scripts and parameter files;
                                     the button icons of the game font are written [○], [L], [Stick↑]...)
  ..._043_move_list_name.dat + .txt  character move list: raw .dat plus the moves with their
                                     inputs and costs, in the language of the release
                                     (_jp.txt, _en.txt... when the release has several)
  NNNNN_..._sounds/                  sound bank: one .vag per sample, NNNNN_SSS_<name>.vag
                                     (SSS = slot in the bank; the same ADPCM bytes with a VAG
                                     header, nothing re-encoded). Names: kastomd's lists for
                                     the characters' banks (hurt_1_normal, sonic_sway...) and
                                     the battle bank 13267; the others keep their slot only.
                                     A bank the game keeps alone in a sub-archive (menus,
                                     system) stays in that sub-archive's folder
  ..._KKK.mot                        animation (parts compressed with zlib are written decompressed)
  ..._KKK.map + .png                 stage / board geometry (signature 60 0B 9A 7E), raw, plus
                                     one PNG sheet of its textures (sky, ground, rocks, trees...);
                                     the geometry itself is not converted
  ..._KKK.rhg + .png                 2D interface graphics (portraits, digits, menu parts...),
                                     signature "RHG\0", plus one PNG sheet with all its images
  ..._KKK.ags                        animation of those graphics (signature "AGS\0"), kept raw
  ..._KKK.<type>                     other formats by signature (pmdl, cman, eedx, v000...)
```

The game names none of its files (the EBOOT holds no file name but PACKFILE.BIN), so
every extension is ours: from a signature when the file has one, otherwise from its
format (FORMATS.md):

```
  .fnt   font                         .lgt   stage lighting / ambient colour (64 bytes)
  .fxh   effect header                .wpt   stage waypoints (path graph)
  .fxs   settings of an effect item   .dbesl list of DBES meshes
  .fxc   colour table of an item      .unl   unlock list (system parts 28..35)
  .fxo   offsets of an effect         .dat   parameter and game tables (character
  .pak   an archive kept whole               parameters, AI, items...; as in the
         (--no-unpack)                       community's lists: 017_common_param.dat)
  NNNNN_chNN_1.bbq + .txt            Dragon Walker chapter script plus its story as text:
                                     "id<TAB>speaker<TAB>line", [message] boxes, [battle] lineups
                                     (in script order; parts _2 / _3 are map data)
  system/00008_boot_logos.fb + .png  raw 480x272 screens (boot logos), stored bottom-up
```

`NNNNN` is always the original entry index and always comes first in the file name
(`find packfile_out -name '04396*'` finds any entry), `LLL` is the line number inside its block.
Audio is raw ATRAC3 in the game; it is written as standard RIFF `.at3`
(playable with vgmstream or ffmpeg). Voices are mono 22050 Hz.
Sound effects are PSX ADPCM (mono, 11025 Hz) in libsndp `PPHD` banks, written as one
`.vag` per sample (the banks hold no sample names: the characters' and battle banks
get the names of kastomd's Editor_indice_Py).

## Names

Names come from the game data where it has them (effect headers, the sprite names
of the `.ags` animations, fonts...: FORMATS.md), else from the lists below; a file
with no name keeps its numbers and is listed in `unnamed.txt`.

Besides what the tool works out from the game code and data, file names carry the
community names of **Editor_indice_Py** by kastomd
(<https://github.com/kastomd/Editor_indice_Py>, Apache-2.0), whose lists are shipped
unchanged in `tttpack/data/editor_indice_py/` (see `NOTICE.txt` there):
PACKFILE entries (`character/fighters/01427_goku/01427_goku_1/`, `story_mode/13275_ch01_2.bbq`),
battle voice lines (`04441_000_intro_1.at3`), character archive parts (`01427_002_model.pmdl`,
`01427_082_jump_in.mot`). They were made on the US release, which has the same layout;
the tool converts their 1-based numbers. The number always stays first in every name.

## Format notes

How each format works: [FORMATS.md](FORMATS.md).


- Container: see `tttpack/packfile.py`. The PACKFILE has no file names.
- Menu flow: each screen script jumps to the next one by PACKFILE index (BBQ native 0 /
  native 1): boot 9 -> title 14 -> main 19 -> 13934 story, 33, 30, 63, 71, 54, 22; the
  debug menu 13269 lists them all with their names (names.MENU_SCREENS, names.UNNAMED).
- Dragon Walker scripts: every chNN_2 (and if_NN_2) carries the same compiled library of
  the board engine (player / enemy / motion / skill / debug menu strings), like every
  chNN_1 carries the dialogue functions: the copies are a side effect of the script
  compiler, not different engines.
- Story speakers: worked out at extraction time from the GSCF battle scripts
  (entries 13401..13568), see `tttpack/gscf.py` and `tttpack/story.py`.
- Audio layout: see `tttpack/audio_map.py`. The tables (character blocks, story episodes)
  come from the decrypted EBOOT; `tools/dump_eboot_tables.py EBOOT.BIN` checks them
  against your own copy (they are the same in the JP, US and EU releases).
- Releases: Japanese ULJS00311, US ULUS10537 and EU ULES01456 have the same 14097-entry
  layout. US / EU have per-language copies of menus, text and the battle_ui archive
  (en, es, fr; EU adds de, it) and English voices.

## Layout

```
ttt_unpack.py              entry point
tttpack/packfile.py        PACKFILE container
tttpack/formats.py         file type detection
tttpack/atrac3.py          ATRAC3 detection and RIFF header
tttpack/archive.py         nested archives -> folders
tttpack/texture.py         textures (4/8-bit palette, PSP swizzle) -> PNG
tttpack/rhg.py             RHG interface graphics -> PNG
tttpack/text.py            text tables, button icons of the font
tttpack/movelist.py        character move lists
tttpack/layout.py          output folder of each entry
tttpack/official.py        official character names (EU / US interface texts)
tttpack/bbq.py             BBQ stage scripts (VM instructions) -> story text
tttpack/params.py          character parameter files -> stats table (field offsets documented)
tttpack/gscf.py            GSCF event scripts (story battles)
tttpack/story.py           who says each story line
tttpack/intro.py           pre-battle dialogue pairs
tttpack/sound_bank.py      PPHD sound effect banks -> .vag
tttpack/effect.py          visual effect packages: names of their parts
tttpack/cman.py            camera moves (.cman) -> text
tttpack/unlocks.py         unlock lists of the system archive -> text
tttpack/identify.py        names found from the content of a part (fonts...)
tttpack/names.py           community names (Editor_indice_Py lists in tttpack/data/)
tttpack/audio_map.py       audio index -> category / character / episode
tttpack/extract.py         extraction and command line
tools/dump_eboot_tables.py check audio_map.py against EBOOT.BIN
tools/make_sample.py       small PACKFILE with a few entries only (to share / test them)
tools/dump_gscf.py         print the native calls of GSCF scripts
tools/compare_packfiles.py  compare two releases entry by entry (what differs, what only one has)
tools/compare_outputs.py   compare two extractions by their files, numbers and languages aside
tools/make_entry_list.py   write docs/entries_<game id>.csv: every entry and part of one
                           PACKFILE (name, type, offset, size), nothing extracted
tools/check_extraction.py  check that an extraction has every file of the list of its
                           release (docs/entries_<game id>.csv)
tests/test_tttpack.py      tests (synthetic data; optionally a real sample)
```

## Tests

```bash
python3 -m unittest discover tests                          # no game data needed
python3 tools/make_sample.py PACKFILE.BIN sample.bin 0 17 1427-1431 1004
TTT_SAMPLE=sample.bin python3 -m unittest discover tests    # also extract a real sample
```

The sample test fails if a file of the sample has no descriptive name (`unnamed.txt`).
