"""Extractor for Lucky Star: Net Idol Meister (PSP, ULJM05542).

Extracts the CRI CPK archives of PSP_GAME/USRDIR/DATA (sc.cpk, union.cpk, vo.cpk) and
the two loose graphics files of the same folder, lt.bin (font) and pr.bin (images).
Audio is written as is (ADX/AHX/ACX, playable with vgmstream), except the ACX that hold
AHX streams, which vgmstream cannot open: they are split into <id>_00.ahx, <id>_01.ahx...
CRILAYLA (the CPK compression) is undone, since it is part of the archive format.

What comes from the game and what does not:
  from the game  archive names (sc, vo, union), file IDs (ITOC index), message number,
                 character number, speaker name and text inside the scripts
  added by us    file extensions (CPK entries have no name or extension):
                   .adx / .ahx  official CRI format names, detected from the file header
                   .gim         standard PSP image, already converted: its frames are in png/,
                                the original is kept in gim-converted-to-png/ for reference
                   .acx         union: mini-game sound effects, in acx/ミニゲーム-sfx/<game>/
                                ACX of AHX (mini-game voices, one per character) are split
                                into ahx/ミニゲーム-voices/<game>/<id>-<name>/<id>_<track>.ahx
                   .sc          files of sc.cpk (dialogue scripts and the quiz table),
                                named after their archive, kept raw, sorted in folders
                                (prologue, PV配信 per character or unit, endings...)
                   .txt         decoded text of each .sc (sc/txt/, same folders)
                   .png         images of union.cpk: their format is specific to the game,
                                so they are converted (several images in one file give
                                <id>_00.png, <id>_01.png...); full-screen pictures (event
                                CGs, backgrounds) keep their 512x272 texture size: the PSP
                                screen shows the left 480 px, the 32 columns past x=480 are
                                padding (e.g. "magick in.png -crop 480x272+0+0 out.png");
                                union 03214 is a 16x16 font
                                (same character order as lt.bin), saved as a glyph sheet;
                                character sprites (tachi-e): one PNG, the 2 faces on top
                                (8 px apart) and the body rebuilt from its cells 8 px below,
                                with a hole where the face goes (face position not stored)
                   .bin         anything else not identified, as the developers named their
                                own raw data files (lt.bin, pr.bin, INST.BIN, SAVE.BIN)
                                bin-dummy/: empty placeholders (zeros), e.g. union 02927, 02935
                 union ADX folders adx/bgm, adx/se, adx/ボイストレーニング, adx/ambient, files named
                   by union index (sound effects: + script number, 068-se000)
                 folder names (= detected format, "_encrypted" when the ADX/AHX is encrypted)
                 the "msg" and "chr" labels in voice file names, voices.csv

lt.bin and pr.bin (not CPK, loaded whole by the game) are converted too:
  lt/png/lt.png      the game font: 3650 glyphs of 20x18 px, 2 bits per pixel, as a sheet
  pr/png/<nn>.png    the 30 images of pr.bin (system texts, buttons, text boxes, town map,
                     menus...); <nn> is the resource number the game code uses

Voice files of vo.cpk are named after the script line they belong to (needs sc.cpk) and
sorted like the scripts (prologue, PV配信, endings... see script_folder), one folder per script:
    ahx/prologue/chr00_こなた/sc00000/sc00000_msg0001_chr00_こなた.ahx
      sc00000 = file 00000 of sc.cpk (sc/sc/prologue/chr00_こなた/00000.sc)
      msg0001 = message number stored in that script
      chr00   = character number stored in that script (0 = こなた ... 31 = narration)
      こなた   = speaker name shown in the text box, stored in the script
vo/voices.csv lists the original vo.cpk ID, new name, speaker and spoken text.
Each archive also gets a files.csv: every file ID, its sizes (stored / decompressed), the
detected format and the file(s) it was written as.

Naming rule: what the game itself displays is kept in Japanese as displayed (characters,
units, mini-games, PV配信, らっきーぽん...); the categories we made up are in English
(prologue, endings, story, bgm, ui screens...).
Other archives keep their numeric IDs (the game stores no file names).

Needs numpy + Pillow to convert the images (pip install numpy pillow).

Usage:
  python3 lsnim_extract.py                                  # every .cpk + lt.bin, pr.bin of the current folder -> out/
  python3 lsnim_extract.py DATA_folder [output_folder]      # every .cpk + lt.bin, pr.bin of DATA_folder
  python3 lsnim_extract.py pr.bin [output_folder]           # a single file (lt.bin or pr.bin)
  python3 lsnim_extract.py vo.cpk [output_folder] --sc sc.cpk  # a single archive
  option: -v (print every file)
"""
