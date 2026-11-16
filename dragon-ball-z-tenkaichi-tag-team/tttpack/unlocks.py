"""
Unlock lists (system archive parts 28..35, see FORMATS.md) as text (--txt).
"""
import struct

KINDS = {0: "character", 1: "stage?", 5: "customize item", 6: "customize item (shop?)"}
REQUIREMENT = {
    "unlocks_by_story": "Dragon Walker stage cleared",
    "unlocks_by_count": "count (1000 = all)",
    "battle_100_rewards_1": "100 Battles flag",
    "battle_100_rewards_2": "100 Battles flag",
    "battle_100_rewards_3": "100 Battles flag",
    "unlocks_by_battles_played": "battles played",
    "reward_all_items": "every item owned",
    "starting_items": "none",
}


def to_text(data, name):
    if name not in REQUIREMENT or len(data) < 4:
        return None
    count = struct.unpack_from("<I", data)[0]
    if 4 + 12 * count > len(data):
        return None
    lines = ["%s: %d entries (requirement: %s; -1 = never by this list)" % (name, count, REQUIREMENT[name]),
             "kind;number;requirement"]
    for k in range(count):
        kind, number, need = struct.unpack_from("<Iii", data, 4 + 12 * k)
        lines.append("%s;%d;%d" % (KINDS.get(kind, "kind %d" % kind), number, need))
    return "\n".join(lines) + "\n"
