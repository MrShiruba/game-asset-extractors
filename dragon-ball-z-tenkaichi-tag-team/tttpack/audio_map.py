"""
Audio layout of PACKFILE.BIN for Dragon Ball Z Tenkaichi Tag Team (PSP, ULJS00311).

Maps a PACKFILE entry index to a sorted output path, e.g.
    4458 -> at3/battle/04441_goku/04458_017.at3

All tables below were read from the decrypted EBOOT (see tools/dump_eboot_tables.py):

  Battle voices (function 0x08852504):
      sound_id = 0x8910 + internal_id * 126 + line
      block    = BLOCK_TABLE[internal_id]       (161 bytes at file offset 0x265680)
      index    = 4441 + block * 126 + line      (70 blocks, 4441..13260)
      sound ids 0x8910..0x892D  -> index 4411..4440 (shared battle voices)
      sound ids 0x106F6..0x10713 -> index 4390..4419 (BGM, 21 tracks: 4390..4410)

  Menu voices 1379..1388 are referenced directly by menu code.
  Title screen (module 00012.elf): picks 74 or 75 at random, then 78 or 79.

  Story mode "Dragon Walker": the GSCF battle scripts give line ids, mapped by 0x089C913C:
      line id <  200 -> STORY_EPISODES[chapter].start + line id   (31 x (start, end) at 0x26C708)
      line id >= 200 -> line id - 114   (shared story lines, index 86..1003)
  Who says each story line is worked out from the scripts, see story.py.
  Shared lines that no script uses go to at3/story/unused/.

  Pre-battle dialogue 853..1003 (853 + n, EBOOT 0x08907498): see intro.py.
"""
import re

from . import names


VOICE_BASE = 4441
LINES_PER_CHARACTER = 126

# (internal character id, folder name), in voice block order (block 0..69).
CHARACTERS = [
    (3, "goku"), (4, "goku_ssj"), (5, "goku_ssj2"), (6, "goku_ssj3"),
    (13, "kid_gohan"), (14, "teen_gohan"), (15, "teen_gohan_ssj"), (16, "teen_gohan_ssj2"),
    (17, "gohan"), (18, "gohan_ssj"), (19, "gohan_ssj2"), (21, "ultimate_gohan"),
    (23, "piccolo"), (25, "krillin"), (26, "yamcha"), (27, "tien"), (28, "chiaotzu"),
    (29, "vegeta_scouter"), (34, "vegeta"), (35, "vegeta_ssj"), (36, "vegeta_ssj2"),
    (37, "majin_vegeta"),
    (44, "kid_trunks"), (45, "kid_trunks_ssj"), (39, "trunks_sword"), (40, "trunks_sword_ssj"),
    (41, "trunks_armor"), (42, "trunks_armor_ssj"),
    (56, "videl"), (46, "goten"), (47, "goten_ssj"), (49, "gotenks_ssj"), (50, "gotenks_ssj3"),
    (53, "gogeta_ssj"), (52, "vegito_ssj"),
    (73, "bardock"), (77, "raditz"), (79, "saibaman"), (80, "nappa"), (85, "cui"),
    (82, "zarbon"), (83, "zarbon_transformed"), (84, "dodoria"),
    (86, "ginyu"), (87, "recoome"), (90, "guldo"), (89, "jeice"), (88, "burter"),
    (91, "frieza_1st_form"), (92, "frieza_2nd_form"), (93, "frieza_3rd_form"),
    (94, "frieza_final_form"), (95, "frieza_full_power"),
    (100, "android_16"), (101, "android_17"), (102, "android_18"), (103, "android_19"),
    (104, "android_20"),
    (109, "cell_jr"), (105, "cell_1st_form"), (106, "cell_2nd_form"), (107, "perfect_cell"),
    (108, "super_perfect_cell"),
    (111, "dabura"), (112, "majin_buu"), (114, "super_buu"), (116, "super_buu_gohan_absorbed"),
    (117, "kid_buu"), (133, "broly_lssj"), (99, "frieza_soldier"),
]

# Internal names used by the game itself, in the same block order (debug menu
# "Debug Menu - Character Open" in PACKFILE entry 13269.bbq).
INTERNAL_NAMES = [
    "GOKU_3", "GOKU_4", "GOKU_5", "GOKU_6", "GOHAN_0", "GOHAN_1",
    "GOHAN_2", "GOHAN_3", "GOHAN_4", "GOHAN_5", "GOHAN_6", "GOHAN_7",
    "PICCOLO_1", "KRILLIN", "YAMCHA", "TIEN", "CHIAOTZU", "VEGETA_5",
    "VEGETA_6", "VEGETA_7", "VEGETA_3", "MAJIN_VEGETA", "TRUNKS_3", "TRUNKS_4",
    "TRUNKS_0", "TRUNKS_1", "TRUNKS_5", "TRUNKS_6", "VIDEL", "GOTEN_0",
    "GOTEN_1", "GOTENKS_1", "GOTENKS_2", "GOGETA_1", "VEGITO_1", "BARDOCK_0",
    "RADITZ_0", "SAIBAMEN", "NAPPA_0", "CUI", "ZARBON_0", "ZARBON_1",
    "DODORIA", "GINYU", "RECOOME", "GULDO", "JEICE", "BURTER",
    "FRIEZA_1", "FRIEZA_2", "FRIEZA_3", "FRIEZA_4", "FRIEZA_5", "ANDROID_16",
    "ANDROID_17", "ANDROID_18", "ANDROID_19", "ANDROID_20", "CELL_JR", "CELL_0",
    "CELL_1", "CELL_2", "CELL_3", "DABURA", "BUU_0", "BUU_2",
    "BUU_B", "BUU_3", "BROLLY_2", "FRIEZA_SOLDIER",
]

BATTLE_COMMON = range(4411, 4441)
BGM = range(4390, 4411)
MENU = range(1379, 1389)

# Mono entries that play at 44100 Hz instead of the default 22050 Hz (checked by ear).
RATE_44100 = [MENU, range(4425, 4435)]


def sample_rate(index, default):
    """Playback rate of a mono ATRAC3 entry."""
    return 44100 if any(index in r for r in RATE_44100) else default


OFFSCREEN = "offscreen"
TITLE = range(74, 86)
STORY_SHARED = range(86, 853)           # story line ids 200..966
BATTLE_INTRO = range(853, 1004)         # pre-battle dialogue, see intro.py
GSCF_SCRIPTS = range(13401, 13569)      # story battle scripts read by story.py

# Characters of the shared story line blocks, by first index of the block.
# Read from the game data: the Dragon Walker stage scripts
# (bbq, BBQ native 188) start each battle with 4 characters (enemy partner, enemy leader,
# player partner, player leader, as STORY_CHARACTER_IDS numbers) and a GSCF script; the
# GSCF script says which fighter slot speaks each shared block. Seeded with the blocks
# checked by ear (187..273); 13 blocks of single-fighter battles resolved by elimination.
STORY_SHARED_NAMES = {
    86: "goku", 102: "goku_ssj", 118: "goku_ssj2", 122: "goku_ssj3", 126: "kid_gohan",
    158: "teen_gohan_ssj", 162: "teen_gohan_ssj2", 181: "gohan_ssj", 184: "gohan_ssj2",
    187: "piccolo", 205: "krillin", 223: "yamcha", 239: "tien", 257: "chiaotzu",
    274: "vegeta_scouter", 290: "vegeta", 306: "vegeta_ssj", 326: "majin_vegeta",
    358: "trunks_sword_ssj", 378: "trunks_armor_ssj", 382: "kid_trunks", 403: "goten",
    423: "gotenks_ssj", 443: "vegito_ssj", 464: "bardock", 467: "raditz", 470: "nappa",
    475: "zarbon", 479: "zarbon_transformed", 483: "dodoria", 487: "ginyu", 503: "recoome",
    519: "burter", 535: "jeice", 553: "guldo", 556: "frieza_1st_form", 559: "frieza_2nd_form",
    566: "frieza_final_form", 572: "android_16", 588: "android_17", 607: "android_18",
    626: "android_19", 629: "android_20", 645: "android_17", 649: "cell_2nd_form",
    653: "perfect_cell", 659: "super_perfect_cell", 664: "majin_buu",
    674: "super_buu_gohan_absorbed", 678: "kid_buu", 682: "broly_lssj", 688: "vegito_ssj",
    693: "bardock", 698: "raditz", 703: "nappa", 708: "zarbon", 716: "zarbon_transformed",
    721: "dodoria", 726: "guldo", 731: "frieza_1st_form", 736: "frieza_2nd_form",
    746: "frieza_final_form", 756: "android_19", 761: "android_17", 766: "cell_2nd_form",
    771: "perfect_cell", 776: "majin_buu", 781: "super_buu", 786: "super_buu_gohan_absorbed",
    791: "broly_lssj", 801: "ultimate_gohan", 809: "saibaman", 817: "cui", 825: "cell_jr",
    833: "dabura", 841: "frieza_soldier",
}

# Shared story lines that no battle script gives to a fighter, checked by ear (their
# place in the blocks, which follow the roster order, gave the first guesses). Except
# 324 / 325, no story script plays them (cut content), but they are written with the
# other shared lines. used = played by a story script. (first index, end exclusive, name, used by a script)
SHARED_GAPS = [
    (142, 158, "teen_gohan", False), (178, 181, "gohan", False),
    (322, 326, "vegeta_ssj2", True), (342, 358, "trunks_sword", False),
    (362, 378, "trunks_armor", False), (399, 403, "kid_trunks_ssj", False),
    (419, 423, "goten_ssj", False), (427, 443, "gotenks_ssj3", False),
    (446, 464, "videl", False), (685, 688, "gogeta_ssj", False), (563, 566, "frieza_3rd_form", False),
    (569, 572, "frieza_full_power", False), (741, 746, "frieza_3rd_form", False),
    (751, 756, "frieza_full_power", False), (796, 801, "gogeta_ssj", False),
]


# Characters with few lines have two shared blocks: a small one in the first series
# (lines to the opponent: taunts, reactions) and one of 5 lines from 688 (lines to the tag
# partner: "hey, are you alright?", "well done"), checked by ear on Raditz. The big blocks
# of the main characters hold both kinds.
PARTNER_SERIES = range(688, 801)


def shared_folder_name(first, name):
    """Folder label of a shared block: '<name>', '<name>_to_partner' or '<name>_to_opponent'."""
    if first in PARTNER_SERIES:
        return name + "_to_partner"
    starts = sorted(set(STORY_SHARED_NAMES) | {g[0] for g in SHARED_GAPS} | set(SHARED_SPLITS)
                    | {PARTNER_SERIES.stop})
    names = dict(STORY_SHARED_NAMES, **{})
    names.update(SHARED_SPLITS)
    names.update((g[0], g[2]) for g in SHARED_GAPS)
    size = next((s - first for s in starts if s > first), 0)
    paired = any(names.get(s) == name for s in starts if s in PARTNER_SERIES)
    return name + "_to_opponent" if paired and size < 16 else name


# A block the battle scripts give to one fighter slot but that holds 2 characters
# (checked by ear): first index of the second part -> name.
SHARED_SPLITS = {669: "super_buu"}


def shared_gap(index):
    for first, end, name, used in SHARED_GAPS:
        if first <= index < end:
            return first, name, used
    return None


# Character numbers used by the stage scripts -> internal character id
# (85 u32 at EBOOT file offset 0x26C458; 70..84 are extra slots for repeated characters).
STORY_CHARACTER_IDS = [
    3, 4, 5, 6, 13, 14, 15, 16, 17, 18, 19, 21, 23, 25, 26, 27, 28, 29, 34, 35, 36, 37, 39, 40,
    41, 42, 44, 45, 46, 47, 49, 50, 52, 53, 56, 73, 77, 79, 80, 82, 83, 84, 85, 86, 87, 88, 89,
    90, 91, 92, 93, 94, 95, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 111, 112, 114,
    116, 117, 133, 34, 35, 79, 79, 79, 99, 99, 99, 109, 109, 109, 99, 99, 99, 99,
]

# (first index, end index exclusive) for story episodes 1..31.
STORY_EPISODES = [
    (1777, 1950), (1950, 2019), (2019, 2131), (2131, 2214), (2214, 2348), (2348, 2437),
    (2437, 2570), (2570, 2672), (2672, 2801), (2801, 2850), (2850, 2904), (2904, 2953),
    (2953, 3080), (3080, 3114), (3114, 3180), (3180, 3278), (3278, 3318), (3318, 3356),
    (3356, 3489), (3489, 3530), (3530, 3598), (3598, 3691), (3691, 3794), (3794, 3837),
    (3837, 3912), (3912, 3983), (3983, 4074), (4074, 4129), (4129, 4235), (4235, 4290),
    (4290, 4390),
]

def internal_name(index):
    """Internal name of the character an entry belongs to (its 5 files, its battle voices),
    e.g. 1427 -> 'GOKU_3'; None for other entries."""
    if CHARACTER_FILES <= index < CHARACTER_FILES + 5 * len(INTERNAL_NAMES):
        return INTERNAL_NAMES[(index - CHARACTER_FILES) // 5]
    if VOICE_BASE <= index < VOICE_BASE + LINES_PER_CHARACTER * len(INTERNAL_NAMES):
        return INTERNAL_NAMES[(index - VOICE_BASE) // LINES_PER_CHARACTER]
    return None


assert len(CHARACTERS) == len(INTERNAL_NAMES) == 70 and len(STORY_EPISODES) == 31

# Sound effect banks (see sound_bank.py). The bank loader 0x0885472C takes a slot bit:
#   battle (EBOOT 0x08855740): 0x10 = 13267 common battle bank,
#     0x40/0x80/0x100/0x200 = the 4 fighters, file 1427 + 5 * block + 4 (0x089C5F80;
#     k = 0..2 are the model/motion archives, k = 3 a small table),
#     0x20 = stage bank 1174 + 2 * stage (0x089C6098; 1173 + 2 * stage is the stage data).
#   Dragon Walker (module 13932, 0x08A95308): 0x4 = 13938, 0x2 = 73,
#     0x8 = 1140 + map, map = episode - 1 (0..30) or the 2 extra maps 31 and 32;
#     the same map number picks the map file 13273 + 3 * map.
#   Screens: the EBOOT preload lists (0x08830274 calls at 0x089C3B6C..0x089C4460) give
#     each menu module and its data entries; the bank is in the first data archive.
CHARACTER_FILES = 1427
FILES_PER_CHARACTER = 5
CHARACTER_BANK = 4
DW_MAP_BANKS = range(1140, 1173)        # 1140 + map number (0..32)
STAGE_BANKS = range(1174, 1194, 2)      # 1174 + 2 * stage number (0..9)
SOUND_BANKS = {
    # menu banks: the code gives the screen module (EBOOT preload lists), the
    # Editor_indice_Py list gives the screen name (see names.py)
    0: "system",               # loaded at boot with the common data of entry 0
    13: "title",               # module 12
    17: "main_menu",           # module 16, reloaded by every screen going back to the menu
    24: "free_battle",         # module 23 (it also loads the battle bank)
    34: "battle100",           # module 31 ("BTL100" layouts)
    40: "survival",
    48: "training",            # module 47
    56: "multiplayer",         # module 55 (ad hoc)
    57: "free_battle_multiplayer",
    65: "customize",           # module 64
    73: "menu_sfx",            # also slot 0x2 in the Dragon Walker module
    13267: "battle",
    13938: "dragon_walker",
    13951: "results",          # loaded by the Dragon Walker module
}


def classify(index, story=None, intro=None):
    """Return (category, group, line) for a PACKFILE index, or None if not audio.

    story:    optional story.StoryInfo (speakers worked out from the GSCF scripts)
    intro:    optional {index: (speaker, partner)} from intro.read_pairs
    category: battle, battle_common, story, story_shared, story_unused, battle_intro,
              bgm, menu, title
    group:    character name (battle), (episode number, speaker or None) (story),
              (first index, name) (story_shared), (speaker, partner) or None
              (battle_intro), else None
    line:     position inside the block / episode / range
    """
    last = VOICE_BASE + len(CHARACTERS) * LINES_PER_CHARACTER
    if VOICE_BASE <= index < last:
        block, line = divmod(index - VOICE_BASE, LINES_PER_CHARACTER)
        return "battle", CHARACTERS[block][1], line
    if index in BATTLE_COMMON:
        return "battle_common", None, index - BATTLE_COMMON.start
    if index in BGM:
        return "bgm", None, index - BGM.start
    for episode, (start, end) in enumerate(STORY_EPISODES, 1):
        if start <= index < end:
            speaker = story.episode_speaker(index) if story else None
            return "story", (episode, speaker), index - start
    if index in TITLE:
        return "title", None, index - TITLE.start
    if index in STORY_SHARED:
        block = story.shared_block(index) if story else None
        if block:
            for first, name in SHARED_SPLITS.items():
                if block[0] < first <= index < first + 5:
                    block = (first, name)
            return "story_shared", block, index - block[0]
        gap = shared_gap(index)
        if gap and story:
            first, name, used = gap
            return "story_shared", (first, name), index - first
        if story and index in story.offscreen_shared:
            return "story_shared", (index, story.shared_speakers.get(index, OFFSCREEN), "single"), 0
        if story:
            return "story_unused", None, index - STORY_SHARED.start
        return "story_shared", None, index - STORY_SHARED.start
    if index in BATTLE_INTRO:
        return "battle_intro", (intro or {}).get(index), index - BATTLE_INTRO.start
    if index in MENU:
        return "menu", None, index - MENU.start
    return None




def audio_relpath(index, ext="at3", story=None, intro=None):
    """Sorted relative output path for an audio entry, or None if the index is not audio
    (with the official character names, official.py)."""
    from .official import official
    path = _audio_relpath(index, ext, story, intro)
    return official(path) if path else None


def _audio_relpath(index, ext="at3", story=None, intro=None):
    c = classify(index, story, intro)
    if c is None:
        return None
    category, group, line = c
    # The entry index always comes first, so a file can be found by its index (e.g. 04396*).
    name = "%05d_%03d.%s" % (index, line, ext)
    if category == "battle":
        # Folder starts with the block's first index, so folders sort in game order.
        first = VOICE_BASE + (index - VOICE_BASE) // LINES_PER_CHARACTER * LINES_PER_CHARACTER
        label = names.battle_voice(line)
        if label:
            name = "%05d_%03d_%s.%s" % (index, line, label, ext)
        return "audio/battle_voice/%05d_%s/%s" % (first, group, name)
    if category == "story":
        episode, speaker = group
        if speaker:
            name = "%05d_%03d_%s.%s" % (index, line, speaker, ext)
        return "audio/story/ep%02d/%s" % (episode, name)
    if category == "bgm":
        label = names.entry(index)
        return "music/%05d_bgm%02d%s.%s" % (index, line, "_" + label if label else "", ext)
    if category == "story_shared":
        if group is None:
            return "audio/story/shared/%05d.%s" % (index, ext)
        if len(group) == 3:     # a line outside the blocks
            return "audio/story/shared/%05d_%s.%s" % (index, group[1], ext)
        name = "%05d_%03d_%s.%s" % (index, line, group[1], ext)      # line said by that character
        return "audio/story/shared/%05d_%s/%s" % (group[0], shared_folder_name(*group[:2]), name)
    if category == "battle_intro":
        if group:
            name = "%05d_%03d_%s_with_%s.%s" % (index, line, group[0], group[1], ext)
        return "audio/battle_intro/%s" % name
    if category == "story_unused":
        if group:
            name = "%05d_%03d_%s.%s" % (index, line, group[1], ext)
            return "audio/story/unused/%05d_%s/%s" % (group[0], group[1], name)
        return "audio/story/unused/%05d.%s" % (index, ext)
    label = names.entry(index)
    label = label[4:] if label and label.startswith("aud_") else label    # "aud_" = audio
    if category in ("menu", "title"):
        name = "%05d_%s.%s" % (index, label, ext) if label else "%05d.%s" % (index, ext)
        # title = voices (the title called out); menu = jingles of the menus
        return "%s/%s" % ("audio/title" if category == "title" else "menu", name)
    if label:
        name = "%05d_%03d_%s.%s" % (index, line, label, ext)
    if category == "battle_common":       # sound effects and jingles, not voices
        return "audio/battle_common/%s" % name
    return "audio/%s/%s" % (category, name)
