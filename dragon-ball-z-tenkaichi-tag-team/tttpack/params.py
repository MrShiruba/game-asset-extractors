"""
Character parameter files (parts of the character archives), worked out by comparing
the 148 character archives (70 different data sets: the 3 costumes share theirs).

blast_param (part 23, 640 bytes), little-endian:
    0x184 3 x u32  damage of the 3 Blast 2 moves (2 special moves, then the ultimate)
    0x190 3 x u32  damage when guarded (always 30 %)
    0x19C 3 x u32  Ki cost (20000 = 1 Ki bar; matches the move list on every character)
skill_param (part 24, 256 bytes):
    0x94  2 x u8   Blast stock cost of the 2 Blast 1 (support) skills (matches the move list)
kidan_param (part 19, 768 bytes): ki blasts, 12 blocks of 0x38 bytes from 0x04
    (3 sets of 4: a rapid shot, then 3 charge levels), each:
    +0x00 u32 damage, +0x04 u32 damage when guarded (20 %), +0x08 u32 Ki cost,
    +0x0C f32 speed
common_param (part 17, 256 bytes):
    0x2C u32 maximum Ki (100000 = 5 bars, every character)
    0x84 f32 damage taken multiplier (1.2 for the soldier, 0.9 for Broly; checked in game:
         the soldier loses 1.2 times as much health as Goku from the same attack)
    0x24 u32 health (30000; 40000 for Gogeta, Vegito, Nappa, Recoome, Broly; checked in game)
    0x7C f32 attack multiplier (1.70 for Broly, 1.05 for Goku; checked in game)
    0x28 u32 Ki at the start of a battle (0 for Androids 16 / 17; checked in game)
    0x38 u32 Ki charge speed (150 for the Androids, who cannot charge; checked in game)
    0x40 u32 Ki recovered on its own (highest for Androids 16 / 17 / 18; checked in game)
    field below is likely but not proven, and is marked "?" in the table:
    0x6C f32 power rank (10 for Yamcha, Guldo, the soldier; 35-36 for Gogeta, Vegito, Broly)
The other files (melee_param: 177 records of 48 bytes whose +4 is the damage of a hit;
movement_param: speeds as floats; com_param: computer AI; camera_param; patch_param;
hurtbox; voice_speaker) are kept raw.
"""
import struct

KI_BAR = 20000
STAT_FILES = ("blast_param", "skill_param", "common_param", "kidan_param", "move_list_name")


def _u32(data, off, n=1):
    return list(struct.unpack_from("<%dI" % n, data, off))


def _f32(data, off):
    return round(struct.unpack_from("<f", data, off)[0], 3)


def character_stats(files, moves, texts):
    """One row (dict) of stats for a character, from its parameter files.

    files: {"blast_param": bytes, ...}; moves: read_move_list() records; texts: the
    interface text table (for the move names), or None.
    """
    from .movelist import TEXT_BASE
    from .text import readable

    def name(k):
        k += TEXT_BASE
        if texts and 0 <= k < len(texts) and texts[k] is not None:
            return readable(texts[k])
        return "#%d" % (k - TEXT_BASE)

    specials = [m for m in moves if m[0] == 0] if moves else []
    row = {}
    skill = files.get("skill_param")
    for k in range(2):
        row["blast1_%d" % (k + 1)] = name(specials[k][1]) if len(specials) > k else ""
        row["blast1_%d_stock" % (k + 1)] = skill[0x94 + k] if skill and len(skill) >= 0x96 else ""
    blast = files.get("blast_param")
    if blast and len(blast) >= 0x1A8:
        damage, guard, ki = _u32(blast, 0x184, 3), _u32(blast, 0x190, 3), _u32(blast, 0x19C, 3)
        for k, label in enumerate(("blast2_1", "blast2_2", "ultimate")):
            row[label] = name(specials[2 + k][1]) if len(specials) > 2 + k else ""
            row[label + "_damage"] = damage[k]
            row[label + "_guarded"] = guard[k]
            row[label + "_ki_bars"] = ki[k] / KI_BAR
    common = files.get("common_param")
    if common and len(common) >= 0x88:
        row["max_ki_bars"] = _u32(common, 0x2C)[0] / KI_BAR
        row["health"] = _u32(common, 0x24)[0]
        row["start_ki_bars"] = _u32(common, 0x28)[0] / KI_BAR
        row["ki_charge"] = _u32(common, 0x38)[0]
        row["ki_regen"] = _u32(common, 0x40)[0]
        row["power_rank?"] = _f32(common, 0x6C)
        row["attack_mult"] = _f32(common, 0x7C)
        row["damage_taken_mult"] = _f32(common, 0x84)
    kidan = files.get("kidan_param")
    if kidan and len(kidan) >= 0x04 + 4 * 0x38:
        for k, label in enumerate(("rapid", "charge1", "charge2", "charge3")):
            row["ki_blast_%s_damage" % label] = _u32(kidan, 0x04 + k * 0x38)[0]
    return row


def stats_csv(rows):
    """rows: [(index, label, row)] -> CSV text (';' separated, like index.csv)."""
    columns = []
    for _, _, row in rows:
        for c in row:
            if c not in columns:
                columns.append(c)
    lines = [";".join(["index", "character"] + columns)]
    for index, label, row in rows:
        lines.append(";".join(["%05d" % index, label] + [str(row.get(c, "")) for c in columns]))
    return "\n".join(lines) + "\n"
