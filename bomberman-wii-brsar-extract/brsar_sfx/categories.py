"""Output folder names.

Bomberman Blast (Wii) labels are organised by prefix, so a readable folder is
picked from the label.  For any other game the folder falls back to the name
of the RSAR "player" the sound uses (e.g. ``PLY_SE_SYS``).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

BOMBERMAN_BLAST_RULES: List[Tuple[str, str]] = [
    (r"^SE_SYS_", "System"),
    (r"^SE_ACT_", "Player Actions"),
    (r"^SE_FIRE_", "Explosions"),
    (r"^SE_PNL_", "Power-Ups"),
    (r"^SE_SICK_", "Skull Ailments"),
    (r"^SE_APL_", "Taunts"),
    (r"^SE_GIM_", "Battle Gimmicks"),
    (r"^SE_RSLT_", "Results"),
    (r"^SE_ST_MENU_", "Story Mode - Shop & Menus"),
    (r"^SE_ST_CMN_", "Story Mode - Common"),
    (r"^SE_ST_ZK_", "Story Mode - Enemies"),
    (r"^SE_ST_BS_", "Story Mode - Bosses"),
    (r"^SE_ST_GIM_", "Story Mode - Stage Gimmicks"),
    (r"^SE_DMO_", "Story Mode - Cutscenes"),
    (r"^SE_HJ_", "Bomberman for Beginners"),  # HJ = Hajimete no Bomberman (tutorial)
    (r"^SEQ_MU", "Music"),
    (r"^SEQ_JG", "Jingles"),
    (r"^SE_", "Other"),
]

REMOTE_SUBFOLDER = "Wii Remote Speaker"


def folder_for(name: str, player_name: Optional[str], all_names: set) -> str:
    folder = None
    for pattern, f in BOMBERMAN_BLAST_RULES:
        if re.match(pattern, name):
            folder = f
            break
    if folder is None:
        folder = player_name or "Other"
    # "<NAME>_R" variants are the copies the game sends to the Wii Remote speaker
    if name.endswith("_R") and name[:-2] in all_names:
        folder = f"{folder}/{REMOTE_SUBFOLDER}"
    return folder

