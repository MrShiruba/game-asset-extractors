"""
Character names as the game shows them (EU / US interface text table, entry 1 part 2:
character names at 1051.., forms at 1097.., roster screens at 982.. and 1039..),
written in lower case with "_". Every other spelling met in the PACKFILE lists, the
voice tables or the speaker data is mapped to these names, so one character has one
name everywhere in the output.
"""
import functools
import re

# The 70 playable characters, in block order (PACKFILE 1427 + 5 * block, voices 4441 +
# 126 * block); the internal names of the game are audio_map.INTERNAL_NAMES.
ROSTER = [
    "goku", "goku_super_saiyan", "goku_super_saiyan_2", "goku_super_saiyan_3",
    "kid_gohan", "teen_gohan", "teen_gohan_super_saiyan", "teen_gohan_super_saiyan_2",
    "gohan", "gohan_super_saiyan", "gohan_super_saiyan_2", "ultimate_gohan",
    "piccolo", "krillin", "yamcha", "tien", "chiaotzu",
    "vegeta_scouter", "vegeta", "vegeta_super_saiyan", "vegeta_super_saiyan_2", "majin_vegeta",
    "kid_trunks", "kid_trunks_super_saiyan", "trunks_sword", "trunks_sword_super_saiyan",
    "trunks_fighting_teen", "trunks_fighting_teen_super_saiyan",
    "videl", "goten", "goten_super_saiyan", "super_gotenks", "gotenks_super_saiyan_3",
    "super_gogeta", "super_vegito",
    "bardock", "raditz", "saibamen", "nappa", "cui", "zarbon", "zarbon_post_transformation",
    "dodoria", "captain_ginyu", "recoome", "guldo", "jeice", "burter",
    "frieza_1st_form", "frieza_2nd_form", "frieza_3rd_form", "frieza_final_form",
    "frieza_full_power",
    "android_16", "android_17", "android_18", "android_19", "dr_gero",
    "cell_jr", "cell_1st_form", "cell_2nd_form", "cell_perfect_form", "cell_super_perfect_form",
    "demon_king_dabura", "majin_buu", "super_buu", "super_buu_gohan_absorbed", "kid_buu",
    "broly_legendary_super_saiyan", "frieza_soldier",
]

# Characters that only appear in the story mode (portraits, speakers).
OTHERS = {
    "kaioshin": "supreme_kai", "kayoshin": "supreme_kai", "kibitoshin": "kibitokai",
    "satan": "hercule", "mr_satan": "hercule", "kaio": "king_kai", "kaiosama": "king_kai",
    "kamisama": "kami", "girl": "young_lady", "old_namekian": "namek_elder",
    "shenlong": "shenron", "freezer_soldier": "frieza_soldier", "soldier": "frieza_soldier",
    "gotenks": "super_gotenks", "bu": "buu",
}

# Names that contain a spelling above but are other characters.
KEEP = ("alien_soldier",)

# Spellings of the render list (rnd_*) that differ from the character archives.
RENDER_NAMES = {
    "goku_ssj1": "goku_super_saiyan_2", "goku_ssj2": "goku_super_saiyan_3",
    "trunks_future_base": "trunks_sword", "trunks_future_ssj": "trunks_sword_super_saiyan",
}


@functools.lru_cache(maxsize=None)
def aliases():
    """{spelling: official name}."""
    from . import audio_map, names
    table = dict(OTHERS)
    for block, official in enumerate(ROSTER):
        table[audio_map.CHARACTERS[block][1]] = official
        for k in (0, 4):
            label = names.entry(names.CHARACTER_FILES + 5 * block + k) or ""
            base = re.sub(r"^(char|sfx)_|_\d$", "", label)
            if base:
                table.setdefault(base, official)
    for spelling, official in list(table.items()):     # community "_base" forms
        if spelling.endswith("_base"):
            table.setdefault(spelling[:-5], official)
    # official names map to themselves, so that official() can run twice on a name
    # ("super_gotenks" must not become "super_super_gotenks")
    for official in list(ROSTER) + list(OTHERS.values()) + list(KEEP):
        table[official] = official
    return table


@functools.lru_cache(maxsize=None)
def _pattern():
    keys = sorted(aliases(), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(%s)(?![a-z0-9])" % "|".join(map(re.escape, keys)))


def render(name):
    """Official name of a render (rnd_*), whose list spells some characters differently."""
    return official(RENDER_NAMES.get(name, name))


def official(text):
    """Replace every character spelling in a name or path by the official name."""
    if not text:
        return text
    table = aliases()
    return _pattern().sub(lambda m: table[m.group(1)], text)
