# lsnim-extract

Extractor for **Lucky Star: Net Idol Meister** (らき☆すた ネットアイドル・マイスター, PSP, `ULJM05542`).

It unpacks the data files of `PSP_GAME/USRDIR/DATA` and sorts what comes out into folders.
No game data is included here: you need your own copy of the game.

## Usage

Python 3 is enough to unpack the archives; numpy and Pillow are needed to convert the
images. Recent Linux distributions refuse `pip install` outside a virtual environment, so
create one first:

```bash
python3 -m venv venv
source venv/bin/activate               # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Then, with the files of this repository copied next to the game's data
(`PSP_GAME/USRDIR/DATA`):

```bash
python3 lsnim_extract.py . out         # every .cpk + lt.bin + pr.bin of the current folder
```

Or from anywhere else:

```bash
python3 lsnim_extract.py DATA_folder out          # the same, for another folder
python3 lsnim_extract.py vo.cpk out --sc sc.cpk   # one archive (vo.cpk needs sc.cpk for names)
python3 lsnim_extract.py pr.bin out
```

Option `-v` prints every file.

## Output

One folder per data file, then one folder per file type, then the categories:

```
out/
  sc/     sc/<category>/      the scripts, as stored
          txt/<category>/     their decoded text
  vo/     ahx_encrypted/<category>/sc00000/     the voices, one folder per script
          voices.csv          every voice line: ID, name, speaker and spoken text
  union/  adx/  ahx_encrypted/  acx/  png/  gim-converted-to-png/  bin-dummy/
  lt/     png/lt.png
  pr/     png/00.png ... 29.png
```

Each archive folder also gets a `files.csv`: every file ID, its sizes, its detected format
and the file(s) it was written as.

## What is extracted, what is converted

Files are written as they are stored. A file is only converted when no existing tool can
read it:

| Data | Written as | Why |
|---|---|---|
| ADX / AHX audio | `.adx` / `.ahx`, untouched | playable with [vgmstream](https://vgmstream.org) |
| ACX holding ADX | `.acx`, untouched | playable with vgmstream |
| ACX holding AHX | split into `.ahx` streams, each playable with vgmstream | vgmstream cannot open the ACX container itself |
| Images (game format) | `.png` | format specific to this game |
| GIM images | `.png` + the original `.gim` (in `gim-converted-to-png/`) | standard PSP format, kept for reference |
| Fonts | `.png` glyph sheet | raw 2-bit glyphs |
| Scripts | `.sc`, untouched, + decoded `.txt` | text is stored as glyph numbers |

Full-screen pictures keep their 512x272 texture size, although the PSP only shows the
left 480 pixels. Use an external tool such as ImageMagick to crop them.

## The data files

The game uses CRI middleware. The CPK archives hold no file names, only numeric IDs, so
every name below was added by this tool (see [Names](#names)).

### sc.cpk — 596 scripts

| IDs | Folder | Content |
|---|---|---|
| 00000–00018 | `prologue/<unit>/` | first scene of each of the 19 units |
| 00019–00460 | `pv-haishin/chrNN_<name>/` | PV配信 scenes, per character |
| 00461–00522 | `pv-haishin/unitNN_<name>/` | PV配信 scenes, per unit |
| 00523–00579 | `endings/<unit>/` | 3 endings per unit |
| 00580–00592 | `story/` | story told by 鳥工作; 00580 opens a new game |
| 00593–00594 | `minigame/` | texts shown after the ファン暴走 mini-game |
| 00595 | `local-audition/` | quiz database: 1800 questions, 9 categories of 200 |

`<unit>` is `chrNN_<name>` for a single character or `unitNN_<name>` for a group.

### vo.cpk — 23,487 voice lines

One AHX per voiced line, in script order. Files are named after the line they belong to
and sorted like the scripts, one folder per script:

```
ahx_encrypted/prologue/chr00_konata/sc00000/sc00000_msg0001_chr00_konata.ahx
                                            │       │       │     └ name of the character, when it is a known one
                                            │       │       └ character number stored in the script
                                            │       └ message number stored in the script
                                            └ script 00000 of sc.cpk
```

### union.cpk — 3,256 files

| IDs | Folder | Content |
|---|---|---|
| 00000–00044 | `adx/bgm/` | music |
| 00045–00067 | `adx/voice-training/` | singing voices of that mini-game, one per character |
| 00068–00242 | `adx/se/` | sound effects, with the number the scripts use |
| 00243–00250 | `adx/ambient/` | looping ambience |
| 00251–00450 | `ahx_encrypted/local-audition/` | one voice per question of the モノマネ大会 quiz category |
| 00451–00910 | `ahx_encrypted/system-voices/<situation>/` | 20 situations x 23 characters |
| 00911 | `ahx_encrypted/story/` | narration of the game intro |
| 00912–01236 | `png/album-kanshou/` | event CGs, named `<album rank>-<id>.png` |
| 01237–01463 | `png/bg/` | backgrounds |
| 01464–02925 | `png/tachie/<character>/` | character sprites |
| 02926–02962 | `png/<screen>/` | interface screens |
| 02963–03238 | `png/minigame/<mini-game>/`, `acx/minigame-sfx/`, `ahx/minigame-voices/<mini-game>/chrNN_<name>/` | mini-games: images, sound effects, per-character voices |
| 03239–03247 | `png/<screen>/` | interface screens |
| 03248–03255 | `png/minigame/<mini-game>/` | 8 GIM previews of the mini-game menu |

### lt.bin and pr.bin

Two files that are not archives; the game loads each one whole.

- `lt.bin`: the game font, 3,650 glyphs of 20x18 pixels.
- `pr.bin`: 30 images (system texts, buttons, text boxes, town map, menus) and their
  31 palettes. The file has no table of contents: the offsets are in the game executable.

## Formats

- **CPK**: CRI archive, files listed by ID (`ITOC`), compressed with CRILAYLA.
- **Images**: palettes first (256 RGBA colours, or 16 padded to 0x100 bytes), then blocks of
  gzip tiles holding palette indices in PSP "swizzled" order. Neither the size nor the bit
  depth is stored; the tool finds the width by trying powers of two.
- **Character sprites**: a `MAP` chunk gives the position of the 32x16 cells of the body;
  the body is rebuilt from it, the two faces are written above it.
- **Scripts**: little-endian 16-bit words. Text is a list of glyph numbers into `lt.bin`,
  not Shift-JIS; commands are words from `0xFF00` up.

The details are in the comments of each module.

## Code

| File | Content |
|---|---|
| `lsnim/cpk.py` | CPK archives, `@UTF` tables, CRILAYLA |
| `lsnim/audio.py` | file type detection, ACX |
| `lsnim/images.py` | game images, fonts, sprites, GIM |
| `lsnim/scripts.py` | scripts, quiz database, voice names |
| `lsnim/loose.py` | `lt.bin` and `pr.bin` |
| `lsnim/tables.py` | data only: sorting tables, names, tables copied from the executable |
| `lsnim/extract.py` | extraction and command line |

## Names

The game stores no file name, so every folder and file name is ours. Output names use
ASCII only, to stay easy to type and to script:

- names shown by the game are written in **romaji** (Hepburn, long vowels spelled out:
  `kou`, `soujirou`), and loanwords in **English** (`voice-training`, `minigame`);
- the categories we made up are in English: `prologue`, `endings`, `story`, `bgm`, `se`,
  `system-voices`, `tachie`…
- numbers in file names are the original IDs, or numbers stored in the scripts (`msg`,
  `chr`). `unitNN` and the `Q` of quiz questions are ours.

| In the output | In the game |
|---|---|
| `konata`, `kagami`, `tsukasa`, `miyuki` | こなた, かがみ, つかさ, みゆき |
| `misao`, `ayano`, `kou`, `yamato` | みさお, あやの, こう, やまと |
| `yutaka`, `minami`, `hiyori`, `patty` | ゆたか, みなみ, ひより, パティ |
| `akira`, `hikage`, `hinata`, `yui` | あきら, ひかげ, ひなた, ゆい |
| `nanako`, `hikaru`, `fuyuki`, `soujirou` | ななこ, ひかる, ふゆき, そうじろう |
| `yukari`, `minami-no-haha`, `cherry` | ゆかり, みなみの母, チェリー |
| `kanata`, `anizawa`, `takahashi`, `tori-kousaku`, `miku` | かなた, 兄沢, 高橋社長, 鳥工作, ミク |
| `misao-ayano` and the other duos | みさお & あやの… |
| `main-chara-4nin`, `u-18`, `adult-only` | メインキャラは4人, U-18, Adult Only |
| `pv-haishin` | PV配信 |
| `minigame` | ミニゲーム |
| `local-audition`, `net-idol-audition` | ローカルオーディション, ネットアイドルオーディション |
| `akushukai`, `blog-enjou`, `omikoshi-wasshoi` | 握手会, ブログ炎上, お神輿わっしょい |
| `fan-bousou`, `mega-konatan` | ファン暴走, メガコナタン |
| `voice-training`, `gravure-satsuei`, `dance-lesson` | ボイストレーニング, グラビア撮影, ダンスレッスン |
| `album-kanshou` | アルバム鑑賞 |
| `idol-sentaku`, `idol-dendou` | iDOL☆選択, アイドル殿堂 |
| `lucky-pon`, `wagon-sale`, `izumi-ke`, `costume` | らっきーぽん, ワゴンセール, 泉家, コスチューム |
| `save`, `load`, `install` | セーブ, ロード, インストール |

Voice files of minor speakers only get their character number (`chr27`); the speaker name
shown by the game is in `voices.csv`.

The sorting was checked by playing the game: the unit names and their members, which
unit each prologue, ending and PV配信 scene belongs to, the quiz voices, the intro
narration, the interface screens and the mini-games.

Not known: which of the 3 endings of a unit is the good, normal or bad one, and what makes
the game show the `story` scripts 00581–00592.

## Legal

This repository contains only code and tables describing the layout of the game's files.
It contains no asset, no script text and no executable code from the game.
