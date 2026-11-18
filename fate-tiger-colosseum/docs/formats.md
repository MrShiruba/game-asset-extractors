# File formats — Fate/tiger colosseum (PSP, ULJM05266)

All integers are little-endian. ✅ = format understood and documented below.

| Ext. | Count | Magic | Contents | Status / tool |
|---|---|---|---|---|
| `.bnd` | 1 + 95 | `BND\0` | Archive | ✅ `fate_tiger.py extract` |
| `.pac` | 107 | — | Compiled scripts (bytecode) | ✅ `fate_tiger.py text` / `disasm` |
| `.at3` | ~4100 | `RIFF…WAVE` | ATRAC3 voices / sounds | standard — vgmstream, ffmpeg |
| `.vag` | 149 | `VAGp` | PS-ADPCM sounds | standard — vgmstream |
| `.phd` / `.pbd` | 96 / 96 | `PPHD` / — | Sony sound bank (header + data) | standard — vgmstream |
| `.gmo` | ~1280 | `OMG.00.1PSP` | PSP 3D models | standard — Noesis, Blender plugins |
| `.gim` | 124 | `MIG.00.1PSP` | PSP textures | standard — Noesis, GimConv |
| `.pmf` | 5 | `PSMF` | PSP movies | standard — PMF tools, ffmpeg (partial) |
| `.png` | 2 | PNG | Images | standard |
| `.gmp` | 58 | `PXG.00.1OMG.` | Precompiled model: GE display lists + vertex data | ✅ |
| `.col` | 15 | `COl\0` | Stage collision | ✅ documented |
| `.pcl` | 15 | `PCL\0` | Stage walls (2D boundary segments) | ✅ |
| `*eff*.bin` | ~170 | `EFFECT2\0` | Particle effects | ✅ |
| `.ftl` | 1 | `FNTL` | Font glyph table (glyphs are in `font_00.gim`) | ✅ |
| `namefilterlist.dat` | 1 | `FMAP` | Banned-word filter (player names) | ✅ |
| `ucs2jis.bin` | 1 | — | Unicode → JIS X 0208 table | ✅ |
| `jis2ucs.bin` | 1 | — | JIS X 0208 → Unicode table | ✅ |

---

## BND (archive)

Uncompressed, unencrypted archive. `PSP_GAME/USRDIR/BUILDED.BND` holds 5007 files,
95 of which are themselves BND archives in the same format.

### Header

| Offset | Type | Value |
|---|---|---|
| 0x00 | char[4] | `BND\0` |
| 0x04 | u32 | version (1) |
| 0x08 | u32 | data alignment (0x800) |
| 0x0C | u32 | header size (0x20) |
| 0x10 | u32 | name table offset |
| 0x14 | u32 | data start offset |
| 0x18 | u32[2] | 0 |
| 0x20 | u32 | file count |
| 0x24 | u32 | entry count (files + directories) |

### Entry table (at 0x28, 16 bytes per entry)

| Offset | Type | Value |
|---|---|---|
| +0x0 | u32 | **CRC-32** (standard, as `zlib.crc32`) of the full path with a leading `/`, e.g. `/prj/tiger/data/builded/battle.bnd`; directories included. Entries are sorted by this hash |
| +0x4 | u32 | absolute offset of the record in the name table |
| +0x8 | u32 | data offset (relative to the start of this BND) |
| +0xC | u32 | exact size |

Directories have offset and size set to 0.

### Name table

Sequence of records, in depth-first order of the tree:

| Offset | Type | Value |
|---|---|---|
| +0 | s8 | depth: > 0 for a directory, < 0 for a file (absolute value = depth) |
| +1 | u8 | length of the previous record (0xFF for the first one) |
| +2 | u8 | length of this record |
| +3 | u32 | offset of the matching entry in the entry table |
| +7 | char[] | null-terminated name (directories end with `/`) |

The full path is the concatenation of the parent directory names (lower depth).
Example: `/` → `prj/` → `tiger/` → `data/` → `builded/` → `battle.bnd`.

Nested BNDs store complete paths (`prj/tiger/data/builded/battle/…`); their offsets are
relative to the start of the nested BND.

---

## PAC (scripts)

Virtual machine bytecode. Each instruction starts with the 4-byte marker `25 GG OO 00`
(`%`, group, command index, 0) and its arguments run until the next marker. The command names
come from the game's registration tables in `EBOOT.BIN` (records of `{char *name, u32 id, 0, 0, 0}`,
file offsets 0xF906C–0xFAC18; command index = `id − 1`). The full list is in
[`pac_opcodes.md`](pac_opcodes.md); `fate_tiger.py disasm` prints readable listings.

| Group | Name | Commands | Used by |
|---|---|---|---|
| 0 | core | 64 | everything: `cmd_jmp`, `cmd_call`, `cmd_mov`, `cmd_ifEQ`, `cmd_waitFrame`… |
| 1 | message | 82 | dialogue windows, voices, BGM, SE: `setMessageLabel`, `setFontColor`, `playVoice`… |
| 2 | menu | 10 | pad input and menus |
| 3 | GameSystemCommand | 23 | story flow: `setStageID`, `setVersusCharacter`, `setVersusRuleMessageLabel`… |
| 4 | CharacterSetup | 36 | `setup_XXX.pac`: attacks, guards, effects, voices per character |
| 5 | StageSetup | 20 | `path_XXX.pac`: AI navigation graph (`setMapNodeMax`, `appendNode`, `connectLink`) |

Each command's argument layout was read from its handler in `EBOOT.BIN` (the handler reads its
operands with a helper at 0x0885E118, `getOperand(index, typed, size)`); `pac_opcodes.md` lists them.
Arguments are read in order and the instruction is padded to 4 bytes:

| Kind | Encoding |
|---|---|
| typed | 1 type byte, padding to the next multiple of 4, then a 32-bit value |
| raw u32 / u16 / u8 | the value, aligned on its own size (u8: no alignment) |
| string | inline null-terminated Shift-JIS (`cmd_string`, `cmd_print`, `setMessage`…) |
| label | a raw u32 offset to a string in the pool (`setMessageLabel` 1.0E, `setWindowNameLabel` 1.04, `setVersusRuleMessageLabel` 3.11) |

Operand types (type byte of a typed argument, resolved by the function at 0x0885E00C):

| Type | Meaning | `disasm` shows |
|---|---|---|
| 0x00, 0x01, 0x02 | integer immediate (0x02 is the one used in practice) | `5`, `-1` |
| 0x10 | float immediate | `1.2` |
| 0x04 | integer variable of the running script | `i[n]` |
| 0x20 | float variable of the running script | `f[n]` |
| 0x08 | global integer variable (shared by all scripts) | `gi[n]` |
| 0x40 | global float variable | `gf[n]` |

Jumps and calls take a raw u32 offset from the start of the file. `cmd_inxJmp` reads a typed index and
then jumps through the table of u32 offsets that follows it (`.jumptable` in `disasm`). Checked on
`story_main_sbw_jp.pac`, `setup_sbw.pac`, `path_sto.pac` and `battle_main_jp.pac`: every instruction
decoded with these layouts ends exactly on the next marker.

Strings are **Shift-JIS (cp932)** in a pool after the code; `/` is a line break. Inline control
tags: `&tsp(x)` (text display speed: the scripts put `&tsp(0.0)` before text that must appear at once and `&tsp(1.0)` after it to restore the normal speed), `&scl(x , y)` (character scale, e.g. `&scl(3.0 , 1.0 )―&scl(1.0 , 1.0 )`
stretches a dash).

Voices: after `setMessageLabel`, the script does `cmd_mov var[1], <voice ID>` then calls a script
subroutine that plays it. The ID indexes `voiceidtable.pac`. Some lines play their voice another way
(string `<<<<< Waiting VoiceNK >>>>>`); their voice is not resolved yet.

`path_XXX.pac` (one per stage): `appendNode(id, 0, x, y, z, link_count)` and
`connectLink(node_a, node_b, distance)`.

Files:
- `story_main_XXX_jp.pac`: each character's story mode (text + flow).
- `setup_XXX.pac`: character setup (group 4). `setup_<stage>.pac` for stages.
- `path_XXX.pac`: stage navigation graphs (group 5).
- `cmd_XXX.pac` (one per character): **command input table**, run by a separate 8-instruction
  interpreter (handler table at 0x08918AEC in `EBOOT.BIN`, loop at 0x088AA90C). See below.
- `param.pac`: (u32 id, u32 value) pairs (value 300 for most ids), followed by a few instructions.
- `battle_main_jp.pac`: small battle flow script.
- `ai_XXX.pac`: empty in the shipped game (0–4 bytes).
- `voiceidtable.pac`, `bgmidtable.pac`, `advseidtable.pac`, `modelidtable.pac`,
  `itembillboardidtable.pac`: plain ID tables, see below (not bytecode).

### cmd_XXX.pac (command input tables)

Which pad input starts which move. Same `25 00 OO 00` marker, but the opcode is the u16 at +2 and is
run by its own interpreter (not the script VM). The header's u32 at +0x0C points to a zero-terminated
list of entry offsets (0x1054 in `cmd_sbw.pac`); the game checks every entry each frame.

| Op | Words after the marker | Meaning (from the handlers) |
|---|---|---|
| 1 | id, action_offset, previous | starts an entry: command id, offset of its action record (op 7), and the action that must be running for this entry to apply (−1 = any: used for combos / follow-ups) |
| 2 | — | no-op |
| 3 | pressed, kind, buttons, window | pad condition: `buttons` is a PSP pad mask (0x20 right, 0x40 down, 0x80 left, 0x10 up, 0x1000 triangle, 0x2000 circle, 0x4000 cross, 0x8000 square, 0xF000 any face button; 0x10000 / 0x20000 are game-defined); `pressed` 0 inverts the test; `window` = frames the input stays valid (0 = this frame) |
| 4 | state, value | character state condition (checked by the function at 0x088AFA78) |
| 5 | — | end of the conditions |
| 6 | priority | entry matched: the action is queued if no higher-priority entry was |
| 7 | 10 words | action record (at 0xB00…), copied as is to the character's "next action"; see the table below |
| 8 | same as 3 | same handler as 3; used in the parameter list at the header's +0x10 offset |

Header: u32 +0x00 = offset of the action records, +0x0C = entry list, +0x10 = parameter list; a few
values (0, 1, 11.0, 3.0, 6.0) sit just before the entry list.

Action record (op 7), with the values seen in the 641 records of the 21 files. The record is
copied to the character (functions 0x088AA640 and 0x088AFFD4), which plays the motion:

| Word | Type | Use |
|---|---|---|
| 0 | u32 | action slot (0–30; every character has the same slots) |
| 1 | u32 | **motion id** played by the character (`playMotion`, 0x08844A44); the interpreter also maps it to one of about 20 internal move categories (0x1B–0x1F = step / dodge variants…) |
| 2 | u32 | timing-set variant: selects which list of timed events (attacks, sounds, effects declared by the `CharacterSetup.set…Timing` commands of `setup_XXX.pac`) runs with this motion (0 / 1) |
| 3 | f32 | start frame of the motion (0.0 / 3.0) |
| 4 | f32 | motion blend time in seconds (0.06, 0.2…) |
| 5 | u32 | loop the motion (stored as a byte in the motion player) |
| 6 | u32 | 1 on attack motions that hop (ids 8, 24, 25, 28), 0 elsewhere |
| 7 | f32 | −1.0, or a frame number (6–16); see below |
| 8 | f32 | **initial vertical speed** of the hop (0.5–7.0), copied into the character's velocity when the motion starts (0x088B1ADC); a negative value reverses the move direction (0x088B1E6C) |
| 9 | f32 | **frame from which the rise is damped**: while the character is still going up and the motion frame is ≥ this value, the vertical speed is halved every frame (0x0887B55C, 0x0887D840) |

Words 0–5, 8 and 9 are confirmed in the code (8 and 9 also with PPSSPP memory breakpoints during
Saber's and the CPU's attacks). Words 6 and 7 were never read in about 3500 memory-breakpoint hits
covering attacks in the air, attacks that connect and the CPU's attacks: they appear to be unused by
the game (leftover data from the tools).

`fate_tiger.py disasm` decodes these files with this instruction set (`entry`, `pad`, `state`, `then`,
`commit`, `action`, `param`).

### voiceidtable.pac

32-byte records: u32 ID (0, 1, 2…), char[28] path (`10SBW/sbw100040.at3`).
Terminated by `FF FF FF FF`. 4054 entries. Paths appear to be relative to
`prj/tiger/data/builded/sound/advvoice/` (lower-case folders after extraction).

### ID tables

Not bytecode: fixed-size records starting with a u32 ID (0, 1, 2…), terminated by `FF FF FF FF`.

| File | Record | Fields | Entries |
|---|---|---|---|
| `bgmidtable.pac` | 16 bytes | u32 ID, char[12] file (`ML01.at3`) | 49 |
| `advseidtable.pac` | 32 bytes | u32 ID, char[28] file (`SE_ADV_001.vag`) | 149 |
| `modelidtable.pac` | 48 bytes | u32 ID, u32 kind (0 or 1), char[40] path (`w000/g000win.gmo`) | 589 |
| `itembillboardidtable.pac` | 32 bytes | u32 ID, f32 × 7 (sizes / scales: `10.0, 10.0, 0, 0, 1.0, 1.0, 0`) | 2 |

`modelidtable.pac` paths start with `c` (characters), `t` (tarot cards), `m`, `e` or `w`. Kind 0 marks
the 13 `wNNN/gNNN….gmo` models (the story-mode message window models loaded by `loadWindowModel`,
from `adv/wNNN.bnd`); every other model has kind 1.

### Character codes

Used as file-name prefixes (`ai_sbw`, `story_main_rin_jp`, `sbw100040.at3`…).

| Code | Character | Code | Character |
|---|---|---|---|
| arc | Archer (アーチャー) | koj | Assassin (アサシン, Sasaki Kojirō) |
| ily | Illya (イリヤ) | sir | Shirō Emiya (衛宮士郎) |
| cas | Caster (キャスター) | gil | Gilgamesh (ギルガメッシュ) |
| sou | Kuzuki Sōichirō (葛木宗一郎) | kir | Kirei Kotomine (言峰綺礼) |
| ass | True Assassin (真アサシン) | sbw | Saber (セイバー) |
| sbb | Saber Alter (セイバーオルタ) | rin | Rin Tōsaka (遠坂凛) |
| ber | Berserker (バーサーカー) | tig | Taiga Fujimura (藤村大河) |
| skw | Sakura Matō (間桐桜) | skb | Dark Sakura (間桐桜（黒）) |
| sin | Shinji Matō (間桐慎二) | rid | Rider (ライダー) |
| lan | Lancer (ランサー) | kar | Caren (カレン) |
| baz | Bazett (バゼット) | | |

Confirmed from `EBOOT.BIN`: the per-character file-name table (`story_main_XXX_jp.pac`, `setup_XXX.pac`,
`cmd_XXX.pac`, file offset 0x10749C) and the display-name table (0x101704, 0x24 bytes per name) use the
same order.

---

## COL (stage collision) ✅

Checked on `am000tes_d.col` (test stage, 1 mesh) and `am001emi_d.col` (11 meshes).
`_d` / `_n` = day / night variant.

| Offset | Value |
|---|---|
| 0x00 | `COl\0` |
| 0x04 | u32 0x20 (header size) |
| 0x0C | u32 mesh count |
| 0x10 | u32 offset of the mesh offset table (0x20) |
| 0x14 | `CC` padding |
| 0x20 | u32 × mesh count: absolute offset of each mesh |

The stage is split into several meshes (sectors), each with its own bounding box.

Mesh header (offsets relative to the mesh header):

| Offset | Type | Value |
|---|---|---|
| +0x00 | u32 | vertex offset (always 0x40) |
| +0x04 | u32 | vertex count (= 3 × triangle count, vertices are not shared) |
| +0x08 | u32 | triangle offset |
| +0x0C | u32 | triangle count |
| +0x10 | u32 | k-d tree: node offset table |
| +0x14 | u32 | k-d tree: first node |
| +0x18 | u32 | node count (0x3F) |
| +0x1C | u32 | triangle count again |
| +0x20 | f32 × 4 | bounding box: xmin, xmax, zmin, zmax |

- Vertices: 4 × f32 (x, y, z, 1.0).
- Triangles: 4 × u32 (i0, i1, i2, 0), indices local to the mesh. These are the walkable surfaces:
  171 of the 172 triangles of `am001emi_d.col` face up, at several heights (0 to 50). Walls are in the `.pcl`.
- +0x10 points to a table of u32 node offsets and +0x14 to the nodes (count at +0x18): a **k-d tree**
  over the mesh for fast lookups. Node (0x20 bytes): u32 split axis (0 = x, 1 = z), f32 split
  position, s32 child below, s32 child above (−1, −1 = leaf), u32 triangle count, u32 offset into the
  triangle index list, `CC` padding. Each triangle is stored in exactly one node; the index list
  (u32 per triangle) follows the nodes. Checked on all 221 meshes of the 15 `.col` files: the counts
  add up to the triangle count, the offsets are running sums and the list is a permutation of the
  triangles. The tree is not needed to
  rebuild the geometry: vertices + triangles are enough to export an OBJ.

## PCL (stage walls) ✅

Loaded together with the `.col`, `.phd` and `.pbd` of the same stage (function at 0x08890D6C in
`EBOOT.BIN`). Checked on all 15 `.pcl` files (1922 segments). Holds the stage boundaries and obstacles as
polylines of wall segments seen from above (the `.col` holds the floor). `_d` / `_n` = day / night.

| Offset | Type | Value |
|---|---|---|
| 0x00 | char[4] | `PCL\0` |
| 0x04 | u32 | 0x20 (header size) |
| 0x0C | u32 | loop count |
| 0x10 | u32 | offset of the loop offset table (0x20) |
| 0x14 | — | `CC` padding |
| 0x20 | u32 × loop count | absolute offset of each loop |

Loop: u32 absolute offset of its segments, u32 segment count, `CC` padding up to 0x20, then the
segments (0x40 bytes each):

| Offset | Type | Value |
|---|---|---|
| +0x00 | f32 × 4 | start point (x, y, z, 1.0); y = height of the wall at that point |
| +0x10 | f32 × 4 | end point (x, y, z, 1.0) |
| +0x20 | f32 × 4 | bounding box: zmin, zmax, xmin, xmax |
| +0x30 | f32 | segment length |
| +0x34 | f32 × 2 | the corner angles at the two ends of the segment, in radians: angle between this wall and the neighbouring one (π/2 on a rectangle corner, π where the wall continues straight, 0 / π on open ends). The two values are not always in start / end order. Checked: they match the geometry on all 1692 segments that have two neighbours |
| +0x3C | — | `CC` padding |

Each segment ends where the next one starts. Most polylines are closed (the last segment ends on
the first); 74 segment ends, in short 2-segment polylines, are open. Length and bounding box match
the points on every segment.

## GMP (precompiled models) ✅

Read by the function at 0x088C68CC in `EBOOT.BIN` (no magic check). Checked on all 58 `.gmp` files:
sections, display lists (every draw stays inside the vertex section) and embedded textures. Not a GMO: the model is already
converted to PSP GE display lists and vertex buffers, ready to send to the GPU, so Noesis does not
open it. The structure below is enough to read the geometry.

| Offset | Type | Value |
|---|---|---|
| 0x00 | char[12] | `PXG.00.1OMG.` |
| 0x10 | u32 | 1 |
| 0x14 | u32 | file size |
| 0x18 | u32 | file size |
| 0x24 | u32 | 0xC0 |
| 0x40 | (u32, u32) × 4 | offset and size of the 4 sections (rewritten in memory at load time) |
| 0x80 | — | sections |

Each section starts with a 0x40-byte header: u8 type (0–3), u32 size at +0x04 and +0x08.

| Type | Contents |
|---|---|
| 0 | material / texture bindings: 0x40-byte records (kind 3 = material, kind 0x0A = texture by name, e.g. `arc_w2`); each gives a name offset (+0x1C, from the start of the file; names such as `arc_w1`, `itm00`, `b007san`), a list (+0x28, count at +0x2C) and the display-list offset to patch (+0x30). At load time the game looks the texture up and writes a GE `BASE` + `JUMP` there (function 0x088C62D8) |
| 1 | material / transform values, then **PSP GE display lists** |
| 2 | **vertex buffers** referenced by the display lists |
| 3 | embedded textures: sub-records of type 0x4003, each a header (u16 GE pixel format, u16 width, u16 height, u16…) then the data. Images are format 4 (4-bit indexed) or 5 (8-bit indexed), 32 × 32; palettes are separate sub-records of format 3 (RGBA8888) or 1 (RGBA5551), 16 × 1 or 256 × 1. Empty (header only) when the textures come from elsewhere |

The display lists are plain PSP GE commands (u32: command in the top byte, parameter in the low
24 bits). All addresses in them (`CALL`, `VADDR`) are **offsets from the start of the file**; the
game adds the load address via `BASE` 0. Example from `cursor_01.gmp`:

```
0x1B4  10000000 BASE 0      0x240  12000139 VTYPE 0x139
       0A0009C0 CALL 0x9C0         10000000 BASE 0
       10000000 BASE 0             01000AC0 VADDR 0xAC0
       0A000240 CALL 0x240         04050004 PRIM triangle fan, 4 vertices
       0E120000 SIGNAL             ...
       0C000000 END
```

The list at 0x9C0 sets render state (material colours `AMA`/`AMC`, lighting, texture mapping…);
the list at 0x240 draws: `VTYPE` 0x139 = 8-bit UV, 16-bit RGBA4444 colour, 8-bit normal, 16-bit
position → 14-byte vertices, which matches the vertex data. Across the 58 files only two vertex
formats are used (0x139, and 0x138 = the same without UV) and every `PRIM` is a triangle fan. Converting a GMP to a standard model
therefore means walking the lists and decoding `VTYPE` / `VADDR` / `PRIM` (any GE documentation, e.g.
PPSSPP's, describes the bits). Textures are referenced by name (section 0) or embedded (section 3).

## EFFECT2 (`syseff*.bin`, `*_c1_eff*.bin`) ✅

Read by the function at 0x088514A8 in `EBOOT.BIN`, which checks the 8-byte magic.

| Offset | Type | Value |
|---|---|---|
| 0x00 | char[8] | `EFFECT2\0` |
| 0x08 | u32 | file size |
| 0x0C | u16 | emitter count |
| 0x0E | u16 | file size again |
| 0x10 | — | emitters, one after another |

Emitter: a 0x60-byte header followed by `n` blocks of 0x80 bytes, where `n` is the u16 at
header +0x0E. Next emitter = header + 0x60 + n × 0x80 (checked on all 171 effect files, 388 emitters,
802 blocks: the chain ends exactly at the end
of the file on two samples).

| Header offset | Type | Known use |
|---|---|---|
| +0x00 | u16 | particle type: 0x04A0 (206 emitters) = sprite whose spin is applied around the view axis (z), 0x05D0 (182) = spin applied around the vertical axis (y); the code also handles 0x0280, unused in the files |
| +0x02 | u16 | sprite flags: 0x04 = use the width at +0x0A, 0x08 = use the height at +0x0C, 0x02 / 0x10 = quad anchoring (centre / edge), 0x1000 = set on 101 emitters but never tested by the game code (searched the whole EBOOT), so it has no effect |
| +0x06, +0x08 | u16 | texture width / height (128 × 128 or 64 × 64 in the 171 files); the game stores 1/width, 1/height |
| +0x0A, +0x0C | u16 | sprite width / height in 1/2000 units (6000 → 3.0) |
| +0x0E | u16 | number of 0x80-byte blocks (particle stages) |
| +0x10 | u8 × 4 × 16 | sprite frames: up to 16 rectangles in the texture (u0, v0, u1, v1), e.g. `60 00 7F 1F` = u 96–127, v 0–31. A block picks one with its +0x36 field, or the game animates through them |
| +0x50, +0x52, +0x54 | s16 | flags: follow position / direction / … of the owner |
| +0x56 | u16 | copied |

Each 0x80-byte block is one **stage** of a particle's life: a particle starts with block 0 and moves to
the next block when the stage time runs out (function 0x08851E24). Blocks are read by the functions at 0x0884EB40 (stage start), 0x08851990 (spawn) and
0x08851E24 (update). Most values come as a (base, random range) pair: a bit of the mask at +0x00 turns
the random part on. Angles are s16 in units of 2π/4096 (the game multiplies by π/2048); sizes and
speeds are s16 × 0.001.

| Offset | Type | Use |
|---|---|---|
| +0x00 | u32 | randomise mask (bit 0 → +0x0E, bit 1 → +0x12, bit 2 → +0x22, bits 13–15 → +0x28/+0x2C/+0x30, bits 6–8 → +0x4E/+0x52/+0x56…) |
| +0x04 | u32 | behaviour flags (bits 0–2: integrate rotation x/y/z; 0x200–0x800, 0x04000000–0x10000000: lock / follow axes; 0x4000 / 0x8000: timing mode; bit 31: special spawn) |
| +0x08 | u16 | stage counter / repeat |
| +0x0A | u16 | particles spawned (0 → 1) |
| +0x0C, +0x0E | u16 | stage duration (frames) + random |
| +0x10, +0x12 | u16 | particle lifetime + random |
| +0x14, +0x18 | u32 | start size × 0.001 + random (1000 = 1.0, most common) |
| +0x1C | u32 | end size × 0.001 (the size is interpolated over the life) |
| +0x20, +0x22 | s16 | initial speed × 0.001 + random |
| +0x24 | s16 | end speed × 0.001: with flag 0x10000 of +0x04, the speed moves from +0x20 to this value over the stage |
| +0x26/+0x28, +0x2A/+0x2C, +0x2E/+0x30 | s16 pairs | emission direction x / y / z (angle + random) |
| +0x32 | s16 | 0 / 1 flag |
| +0x34 | s16 | sprite animation: first frame |
| +0x36 | s16 | sprite frame = index into the emitter's rectangle list (always below the rectangle count) |
| +0x38 | s16 | sprite animation: frame count / speed |
| +0x3A/+0x3C, +0x3E/+0x40, +0x42/+0x44 | s16 pairs | rotation x / y / z: start angle, change per frame |
| +0x46, +0x48, +0x4A | s16 | per-frame change (angle units) of a second rotation triplet of the particle (particle +0x10 / +0x14 / +0x18), separate from the sprite rotation at +0x3A…+0x44 |
| +0x4C/+0x4E, +0x50/+0x52, +0x54/+0x56 | s16 pairs | spawn offset along the emission direction, x / y / z, × 0.001 + random |
| +0x58 … +0x5B | u8 × 4 | colour R, G, B, A |
| +0x5C, +0x5E, +0x60 | u16 | fade timings |
| +0x62 | u16 | random extra particle count |
| +0x64, +0x66 | s16 | scale × 0.001 |
| +0x68 | u32 | second flag word (0x2000 = go to next stage, 0x100000 = spawn mode) |
| +0x6C … +0x78 | u16 | timings used by the update |
| +0x7A, +0x7B | u8 | always 0 in the 171 files |
| +0x7C | s16 | scale-related value |

Offsets, types and the (base, random) pairing are certain; the names are deduced from how the
values are used (conversions, which particle fields they drive) and may be refined.

Matching textures are the `.gim` files with the same name
(`sbw_c1_eff.gim`…).

## Font (`font.bnd`: `font_00.ftl` + `font_00.gim`) ✅

`font_00.gim` is a standard GIM holding **7 pictures of 256 × 256, 4-bit indexed, swizzled**: the
glyph pages. Noesis / GimConv open it. Glyphs are 13 × 13 px on a 15 px grid. The game only has
full-width characters (ASCII letters are full-width forms U+FF21…).

`font_00.ftl` maps a **Unicode** code point to a glyph (parsed by the function at 0x08857F2C in
`EBOOT.BIN`, which checks the magic byte by byte):

| Offset | Type | Value |
|---|---|---|
| 0x00 | char[4] | `FNTL` (the game changes the 4th byte to `@` once loaded) |
| 0x04 | u32 | version (0x20 → 12-byte entries; below 0x20 → 2-byte entries) |
| 0x08 | u32 | characters per block (0x1000) |
| 0x0C | u32 | 0x10 |
| 0x10 | u32 | block count (10) |
| 0x14 | s32 × 16 | block index for each range of 0x1000 code points, −1 = none |
| 0x54 | — | blocks: 0x1000 entries of 12 bytes each |

Here: U+0xxx → block 0, U+2xxx–U+9xxx → blocks 1–8, U+Fxxx → block 9. 0x54 + 10 × 0xC000 = file size.

Lookup: `entry = 0x54 + table[c >> 12] × 0xC000 + (c & 0xFFF) × 12`.

| Entry offset | Type | Value |
|---|---|---|
| +0 | u16 | GIM picture (page) index, 0–6 |
| +2 | u16 | x in the page |
| +4 | u16 | y in the page |
| +6 | u8 × 4 | metrics: 13, 13, 13, 13 for a normal glyph; 3, 13, 3, 13 for `！` (width / height / advance) |
| +10 | s8 × 2 | x / y offset |

An all-zero entry means "no glyph". 1978 glyphs are defined.

## FMAP (`namefilterlist.dat`) ✅

Read by the function at 0x088F8950 in `EBOOT.BIN`. Banned-word list for player names.

| Offset | Type | Value |
|---|---|---|
| 0x00 | char[4] | `FMAP` |
| 0x04 | u32 | record size (17) |
| 0x08 | u32 | total record count (171) |
| 0x0C | u32 × 255 | record count per bucket; the bucket is the first byte of the word (Shift-JIS lead byte) |
| 0x408 | — | records, bucket after bucket |

Each record is a null-terminated Shift-JIS word padded to 17 bytes, **every byte XOR 0xFF**
(the 0x54 padding seen in the raw file is 0xAB after XOR). 0x408 + 171 × 17 = 3939 = file size.

## ucs2jis.bin / jis2ucs.bin ✅

Two lookup tables of 65536 × u16:
- `ucs2jis.bin`: index = Unicode code point, value = **JIS X 0208** code (row/cell, not Shift-JIS).
  U+3042 (あ) → 0x2422.
- `jis2ucs.bin`: the reverse. 0x2422 → U+3042, 0x306C → U+4E00 (一).

Python's `euc_jp` / `iso2022_jp` codecs give the same mapping, so these files are only needed by the
game itself.
