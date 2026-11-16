"""
Output folder of each non-audio PACKFILE entry, by category (voices and music:
audio_map.py). Entries kept side by side in the PACKFILE share a folder (a translated
entry sits next to its other language copies, the language is in its name: _jp, _en,
_es, _fr, _de, _it). The entry index always starts the
file / folder name of the entry itself.

    character/fighters/FFFFF_<character>/   the 4 files (costumes: model, textures,
                                   animations, parameters, effects...) and the sound bank
                                   of one roster character (FFFFF = first entry of its block)
    character/render/              the 70 renders (one image per character)
    stage/FFFFF_<stage>/           a battle stage: data, sound bank
    stage/backgrounds/             14091..14095: backgrounds of 5 stages
    story_mode/<part>/             the Dragon Walker (story mode): scripts, board, sounds,
                                   portraits, screens, tutorial, effects, ui, dragon_walker
    menu/<screen>/                 a menu screen: program module, archive, script;
                                   menu/ = their sound bank and jingles
    audio/battle_common/           battle sounds (with the voices: audio_map.py)
    battle/                        battle interface (6 languages) and battle sound bank
    system/                        system archives (6 languages), boot screen (module,
                                   logos, script)
    character/extra/               fusion cut-scenes, props of special moves
    program/                       program modules (.elf) of no screen
    padding/                       14096: the UMD filler
    other/                         anything else
"""
import re

from . import names, official

LANGS = {"ja": "jp", "jp": "jp", "en": "en", "es": "es", "fr": "fr", "dr": "fr", "de": "de",
         "it": "it"}
CHARACTER_BLOCKS = range(1427, 1777)       # 70 characters x (4 costumes + sound bank)
RENDERS = range(14020, 14090)              # rnd_*: one per character (not in roster order)
STAGES = range(1173, 1193)                 # map_* / sfx_* of the 10 battle stages
PADDING_ENTRY = 14096
# boot screen (module, encrypted data, logos, script) and the test / debug scripts
# (the test / debug scripts 13268..13270 and 13400 are stored among the story scripts,
# in the block of BBQ scripts 13268..13570: they go with them)
BOOT_AND_DEBUG = set(names.MENU_SCREENS["boot"]) | {8}


def split_language(label):
    """'menu_training_fr' -> ('menu_training', 'fr'); no language -> (label, None)."""
    m = re.match(r"(.*)_(ja|jp|en|es|fr|dr|de|it)$", label or "")
    if m:
        return m.group(1), LANGS[m.group(2)]
    return label or "", None


def _character_folder(block):
    first = CHARACTER_BLOCKS.start + 5 * block
    return "character/fighters/%05d_%s" % (first, official.ROSTER[block])


def _stage_folder(name):
    for index in STAGES:
        label = names.entry(index) or ""
        if label.startswith("map_") and label[4:] == name:
            return "stage/%05d_%s" % (index, official.official(name))
    return "stage"


def entry_folder(index, label, ext):
    """Folder (relative to the output) of a non-audio entry. Entries the PACKFILE keeps
    side by side stay in the same folder: the 6 language copies of a menu archive sit
    in their screen's folder (00024_free_battle_jp ... 00029_free_battle_it), the
    language is only in the name."""
    base, lang = split_language(label)
    if index == PADDING_ENTRY:
        return "padding"
    if index in CHARACTER_BLOCKS:
        return _character_folder((index - CHARACTER_BLOCKS.start) // 5)
    if index in RENDERS:
        return "character/render"
    if index in STAGES:
        return _stage_folder(re.sub(r"^(map|sfx)_", "", base))
    if base.startswith("bg_map_"):     # 14091..14095, after the renders: one folder
        return "stage/backgrounds"
    if base == "system" or index in BOOT_AND_DEBUG:
        return "system"
    for screen, indices in names.MENU_SCREENS.items():
        if index in indices:
            # the install data screen (10, 11, archive 15) goes with the title screen
            # (12..14): stored between them, and the title module loads archive 15
            return "menu/%s" % ("title" if screen == "install_data" else screen)
    if ext == "elf" and not 13932 <= index < 13937:
        return "program"
    if base == "menu_sfx":
        return "menu"
    if base == "menu_install_data":    # 15: loaded by the title module (12), with 13
        return "menu/title"
    if base == "menu_free_battle_multiplayer":     # 57..62, inside multiplayer (55..63)
        return "menu/multiplayer"
    if base.startswith("menu_") and base != "menu_story_mode":
        return "menu/%s" % base[5:]
    if index < 100:
        return "menu"
    if base in ("battle_ui", "sfx_battle"):        # 13261..13267
        return "battle"
    if base.startswith(("ex_fus_", "ex_char_")):
        return "character/extra"     # 1389..1426, right before the characters (1427..)
    if base.startswith(("sm_", "story_")) or 13268 <= index < 13571 or 1140 <= index < 1173 \
            or 13932 <= index < 13937 or base == "menu_story_mode":
        return "story_mode/%s" % story_part(index, base, ext)
    return "other"


STORY_PARTS = (
    ("sm_hud_", "portraits"),
    ("sm_obj_", "board"), ("sm_map_", "board"), ("sm_minimap_", "minimaps"),
    ("sm_ui", "ui"), ("sm_game_over", "ui"),     # 13939..13950: 6 languages each
    ("sm_bg_", "screens"),               # 13984..13993: stage backgrounds of the story
    ("sm_sfx", "sounds"),
    ("story_frame_", "screens"), ("sm_title", "screens"), ("sm_img", "screens"),
    ("sm_tut_", "tutorial"), ("sm_vfx", "effects"),
    ("menu_story_mode", "ui"), ("sm_results", "ui"),
)


def story_part(index, base, ext):
    """Sub-folder of a story mode entry:
    scripts/   chapter scripts (.bbq + .txt), battle scripts (.gscf), other scripts
    board/     the Dragon Walker boards, the pieces and objects on them
    minimaps/  the mini-maps (14016..14019)
    chapter_texts/ the first text set (1193..1378: sm_txt_chNN, 6 languages)
    texts/     the second one (13734..13931: per language sm_txt, the 31 chapters, credits)
    sounds/    sound banks of the boards and the common one
    portraits/ faces of the dialogue boxes
    screens/   frames and artwork of the screens, chapter titles, images
    dragon_walker/ 13932..13936: the story mode screen: its module (.elf), archive,
               script and two small scripts, as a menu screen
    tutorial/, effects/, ui/"""
    if 13932 <= index < 13937:       # like a menu screen: module, archive, script (+ 2 small)
        return "dragon_walker"
    if 1193 <= index < 1379:         # first text set: sm_txt_chNN, 31 chapters x 6 languages
        return "chapter_texts"
    if 13734 <= index < 13932:       # second set, per language: sm_txt, chapters, credits
        return "texts"
    for prefix, part in STORY_PARTS:
        if base.startswith(prefix):
            return part
    return "scripts"


def top_folder(index, label, ext):
    return entry_folder(index, label, ext).split("/")[0]
