# File formats

How the game files work, for the formats the tool keeps as they are. All values are
little-endian unless written otherwise. The source files named in each section hold
the parsing code and more detail.

## PACKFILE.BIN — tttpack/packfile.py, tttpack/archive.py

`PSP_GAME/USRDIR/PACKFILE.BIN` holds the game data (the main program is `EBOOT.BIN`).

```
0x00  'PacK'
0x04  u32 entry count (14097 in every release)
0x10  count x 16 bytes:
        +0 position in 0x800-byte sectors, from the start of the data   XOR 'PacK' (0x4B636150)
        +4 size                                                         XOR entry index
        +8 compressed size (0 = stored)                                 XOR 'PacK'
        +C unknown                                                      XOR entry index
data: from the end of the table aligned to 0x1000
      (offset of an entry = data start + position x 0x800)
```

A compressed entry is a gzip stream of `compressed size` bytes that inflates to `size`
bytes. There are no file names: the game asks for entries by number, and the numbers
and roles are the same in JP, US and EU. A release leaves empty (size 0) the entries it
does not use (the US has no `_de` / `_it` entries, the US / EU no `_jp`). The names used
here are the community's (kastomd's Editor_indice_Py) or ours.

Many entries are archives, nested up to several levels (big-endian):

```
u32 count
(count + 1) x u32 offsets from the start of the archive; the last one = its size
parts at those offsets, aligned to 64 bytes (empty part: same offset as the next one)
```

A part can be compressed: u32 BE size, u32 BE compressed size, zlib stream, padding.
In an extraction, part K of entry N is `N_K_<name>` (and `N_K_M_<name>` one level
down). Every entry and part of each release, with its name, type, offset and size:
`docs/entries_ULJS00311.csv`, `docs/entries_ULUS10537.csv`, `docs/entries_ULES01456.csv`
(written by `tools/make_entry_list.py`; offsets of parts are inside their archive, after
decompression).

### Blocks of entries

| Entries | Count | Content |
|---|---|---|
| 0-5 | 6 | System archives, one per language (_jp .. _it): interface texts, fonts, icons, common effects, game tables |
| 6-9 | 4 | Boot screen: module (.elf), encrypted file (.pgd), logos (.fb), script |
| 10-15 | 6 | Title screen and install data screen: modules, archives, scripts |
| 16-19 | 4 | Main menu: module, archive, scripts |
| 20-22 | 3 | Settings: module, archive, script |
| 23-30 | 8 | Free battle: module, archive in 6 languages, script |
| 31-33 | 3 | Battle selection: module, archive, script |
| 34-39 | 6 | 100 Battles menu, 6 languages |
| 40-45 | 6 | Survival menu, 6 languages |
| 46 | 1 | Score / rank screen |
| 47-54 | 8 | Training: module, archive, archive in 6 languages, script |
| 55-63 | 9 | Multiplayer: module, archive, free battle archive in 6 languages, script |
| 64-71 | 8 | Customize: module, archive, archive in 6 languages, script |
| 72-73 | 2 | Menu box graphics, menu sound bank |
| 74-85 | 12 | Title screen voices (.at3) |
| 86-852 | 767 | Story lines shared by all episodes (.at3) |
| 853-1003 | 151 | Pre-battle dialogues of tag teams (.at3) |
| 1004-1139 | 136 | Story mode boards (sm_map_*) and the objects on them (sm_obj_*) |
| 1140-1172 | 33 | Story mode sound banks of the boards |
| 1173-1192 | 20 | Battle stages: archive (map_*) + sound bank (sfx_*) each |
| 1193-1378 | 186 | Story chapter texts, first set: 31 chapters x 6 languages |
| 1379-1388 | 10 | Menu voices (.at3) |
| 1389-1426 | 38 | Props of special moves (ex_char_*), fusion cut-scenes (ex_fus_*) |
| 1427-1776 | 350 | 70 characters x 5 entries: 4 costumes (archives) + sound bank |
| 1777-4389 | 2613 | Story mode lines of the 31 episodes (.at3) |
| 4390-4410 | 21 | Music, 21 tracks (.at3) |
| 4411-4440 | 30 | Battle sounds and jingles stored as audio (.at3) |
| 4441-13260 | 8820 | Battle voices: 70 characters x 126 lines (.at3) |
| 13261-13267 | 7 | Battle interface in 6 languages, battle sound bank |
| 13268-13570 | 303 | Scripts: test / debug scripts, story chapter scripts (.bbq, .gscf) |
| 13571-13642 | 72 | Story mode screens and frames |
| 13643-13733 | 91 | Story mode portraits |
| 13734-13931 | 198 | Story texts, second set: per language, common texts, 31 chapters, credits |
| 13932-13936 | 5 | Story mode screen (Dragon Walker): module, archive, scripts |
| 13937 | 1 | Story mode effects (.eedx) |
| 13938 | 1 | Story mode sound bank |
| 13939-13951 | 13 | Story mode interface and game over (6 languages), results |
| 13952-13993 | 42 | Story chapter titles, stage backgrounds of the story |
| 13994-14015 | 22 | Story mode tutorials |
| 14016-14019 | 4 | Story mode mini-maps |
| 14020-14089 | 70 | Character renders (70) |
| 14090 | 1 | Empty |
| 14091-14095 | 5 | Backgrounds of 5 stages |
| 14096 | 1 | UMD padding |

## Visual effects (`fxNN_*`) — tttpack/effect.py

Auras, beams, impacts, explosions. Found in the system archives (entries 0..5), in
the special move archives of each character (`skill_NNN`, `effect_common`) and in the
story mode. One effect is a run of consecutive parts of an archive, named
`fxNN_<layer>_<item>` (NN = order of the effect in its archive):

| part | content |
|---|---|
| `fxNN_effect.fxh` | header: u8 flags, u8 flags, u16 0, u8 layer count, u8 item count; from +0x40 one 0x20-byte entry per layer: u8 type, u8 item count, u8 texture count, u8 0; then one 0x40-byte record per item (timing and scale, as floats) |
| `fxNN_<layer>_texture[_N].tex` | the textures of a layer (texture format below) |
| `fxNN_<layer>_N.fxs` | settings of item N; many values are min / max triples picked at random |
| `fxNN_<layer>_N_colors.fxc` | colour keys of item N: RGBA as floats 0..255 (alpha 128 = opaque) |
| `fxNN_mesh_N.v000` | a 3D shape (signature `V000`) for the mesh layers |

Layer types, named after the textures they use:

| type | name | settings | textures |
|---|---|---|---|
| 0x00 | (no data) | none in the archive | none |
| 0x02 | trail | 1216 bytes, no colour table | vertical streaks |
| 0x05 | particles | 768 bytes | glows, flames, dust |
| 0x09 | rings | 640 bytes | rings, shock waves, swirls |
| 0x0A | crackles | 576 bytes | scattered electric crackles |
| 0x0E | mesh | `.v000` shape | arcs, cylinders |
| 0x0F | sparks | 448 bytes | small electric sparks |
| 0x10 | glows | 192 bytes | round glows, flares |
| 0x11 | beam | 192 bytes | beam body and tip |
| 0x12 | lightning | 512 bytes | lightning bolts |

A header with no layer (64 bytes: 8 zero bytes, a float, zeros) is a special move with
no visual effect. Some special moves have, just before the header, `fxNN_offsets.fxo`:
176 float vectors (x, y, z, w), (0, -160, 0, 0) or zero in every file seen.

The meaning of each field inside the settings records is not worked out.

In the `effect_common` sub-archive of a character, part 0 (`contents`) is a bit mask
of the sub-archives present (bit k-1 = part k, e.g. 0x77), part 5 holds a one-quad
`mesh` and its texture, part 7 the camera moves of attacks (`attack_camera_N.cman`).

## Model archives (character layout)

The 4 files of a roster character, the story mode board objects (`sm_obj_*`), the
props and the fusion cut-scenes (`ex_*`) are all archives of 497 parts in the same
order (model, textures, parameters, cameras, HUD graphics, animations, special move
effects, effect_common): their parts carry the names of kastomd's `patch.txt`.

## Fonts (`font_NNpx.fnt`) — tttpack/identify.py

Bitmap fonts of the system archives: u8 4 (4-bit pixels), u8 line height, u16 glyph
count, then 16 u16: how many glyphs have a code point ending in hex digit 0..F (the
glyphs are stored in these 16 groups, by code point inside each group). Then one
10-byte record per glyph: u16 Unicode code point, u8 advance, u8 width, u8 height,
u8 x offset, u8 y offset, u24 offset of its bitmap; then the 4-bit bitmaps.

## Textures (`.tex`) — tttpack/texture.py

u32 image count, u32 8, then from +0x20 one 0x60-byte record per image: pixel offset / 4,
palette offset / 4 (from the start of the file), pixel bytes, palette bytes, ..., at
+0x28 u8 log2 height, u8 log2 width. Pixels are 4- or 8-bit palette indices in the PSP
swizzled layout (blocks of 16 bytes x 8 rows); palettes are RGBA8888 with
PlayStation alpha (0x80 = opaque). A record with no pixels is another palette for
the previous image.

## Stage geometry (`.map`) — tttpack/texture.py `map_textures`

Signature `60 0B 9A 7E`. The textures are a `.tex` block at the offset in u32 +0x2C
(size u32 +0x1C, image count u32 +0x18), with offsets from the start of the `.map`.
The geometry (u32 +0x08 / +0x0C: count and offset of the 0x20-byte mesh records) is
not decoded.

## 2D interface graphics (`.rhg`, `.ags`) — tttpack/rhg.py, tttpack/identify.py

`.rhg` (signature `RHG\0`): images and palettes; the n-th 8-bit image uses the n-th
256-colour palette, the n-th 4-bit image the n-th 16-colour palette, PSP swizzled.
`.ags` (signature `AGS\0`): the animation of the graphics of the `.rhg` after it. It
stores, for each animation, its name ("00_open", "01_normal", "40_button_ON"...) and
the names of the sprites it moves ("WINDOW", "BUTTON_01", "btl_hp_1p"...), each
ending with a zero byte. The pair is named after the first sprite names (numbers and
generic words such as open / normal / close dropped), or after the animation names
when there is no sprite name: `btl_hp_1p.ags` + `btl_hp_1p.rhg`. When the developers
only used generic names (`01_normal`), the pair gets these: `normal.ags`.

Translated graphics: language slots in the order of the entries (jp, en, es, fr, de,
it), as 1 animation slot + 6 image slots, or 6 animation slots + 6 image slots (the
button labels of the menus and story texts); empty slots at the end of an archive are
not stored (US: jp, en, es, fr only). The Japanese release fills the
first one only; the European one leaves it empty and fills the 5 others (settings 21:
"Option", "Opciones", "Options", "Optionen", "Opzioni"). These images get the
language at the end: `vol_key_cam_jp.rhg`, `vol_key_cam_en.rhg`... A run of 5
animations followed by 6 slots (the button labels of the story texts) pairs them in
order. An image alone in a slot other than jp is shown in every language and gets no
suffix: the copyright line of the EU title screen (13), stored in the `de` slot only,
appears in French as well.

## Stage and board archives — tttpack/archive.py `stage_names`

The archives of the 10 battle stages (`map_*`) and of the Dragon Walker boards start
with the `.map` geometry (`geometry.map`). Their other parts:

| part | content |
|---|---|
| `map_settings.mapd` | signature `MAPD`, a table of (offset, count) sections; the first holds a position and a unit direction (probably the light) |
| `camera_N.cman` | camera moves (signature `CMAn`) |
| `waypoints.wpt` | big-endian: u32 1, u32 node count, 8 bytes, then 48-byte nodes: x, y, z, 1.0, 4 words, up to 8 u16 numbers of linked nodes (0xFFFF = none): a path graph over the stage |
| `map_effects.mef0` | signature `MEF0`, three lists, empty in the stages seen |
| `ambient_color.lgt` | 64 bytes: one colour (RGBA floats 0..255) |
| `lighting.lgt` | 64 bytes: a colour then distances / factors as floats |
| `event_positions.evpp` | signature `EVPp`, groups of positions (x, y, z, 1.0) with flags |

| `light_pattern.tex` | part 20: a 64 x 64 pattern with alpha, horizontal cyan stripes or green diamonds (Earth 5..8, Supreme Kai world), drawn by 0x088926B4 with the lighting |
| `region_map.bmp` | part 25 of the boards: a small palette image whose colours mark zones (read, not drawn) |

The system archive holds the same two 64-byte layouts as parts 619 / 620.
The unused Earth board (1019) also has a sky: `clouds.tex`, `moon.tex`,
`sky_meshes.dbesl` (a list of DBES meshes) and `sky_settings.dat` (a grey colour, a unit
light direction, ...). The two story mode images 13569 / 13570 (`region_map_1` / `_2`)
are larger maps of the same kind.

## System archives (entries 0..5)

Besides the fonts and the effects, `names.SYSTEM_PARTS` names the parts seen on the JP
release (each only if its type / size matches): button icons, loading screen, aura and
ki textures, and a particle effect driven by the program (3 particle settings and 7
colour tables). In the EBOOT (JP), parts of the system archive are read through the
pointer at 0x08A7E180 (function 0x0887B40C returns part n-1): the effect loaders read
parts 49 / 48 with 47, 51 / 52 with 50 and 55 / 54 with 53, so 47, 50 and 53 are the
settings of those effects (`aura_settings`, `beam_settings`, `small_aura_settings`).
Other parts identified in the EBOOT:

- 37 `customize_items`: 64-byte records, one per customization item. The script native
  at 0x088481F0 reads record n (flags at +0x14) and sets the "owned" / "new" bytes of
  item n in the save data; 0x089CDA7C sums the bonuses of the equipped items
  (u16 item numbers, record = n - 1; +0x0C a signed bonus, +0x18 flags).
- 43 `character_base_stats`: 16-byte records, one per character (number from
  0x089C52F0): u32 base health 30000 (0x089C4578: maximum health = base + bonuses of the
  equipped items, at least 10000), then three u32 (40000 / 20000 / 60000, 100000,
  4..6) whose use is not traced yet.

- 36 `com_character_settings` / 39 `com_ai`: the computer opponent. 36 has one
  60-byte record per character id (0x089CDA7C): u32 AI type (0, 1 or 2; the 25 items
  171..195 of type 2 set it to item - 0xA7 = 4..28), ki amounts (40000, 5000..20000),
  three floats. 39 (read by 0x08870820 into the AI manager at 0x08A7AA70) is one block:
  42 u32 sizes, 8 rule lists (28-byte rules with 0xFF-padded byte lists), then one
  table per AI type whose 8-byte rows are percentages adding up to 100.
- 45 `fighter_camera` (a `CMAn` camera move) and 46 `reference_skeleton` (bone
  positions x, y, z): stored in each fighter by 0x089B3920; 0x089B0054 subtracts
  these positions (or the default skeleton of the EBOOT at 0x08A6EA28) from animation
  bones, scaled by the size of the character.

- 38 `animation_flags`: one u32 of flags per animation slot of the character layout
  (the 414 animations, parts 50..463 of a character archive); the battle code tests its
  bits for the animation being played (0x08914A04, index < 414).
- 40 `camera_param`: the same 36-byte records as part 27 `camera_param` of a character
  archive; the camera code (0x08919CD0) reads record n of the character's table or of
  this common one.
- 41 `battle_voice_events`: one 8-byte record per voice event of a fight (0x08942240):
  s16 first battle voice line, s16 number of lines to pick from at random, float
  seconds before the event can speak again. The ranges match the 126 battle lines
  (40 `switch_out`, 41 `switch_in`, 43..44 `throw_evade`...).
- 42 `action_settings`: 24-byte records for the fighter actions numbered from 126
  (0x08948D94 copies record n - 126 into the fighter when action n starts); byte 0x13
  is a bit of the character's `common_param` +0x20 flags that the action requires
  (0xFF = always available). What each action is has not been traced.
- 44 `blast_types`: 20-byte records, byte 2 a type (0..3), then 4 lists of up to 4
  motion numbers; `blast_param` +0x229 of each character holds the record used by each
  of its Blast 2 attacks and its ultimate (0x089A242C).

- 28..35, unlock lists: what the game gives and when. Same layout: u32 count, then
  12-byte records u32 kind, u32 number, u32 requirement (-1 = never by this list).
  Kind 0 is a character (the number is turned into a roster slot and sets a bit of
  the unlocked characters in the save data), kinds 5 / 6 customization items
  (records of part 37); kind 1 holds numbers 5..9 (probably the 5 locked stages).
  The EBOOT's reward checker (0x08A3419C, run after a battle and when the save is
  loaded) loads list n with 0x08A322A4 (system part 28 + n) and runs one function
  per list:

  | part | name | requirement |
  |---|---|---|
  | 28 | `unlocks_by_story` | Dragon Walker stage to clear (index in the story flag table 0x08A74DF0) |
  | 29 | `unlocks_by_count` | a count kept by the checker (+0x20C); 1000 = when it reaches its total (+0x208) |
  | 30 | `battle_100_rewards_1` | one of 12 flags of the 100 Battles results (save +0x52CC +4..) |
  | 31 | `battle_100_rewards_2` | 3 flags (save +0x52CC +0x10..), set by module 31 at counts 1, 5 and 10 |
  | 32 | `battle_100_rewards_3` | 2 flags (save +0x52CC +0x13..) |
  | 33 | `unlocks_by_battles_played` | number of battles played (save +0x21A8, +1 after each battle, 0x08A19574) |
  | 34 | `reward_all_items` | every customization item owned |
  | 35 | `starting_items` | none: given at once |

  Lists 28 and 33 unlock the same 26 characters (by story, or after 5 to 400 battles).
  With `--txt`, each list gets a `.txt` (kind;number;requirement).

## Story mode effects (`.eedx`)

Signature `EEDX093\0`, u16 / u8 counts, u32 header size (0x20 or 0x60), u32 offset of
the effect data; from the header size, a texture block like a `.tex` file (u32 image
count, u32 8, then 0x60-byte records; offsets / 4 from the block) whose images are
32-bit RGBA (PlayStation alpha, PSP swizzled), then the effect data (floats).
The 28 effects of entry 13937 are named after the "Effect..." debug menu of the
Dragon Walker scripts (chNN_2), which plays effect n for menu item n + 1 (item 0 is
">> Clear <<"): normal_move, aura_zone_zoom, ..., burst00..02, smoke, ..., boss_aura,
spelled as the developers wrote them (`lienwork`). The textures agree (three
explosions for burst00..02, smoke for smoke, lightning for bind / lightning).
Their effect numbers in the Dragon Walker module (0x08AED348 maps them to a part of
13937; skill n of the "Use Skill" debug menu plays one through the table 0x08AED4F0)
confirm this order: Taiyouken plays effect 22 = part 3, Solution 30 = part 6,
Kiwokesu 2 = part 8, Teleportation 23 = part 10.

The 5 effects of each board object (part 495 of its archive) are the character's own
versions, in its colours, of effects that have no part in 13937: `aura` (put on every
character when it is created, 0x08AAC9EC), `skill_aura` (the skills Kaiouken, Charge,
Headbreaker, Rush, Novastrike and Tackle), `charge` (played with the motion
`charge_in`, 0x08AB1180), `charge_max` (with `charge_max`, 0x08AB12BC) and `aura_2`
(kept by the character next to its aura, 0x08A8A6B4; same layout as `aura`).

The animations of the board objects are the 32 board motions (`stand`, `search`,
`pick_up`, ... `down_loop`), in the order of the "Motion..." debug menu of the
chNN_2 scripts; the module plays them by that number (0x12 = `charge_in`).

## Camera moves (`.cman`) — tttpack/cman.py

Signature `CMAn`. Header: u32 non-zero until the EBOOT has turned the offsets into
pointers (0x089A92D0), u32 offset of the channel table, u32 channel count (6), f32 0
or 10.0, f32 length in frames, u32 offset of the 8 start values, u32 offset of an
extra block (ignored when the next u32 is below 2). Channel table: u32 output slot,
u32 offset of the keys, u32 key count, 0. Keys: 32 bytes, u32 flags, f32 frame, f32
value, then 5 words the evaluator (0x089A9374) does not read; flag 0x10 holds the
value until the next key, otherwise values are interpolated linearly. Slots 0..2 are
the camera position, 3..5 its rotation (radians). With `--txt`, each `.cman` gets a
`.txt` listing its keys.

## DBES meshes (`.dbes`)

Signature `DBES`, u32 1, u32 0x20 (header size), u32 offset of the second block,
u32 triangle count, then the triangles as 16-byte records of three vertex numbers (and
a zero), then the vertices. Used by effects (system parts 615 / 617 with the
`ki_swirls` texture) and by the models of some special moves.

## Small model archives — tttpack/archive.py `model_names`

An archive with a `.pmdl` that is not of the character layout (props, models of
special moves) gets `model.pmdl` (or `mesh.dbes`), `textures.tex` and `animation_N.mot`.

## Character portraits of the menus — tttpack/archive.py `roster_portraits`

A menu archive with a run of 70+ consecutive `.rhg` parts holds one portrait per
character in the order of the select screen (the roster order of official.py with the
Frieza soldier right after Frieza full power), then `random_portrait` and `random_icon`.
Checked on the images of the training menu; the other menus are named the same way.

## Other parts named from their content — tttpack/identify.py

- `text.tbl`: a text table inside an archive.
- `story_script.bbq`: a BBQ script with dialogue (the chapter script stored in the
  `sm_txt_chNN` archives of the second text set).
- `geometry.map`: stage / board geometry.
- `staff_roll_script.bbq` (credits archive, calls written `staff_r_color(...)`) and
  `field_event_script.bbq` (story text archive 13734, debug message
  フィールドイベント開始 "field event start").
- `sounds/`: a sound bank inside an archive, one `.vag` per sample.

## Mode tables of the language menus — tttpack/names.py `MODE_PARTS`

- 100 Battles (`menu_battle_100_*`) part 0 `course_layout` (13-word cells with links
  and a 10000 marker), part 1 `opponents` (11-word records: character, level, ...);
  Survival (`menu_survival_*`) part 1 `course_layout` (a grid of cell kinds 0 / 1 / 5 /
  7), part 2 `opponents`.
- Battle interface (`battle_ui_*`, 13261..13266) part 1 `special_matchups`: u16 count,
  then 16-byte records (u16 voice, u16 character, u16 pose 0..2, 0, then the same for
  the opponent): the special pre-battle talks between two characters (0x0890551C
  looks up the pair, 0x08907498 plays voice + 0x355). Parts 2..6
  `matchup_camera_1..5` are their camera moves, chosen from the two poses (0x0890544C:
  second pose 0 -> 2, first pose 0 -> 1, 1 -> 3, 2 then 1 -> 4, 2 then 2 -> 5).

## Text tables (`.tbl`) — tttpack/text.py

u16 100, u16 first id, u32 last id, u32 count; from +0x10, 14 reserved slots, then one
slot per id (slot = 14 + id - first id). The ids are the ones the scripts and
parameter files use. Glyphs U+FF67 + k are the button icons of the font.

## Scripts (`.bbq`) — tttpack/bbq.py, tttpack/identify.py

The u32 at +8 of every BBQ file is its build time (Unix time, August 2010 for the
story scripts). Scripts with no code are told apart by their section tables:
`map_script` (the chNN_3 scripts and part 1 of every `sm_txt_chNN` archive; the
Dragon Walker module loads 13273 + 3 x map as the script of a map), `small_script_1`
/ `small_script_2` (13935 / 13936, and parts 5 / 4 of every `sm_txt_chNN` archive,
the same bytes). The `sm_txt_chNN` archives also hold `story_script` (the chapter
script), `text` (the chapter text) and `shadow` (a black disc fading to the edge).


`.BBQ1.00` stack VM: section table, instructions, the natives used by the story mode
and the menus (native 0 / 1 jump to the script with that PACKFILE index).

## Sound (`.at3`, `.phd` + `.pbd`)

ATRAC3 written with a RIFF header (vgmstream, ffmpeg); the samples of the libsndp PPHD
sound banks as `.vag` (below).

## Encrypted file (`.pgd`) — tttpack/pgd.py

Entry 7 (`boot_encrypted.pgd`, 1184 bytes) is a PSP PGD container, read by the boot
module (entry 6) through sceIoIoctl(0x04100001) with a key it builds byte by byte on
the stack. The tool decrypts it with no key: the version key comes from the MAC at
0x70, and the MACs at 0x60 / 0x80 are checked (fixed key "flag 2"). The algorithms
(KIRK AES-128-CBC keys 0x38 / 0x39 / 0x63, BBMac, BBCipher) follow tpu's reverse
engineering in kirk_engine (amctrl.c, pgd.c). The content (`boot_decrypted.dat`,
1024 bytes) is a table of values whose nibbles are mostly 1..9; what the boot module
does with it has not been traced. The EBOOT builds another key the same way at
0x088305F8 (d8 c0 3b 57 ...), for a file it opens with the same call (probably the
install data, DATAINST.BIN), not for this one.

## Sound bank samples (`.vag`) — tttpack/sound_bank.py

A bank (`.phd` header + `.pbd` data) holds PSX ADPCM samples with no names. Each one is
written as `NAME/PREFIX_SSS_<name>.vag` (PREFIX = entry and part numbers, SSS = slot in
the bank's PPVA table): a 48-byte VAG header (big-endian: "VAGp", 0x20, 0, data size,
sample rate, 12 zero bytes, 16-byte name) in front of the same bytes, so nothing is
re-encoded; the loop flags stay in the ADPCM frames. The table's count field is the
last slot number (96 for the 97 slots of a character's bank). The names come
from kastomd's Editor_indice_Py, chosen like his tool does by the slot count: 97 slots
= a character's bank (sfx_ch.txt: hurt_1_normal, melee_1_combo, sonic_sway...), 85 =
the battle bank 13267 (sfx_bt.txt). The other banks (menus, system, story mode) have
no list yet. What only the `.phd` held (programs, tones: key ranges, volume, envelope)
is not written.

## Differences between releases — tools/compare_packfiles.py

The three releases share the same 14097-entry table. Compared entry by entry (and part
by part with `--parts`, BBQ build times ignored), US against EU:

- The US has no entry the EU lacks. The EU has 146 more: every `_de` / `_it` entry
  (system, menus, battle interface, story texts and interface).
- Translated graphics: the EU fills the `de` and `it` image slots of the menus, title
  screens, chapter titles, tutorials and results; the US leaves them empty.
- Boot logos (entry 8): 6 screens in the US (Bandai Namco Games, Bandai, Toei
  Animation, FUNimation Entertainment, Okratron 5000, Spike) against 3 in the EU.
- Title screen (13): another logo (part 11) and English "Press START" (part 21); the
  copyright line in the `en` slot (US) or the `de` slot (EU). Loading screen of the
  system archives (parts 7, 8) differs too.
- Texts: the system text tables (part 2) of en / es / fr, the 31 Spanish chapter texts
  (first set, 18 bytes each), a few English / French chapters (ch22, ch25), the credits.
- Characters: only `move_list_name` (part 43) differs, same size, in every costume;
  probably other text numbers for the same moves (not checked).
- A few retouched images (French battle HUD part 192, French story interface part 8,
  Spanish customize menu 36/11) and the program modules (.elf), mostly same size.
