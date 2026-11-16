"""
Descriptive names from the community lists of Editor_indice_Py (kastomd, Apache-2.0),
stored unchanged in tttpack/data/editor_indice_py/ (see NOTICE.txt there).

The lists were made on the US release, which has the same 14097-entry layout as the
Japanese one. They number everything from 1; the functions here take ttt-unpack's
0-based numbers. Where the game code could be checked (battle voice events, sound bank
programs, character archive parts) the lists agree with it.
"""
import functools
import os
import re
import struct

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "editor_indice_py")

_ITEM = re.compile(r"^\s*(\d+)[-_][0-9A-Fa-f]+(?:\.unk)?:\s*(.+?)\s*$")


def _clean(name):
    """'002_model.pmdl' -> 'model', '4442_001_intro_1_m_.unk' -> 'intro_1'."""
    name = re.sub(r"\.[A-Za-z0-9]+$", "", name)
    name = re.sub(r"_m_?$", "", name)
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    name = re.sub(r"(^|_)sytem(?=_|$)", r"\1system", name)      # typo in LISTA_PACKFILE.txt
    name = re.sub(r"_dr$", "_fr", name)                          # typo (menu_..._dr)
    return re.sub(r"_ja(?=_|$)", "_jp", name)                     # one code for Japanese: jp


@functools.lru_cache(maxsize=None)
def _read(filename):
    """{0-based number: raw name} of one list."""
    items = {}
    path = os.path.join(DATA, filename)
    if not os.path.isfile(path):
        return items
    with open(path, encoding="utf-8-sig", errors="replace") as src:
        for line in src:
            m = _ITEM.match(line)
            if m:
                items[int(m.group(1)) - 1] = m.group(2)
    return items


def _lookup(filename, number):
    raw = _read(filename).get(number)
    if raw is None:
        return None
    name = _clean(raw)
    # entries the list only names by their own index ("13274_33DA.bbq") carry no information
    if not name or re.fullmatch(r"[0-9a-f]+", name) or name in ("unknown", "unk"):
        return None
    return name


# Entries the list leaves unnamed, named from the game: the jumps between the menu
# scripts (native 0 / native 1 of the BBQ VM take the PACKFILE index of the next script),
# the item list of the debug menu (13269: "Battle Test", "DragonWalker", "Boot", "Title",
# "MainMenu", "FreeBattle", "BattleSelection", "BattleNetwork", "Customize", "Training",
# "Option", "MiniGame Test", in that order next to their indices) and the stage list of
# the story mode script (13934: "Stage00".."Stage32" -> 13272 + 3 * k).
# Each menu screen is a program module (.elf, loaded first), its archive (menu_*) and its
# BBQ script.
MENU_SCREENS = {
    "boot": (6, 7, 9), "install_data": (10, 11), "title": (12, 14), "main": (16, 18, 19),
    "settings": (20, 22), "free_battle": (23, 30), "battle_selection": (31, 33),
    "training": (47, 54), "multiplayer": (55, 63), "customize": (64, 71),
}
UNNAMED = {7: "boot_encrypted", 8: "boot_logos", 18: "main_stub_script",
           13268: "battle_test_script", 13269: "debug_menu_script",
           13270: "sys_test_script", 13400: "minigame_test_script",
           13271: "ch00_1", 13272: "ch00_2", 13273: "ch00_3",
           13932: "dragon_walker_module", 13934: "dragon_walker_script",
           13935: "small_script_1", 13936: "small_script_2",
           # palette images whose colours mark zones (like part 25 of the boards)
           13569: "region_map_1", 13570: "region_map_2",
           # GSCF battle scripts: the EBOOT uses 13401 when a battle has no script of
           # its own (0x885456c, 0x8855c9c); 13566..13568 are loaded by the chapter 31
           # script (13364) next to 13565 "ch31_6"
           13401: "default_battle_script", 13566: "ch31_7", 13567: "ch31_8", 13568: "ch31_9",
           # the EBOOT treats scripts from 13402 on as story battles (0x0885587C, story
           # mode): 13402 comes right before 13403 "ch01_1", so it is chapter 0's battle
           13402: "ch00_1"}
for _screen, _indices in MENU_SCREENS.items():
    for _index in _indices:
        UNNAMED.setdefault(_index, "%s_%s" % (_screen, "script" if _index == _indices[-1] else "module"))
# 13937 "effects" (28 .eedx): the "Effect..." debug menu of the Dragon Walker scripts
# (chNN_2) plays effect n for item n + 1 (item 0 is ">> Clear <<"); the names are the
# menu's, as the developers wrote them (the textures match: three explosions for
# Burst00..02, smoke for Smoke, lightning for Bind / Lightning...)
DW_EFFECTS = ["normal_move", "aura_zone_zoom", "aura_zone_action", "taiyouken", "kaikousen",
              "psychokinesis", "solution", "choco_beam", "kiwokesu", "kiaihou", "teleportation",
              "hit00", "hit01", "hit02", "bind", "fukitobi", "lightning", "chara_burst",
              "burst00", "burst01", "burst02", "smoke", "space_ship_fall", "saibamen_appear",
              "space_ship_leave", "lienwork", "icon", "boss_aura"]
DW_EFFECTS_ENTRY = 13937

# 13370..13399: 10 chapter triples that the story mode list does not launch. Their
# chapter script has no dialogue and no battle, and the 10 copies differ by one constant:
# empty boards. 13934 also names 10 stages "Stage01 if", "Stage03 if", "Stage04 if",
# "Stage07 if", "Stage13 if", "Stage17 if", "Stage27 if", "Stage28 if", "Stage29 if",
# "Stage31 if" that it never lists: most likely these, so they are named if_01..if_10.
for _k in range(10):
    for _part in range(3):
        UNNAMED[13370 + 3 * _k + _part] = "if_%02d_%d" % (_k + 1, _part + 1)


def entry(index):
    """Name of a PACKFILE entry, e.g. 1427 -> 'char_goku_base_1', 1174 -> 'sfx_wasteland'."""
    name = _lookup("LISTA_PACKFILE.txt", index)
    if name is None:
        return UNNAMED.get(index)
    raw = _read("LISTA_PACKFILE.txt")[index]
    # voice entries are named in that list as "<line>_<name>"; keep only the name
    if re.match(r"^\d+_\d{3}_", raw):
        return _clean(re.sub(r"^\d+_", "", raw))
    return name


# How an entry name is shown in the output: the abbreviations of the list are dropped
# (the folder already says what the file is), the language stays at the end and
# characters get their official names (official.py). Applied in this order.
_SHOWN = [
    (r"^char_(.+)_(\d)$", lambda m, o: "%s_%s" % (o.official(m.group(1)), m.group(2))),
    (r"^rnd_(.+)$", lambda m, o: o.render(m.group(1)) + "_render"),
    (r"^(?:sfx_battle|menu_sfx|sm_sfx)$", lambda m, o: "sounds"),
    (r"^sm_sfx_pj_(\d+)$", lambda m, o: "map_%s_sounds" % m.group(1)),
    (r"^sfx_(.+)$", lambda m, o: o.official(m.group(1)) + "_sounds"),
    (r"^bg_map_(.+)$", lambda m, o: m.group(1) + "_background"),
    (r"^sm_bg_(.+)$", lambda m, o: m.group(1) + "_story_background"),
    (r"^map_(.+)$", lambda m, o: m.group(1)),
    (r"^battle_ui$", lambda m, o: "hud"),
    (r"^sm_hud_(.+)$", lambda m, o: o.official(m.group(1)) + "_portrait"),
    (r"^sm_obj_(.+)$", lambda m, o: o.official(m.group(1)) + "_map_object"),
    (r"^sm_map_(.+)$", lambda m, o: "map_" + m.group(1)),
    (r"^ex_fus_(.+)$", lambda m, o: o.official(m.group(1)) + "_fusion"),
    (r"^ex_char_(.+)$", lambda m, o: m.group(1) + "_prop"),
    (r"^sm_txt_ch(\d+)$", lambda m, o: "ch%s_text" % m.group(1)),
    (r"^sm_title_ch(\d+)$", lambda m, o: "ch%s_title" % m.group(1)),
    (r"^sm_ch(\d+)_(\d+)$", lambda m, o: "ch%s_%s" % m.groups()),
    (r"^sm_txt_credits$", lambda m, o: "credits_text"),
    (r"^sm_txt$", lambda m, o: "text"),
    (r"^sm_vfx$", lambda m, o: "effects"),
    (r"^sm_tut_img_(\d+)$", lambda m, o: "tutorial_%s" % m.group(1)),
    (r"^(?:menu|sm|aud)_(.+)$", lambda m, o: m.group(1)),
]


def shown(label):
    """Output name of an entry label, e.g. 'sm_hud_picoro' -> 'piccolo'."""
    from . import official
    if not label or label == "extra":       # 14096 "extra" = the UMD filler: no name
        return None
    lang = re.search(r"_(jp|en|es|fr|de|it)$", label)
    label = label[:lang.start()] if lang else label
    for pattern, make in _SHOWN:
        m = re.match(pattern, label)
        if m:
            label = make(m, official)
            break
    # the language copies of an entry sit side by side: the language ends the name
    return official.official(label) + (lang.group(0) if lang else "")


def display(index):
    """Output name of a PACKFILE entry (None if the list has no name for it)."""
    return shown(entry(index))


def battle_voice(line):
    """Battle voice line 0..125 of a character block, e.g. 0 -> 'intro_1'."""
    return _lookup("LISTA_VO_TTT.txt", line)


CHARACTER_FILES, FILES_PER_CHARACTER, CHARACTERS = 1427, 5, 70
STORY_MENU = 13933
EFFECT_COMMON = 495


# Parts of the system archives (entries 0..5, one per language) that no list names,
# named from what they hold (looked at on the JP release): {part: (name, size or "tex")}.
# A part is named only if its type / size is the one seen, in case a language differs.
SYSTEM_PARTS = {
    6: ("button_icons", "tex"),          # the button icons of the font (U+FF67 + k)
    8: ("loading_screen", "tex"),        # "Dragon Ball Tag VS" logo, "Now Loading"
    11: ("loading_parts", "tex"),        # leaves, digits, D-point gauge of the loading screen
    48: ("aura", "tex"), 49: ("aura_colors", "tex"), 51: ("beam", "tex"),
    52: ("sparks", "tex"), 54: ("smoke", "tex"), 55: ("small_aura_colors", "tex"),
    56: ("debris", "tex"), 57: ("rocks", "tex"),
    613: ("glow", "tex"), 614: ("ki_swirls", "tex"), 616: ("blue_noise", "tex"),
    618: ("red_noise", "tex"), 635: ("glow_colors_1", "tex"), 647: ("glow_colors_2", "tex"),
    650: ("smoke_1", "tex"), 652: ("smoke_2", "tex"),
    # same layouts as parts 021 / 022 of the stage archives (a colour; a colour + floats)
    619: ("lighting", 64), 620: ("ambient_color", 64),
    # settings of the three effects the program draws with parts 48..57 (EBOOT: the
    # loaders read parts 49 / 48 + 47, 51 / 52 + 50 and 55 / 54 + 53 together)
    # customization items, 64 bytes each (EBOOT: a script native sets the "owned" and
    # "new" flags of item n in the save data from record n; the equipped items' records
    # add their bonuses to the fighter)
    37: ("customize_items", 25088),
    # one 16-byte record per character: u32 base health (30000, the fighter's maximum
    # health is this plus the bonuses of the equipped items, at least 10000), 3 more u32
    43: ("character_base_stats", 2624),
    # the computer opponent (COM): 36 = one 60-byte record per character id (its
    # default AI type 0..2 — the "AI" items 171..195 replace it by 4..28 —, ki
    # thresholds, distances); 39 = the AI data: rule lists and one table of action
    # odds (rows of percentages adding up to 100) per AI type
    36: ("com_character_settings", 9664), 39: ("com_ai", 71424),
    # 28..35: what the game gives (characters, items...) and when. Same layout: u32
    # count, then 12-byte records u32 kind (0 = character: a bit of the save data's
    # unlocked characters; 5 / 6 = customization items, numbers of part 37), u32
    # number, u32 requirement (-1 = never by this list). The EBOOT's reward checker
    # (0x08A3419C) loads list n with 0x08A322A4 (part 28 + n) and runs one function
    # per list (0x08A338FC...); the requirement means:
    #   28 the Dragon Walker stage that must be cleared (story flags table 0x08A74DF0)
    #   29 a count of the checker (+0x20C) to reach, 1000 = when it reaches its total
    #   30..32 the 100 Battles results kept by module 31 (save data +0x52CC flags:
    #      12 for 30, 3 for 31 — set at 1, 5, 10 —, 2 for 32)
    #   33 the number of battles played (save data +0x21A8, +1 after each battle)
    #   34 every customization item owned
    #   35 nothing: given at the start
    28: ("unlocks_by_story", "list"), 29: ("unlocks_by_count", "list"),
    30: ("battle_100_rewards_1", "list"), 31: ("battle_100_rewards_2", "list"),
    32: ("battle_100_rewards_3", "list"), 33: ("unlocks_by_battles_played", "list"),
    34: ("reward_all_items", "list"), 35: ("starting_items", "list"),
    # read into each fighter (0x089B3920): a camera move that replaces the character's
    # part 41 "camera_win" (same slot of the fighter data), and bone positions (x, y, z)
    # used instead of the default skeleton of the EBOOT (0x08A6EA28) to adapt
    # animations (0x089B0054)
    45: ("win_camera", 768), 46: ("reference_skeleton", 896),
    # same 36-byte records as part 27 "camera_param" of the character archives: the
    # camera code (0x08919CD0) reads the character's table or this common one
    40: ("camera_param", 1472),
    # one u32 of flags per animation slot of the character layout (the 414 animations,
    # parts 50..463): the battle code tests bits of entry n, n < 414 (0x08914A04...)
    38: ("animation_flags", 1792),
    # one 8-byte record per voice event of a fight (0x08942240): s16 first battle voice
    # line, s16 number of lines to pick from at random, float time before the event can
    # speak again (seconds, x30 frames) — the ranges match the 126 battle lines
    # (40 switch_out, 41 switch_in, 43..44 throw_evade...)
    41: ("battle_voice_events", 512),
    # 24-byte records for the fighter actions numbered from 126 (0x08948D94: action
    # n reads record n - 126 and copies its values into the fighter); byte 0x13 = a bit
    # of the character's common_param +0x20 flags that the action needs (0xFF = none)
    42: ("action_settings", 1536),
    # 20-byte records: 4 lists of up to 4 motion numbers (0xFF = none) and a type
    # (byte 2); each character's blast_param +0x229 picks one record for each of its
    # Blast 2 attacks and its ultimate (0x089A242C)
    44: ("blast_types", 384),
    47: ("aura_settings", 4224), 50: ("beam_settings", 192), 53: ("small_aura_settings", 2688),
    # a particle effect driven by the program (no effect header): 3 particle settings
    # (same 768-byte layout as effect.py) and 7 colour tables, one per colour of the
    # glow_colors textures
    651: ("particles_1", 768), 653: ("particles_2", 768), 654: ("particles_3", 768),
}
SYSTEM_PARTS.update({655 + k: ("particles_colors_%d" % (k + 1), 320) for k in range(7)})
# loaded together by the effect code of the EBOOT (getSysPart(n + 1) = part n):
# 0x088BCF88: parts 614 ki_swirls, 615, 616 blue_noise, 617 (two DBES meshes);
# 0x088D1E00: 635 glow_colors_1, 636 (8 colour keys) and 637..646 (10 records);
# 0x088F2148: 647 glow_colors_2, 648 (colour keys), 649, then 650..661 (particles above)
SYSTEM_PARTS.update({
    615: ("swirl_mesh_1", ".dbes"), 617: ("swirl_mesh_2", ".dbes"),
    636: ("glow_1_colors", 128), 648: ("glow_2_colors", 192), 649: ("glow_2_settings", 128),
})
SYSTEM_PARTS.update({637 + k: ("glow_1_settings_%d" % (k + 1), 128) for k in range(10)})


def system_part(index, path, data):
    """Name of a part of a system archive (entries 0..5), checked against its content."""
    if not 0 <= index <= 5 or len(path) != 1 or path[0] not in SYSTEM_PARTS:
        return None
    from . import texture
    name, kind = SYSTEM_PARTS[path[0]]
    if kind == "tex":
        return name if texture.decode(data) else None
    if kind == ".dbes":
        return name if data[:4] == b"DBES" else None
    if kind == "list":
        count = struct.unpack_from("<I", data)[0] if len(data) >= 4 else -1
        return name if 0 < count and 4 + 12 * count <= len(data) else None
    return name if len(data) == kind else None


# Story mode board objects (sm_obj_*, character layout): the animations are the 32
# motions of the board, in the order of the "Motion..." debug menu of the chNN_2
# scripts (the same order the Dragon Walker module plays them by number: 0x12 is
# played with the charge effect, 0x14 with the full charge one).
BOARD_MOTION_FIRST = 50
BOARD_MOTIONS = (
    "stand", "search", "pick_up", "run_in", "run_loop", "dash_in", "dash_loop", "dash_out",
    "damage_f", "damage_b", "numb", "vanish_f", "vanish_down_f", "vanish_b", "vanish_down_b",
    "down", "get_up", "ap_00", "charge_in", "charge_loop", "charge_max", "skill_1", "skill_2",
    "skill_3", "skill_4", "skill_5_in", "skill_5_loop", "skill_5_out", "fatigue_in",
    "fatigue_loop", "fatigue_out", "down_loop")
# Their effect_common holds 5 EEDX effects in the colours of the character; the Dragon
# Walker module keeps them at +0x6C..+0x7C of the character (loader 0x08A8779C) and
# plays them in place of its common effects (13937): 0 on every character from its
# creation (0x08AAC9EC), 1 with the skills Kaiouken, Charge, Headbreaker, Rush,
# Novastrike and Tackle (skill table 0x08AED4F0), 2 with the motion charge_in
# (0x08AB1180), 3 with charge_max (0x08AB12BC), 4 kept by the character next to its
# aura (0x08A8A6B4; same layout as part 0).
BOARD_EFFECTS = ("aura", "skill_aura", "charge", "charge_max", "aura_2")

# Parts of language archives (every language), by the entry name without its language.
# 100 Battles / Survival menus: the board of the mode (13-word cells
# with links and a 10000 marker for 100 Battles; a grid of cell kinds 0 / 1 / 5 / 7
# for Survival) and the list of fights (11-word records: character, level, ...).
MODE_PARTS = {
    ("menu_battle_100", 0): "course_layout",
    ("menu_battle_100", 1): "opponents",
    ("menu_survival", 1): "course_layout",
    ("menu_survival", 2): "opponents",
    # battle interface (13261..13266): the pre-battle talks of special pairs of
    # characters (u16 count, then 16-byte records: voice, character, pose, 0, then
    # the same for the opponent; read at 0x0890551C, the voices played at 0x08907498)
    # and the camera moves of these talks, chosen from the two pose values (0x0890544C)
    ("battle_ui", 1): "special_matchups",
    **{("battle_ui", k + 2): "matchup_camera_%d" % (k + 1) for k in range(5)},
}


def archive_part(index, path, count, counts=()):
    """Name of a part of entry `index` (path = part numbers from the top, count = parts
    in its own archive, counts = part counts of the archives above it), for the archives
    the lists describe. The character layout (497 parts, patch.txt; part 495 is the
    effect_common sub-archive) is used by the 4 files of each roster character and by
    the other models of the game: story mode board objects (sm_obj_*), props and fusion
    cut-scenes (ex_*). The story mode menu archive 13933 has 63 parts."""
    board = (entry(index) or "").startswith("sm_obj_")
    if len(path) == 1 and count == 497:
        if board and BOARD_MOTION_FIRST <= path[0] < BOARD_MOTION_FIRST + len(BOARD_MOTIONS):
            return BOARD_MOTIONS[path[0] - BOARD_MOTION_FIRST]
        return _lookup("patch.txt", path[0])
    if board and counts[:1] == (497,) and path[0] == EFFECT_COMMON and len(path) == 2 \
            and count == len(BOARD_EFFECTS):
        return BOARD_EFFECTS[path[1]]
    if counts[:1] == (497,) and path[0] == EFFECT_COMMON:
        if len(path) == 2 and count == 11:
            # part 0: one bit per sub-archive present (bit k-1 = part k), e.g. 0x77
            special = {0: "contents", 5: "mesh"}
            return special.get(path[1]) or _lookup("05_effect_common.txt", path[1])
        if len(path) == 3 and path[1] == 5:      # a one-quad shape and its texture
            return ("mesh", "mesh_texture")[path[2]] if path[2] < 2 else None
        if len(path) == 3 and path[1] == 7:      # attack_cmans: camera moves of attacks
            return "attack_camera_%d" % (path[2] + 1)
    if index == DW_EFFECTS_ENTRY and len(path) == 1 and count == len(DW_EFFECTS):
        return DW_EFFECTS[path[0]]
    if len(path) == 1:
        mode = re.sub(r"_[a-z]{2}$", "", entry(index) or "")
        if (mode, path[0]) in MODE_PARTS:
            return MODE_PARTS[mode, path[0]]
    if index == STORY_MENU and len(path) == 1 and count == 63:
        return _lookup("menu_stroy_mode_pack.txt", path[0])
    return None


# Extensions of the data files that have no signature. The game names none of its files
# (the EBOOT holds no file name but PACKFILE.BIN), so these are ours, one per format;
# .dat for parameter and game tables, as in the community's lists (017_common_param.dat).
_DATA_EXTENSIONS = (
    (r"font_\d+px", "fnt"),                                   # fonts (identify._font)
    (r"fx\d+_effect", "fxh"),                                 # effect header
    (r"fx\d+_offsets", "fxo"),                                # effect item offsets
    (r"(fx\d+_[a-z_]+_\d+|glow_\d+|particles)(_\d+)?_colors|(particles|glow_\d+)_colors_\d+"
     r"|glow_colors_\d+|glow_\d+_colors", "fxc"),              # colour tables of the layers
    (r"fx\d+_[a-z_]+_\d+|glow_\d+_settings(_\d+)?|particles_\d+", "fxs"),  # layer settings
    (r"lighting|ambient_color", "lgt"),                        # stage lighting (64 bytes)
    (r"waypoints", "wpt"),
    (r"sky_meshes", "dbesl"),                                  # u32 count + DBES meshes
    (r"unlocks_by_[a-z_]+|battle_100_rewards_\d+|reward_all_items|starting_items", "unl"),
)


def data_extension(label):
    """Extension of a named data file that would otherwise be .bin."""
    for pattern, ext in _DATA_EXTENSIONS:
        if re.fullmatch(pattern, label):
            return ext
    return "dat"
