"""
Who speaks the Dragon Walker (story mode) voices, worked out from the GSCF scripts.

Line ids (EBOOT 0x089C913C):
    id <  200 -> STORY_EPISODES[chapter].start + id   (episode lines)
    id >= 200 -> id - 114                              (shared lines, index 86..1003)

Each GSCF battle script lists, with native 19, which fighter slot says each line.
The shared lines come in blocks of consecutive ids that always go to the same slot:
one block per character (and a second, smaller block for most enemies).
A block's character is given by STORY_SHARED_NAMES (first index of the block, read from
the stage scripts); a block missing from the table
inherits the name of a named block that always shares its slot.
Episode lines then get the name of the block held by the same slot in that battle.
Native 7 also names the speaker of each line (story character number); that name is
used first, which also covers the lines with no fighter slot.
Lines that no script names at all are off-screen (narrator, voices off).
Finally, data/story_speakers.txt (every episode line, checked by ear) takes priority.
Shared lines that no script uses at all (neither native 7 nor native 19) are cut content.
"""
import collections
import os

from . import audio_map
from .gscf import battle_info

SHARED_OFFSET = 114
OFFSCREEN = "offscreen"


class StoryInfo:
    def __init__(self):
        self.shared_blocks = []      # (first index, end index exclusive, name)
        self.episode_speakers = {}   # PACKFILE index -> name
        self.offscreen_shared = set()   # shared lines spoken with no fighter slot
        self.shared_speakers = {}    # PACKFILE index -> name, for those lines

    def shared_block(self, index):
        for start, end, name in self.shared_blocks:
            if start <= index < end:
                return start, name
        return None

    def episode_speaker(self, index):
        return self.episode_speakers.get(index, OFFSCREEN)


def _runs(items):
    """Consecutive (index, slot) pairs with the same slot -> [(first, last, slot)]."""
    runs = []
    for index, slot in sorted(items):
        if runs and index == runs[-1][1] + 1 and slot == runs[-1][2]:
            runs[-1][1] = index
        else:
            runs.append([index, index, slot])
    return runs


def analyse(scripts):
    """scripts: iterable of GSCF file contents. Returns a StoryInfo."""
    battles, spoken = [], set()
    explicit = collections.defaultdict(collections.Counter)   # index -> speaker votes
    by_id = dict(audio_map.CHARACTERS)
    for data in scripts:
        voiced = []
        chapter, speakers = battle_info(data, spoken, voiced)
        if chapter is not None:
            chapter = min(chapter, len(audio_map.STORY_EPISODES) - 1)
            battles.append((chapter, speakers))
            start, end = audio_map.STORY_EPISODES[chapter]
            for line, number in voiced:
                if not 0 <= number < len(audio_map.STORY_CHARACTER_IDS):
                    continue
                name = by_id.get(audio_map.STORY_CHARACTER_IDS[number])
                index = start + line if line < 200 else line - SHARED_OFFSET
                if name and (line >= 200 or index < end):
                    explicit[index][name] += 1

    # Shared blocks and where (battle, slot) each one is used.
    extent, used = {}, collections.defaultdict(set)
    per_battle = []
    for b, (chapter, speakers) in enumerate(battles):
        shared = [(i - SHARED_OFFSET, s) for i, s in speakers.items() if i >= 200]
        starts = {}
        for first, last, slot in _runs(shared):
            extent[first] = max(extent.get(first, first), last + 1)
            used[first].add((b, slot))
            starts[slot] = starts.get(slot, []) + [first]
        per_battle.append(starts)

    names = dict(audio_map.STORY_SHARED_NAMES)
    for first in sorted(extent):
        if first not in names:
            match = [n for n in audio_map.STORY_SHARED_NAMES if used[first] <= used.get(n, set())]
            names[first] = audio_map.STORY_SHARED_NAMES[match[0]] if len(match) == 1 else "unknown"
        if names[first] == "unknown":     # speaker given by native 7 for the block's lines
            votes = collections.Counter()
            for i in range(first, extent[first]):
                votes.update(explicit.get(i, {}))
            if votes:
                names[first] = votes.most_common(1)[0][0]
    info = StoryInfo()
    info.shared_blocks = [(first, extent[first], names[first]) for first in sorted(extent)]
    in_block = lambda i: any(a <= i < b for a, b in extent.items())
    info.offscreen_shared = {line - SHARED_OFFSET for line in spoken
                             if line >= 200 and not in_block(line - SHARED_OFFSET)}

    # Episode lines: name of the block held by the same slot in that battle (majority vote).
    votes = collections.defaultdict(collections.Counter)
    for (chapter, speakers), starts in zip(battles, per_battle):
        slot_name = {}
        for slot, firsts in starts.items():
            known = [names[f] for f in firsts if names[f] != "unknown"]
            if known:
                slot_name[slot] = known[0]
        start, end = audio_map.STORY_EPISODES[chapter]
        for line, slot in speakers.items():
            if line < 200 and start + line < end:
                votes[start + line][slot_name.get(slot, "unknown")] += 1
    for index, counter in votes.items():
        named = [(n, c) for n, c in counter.most_common() if n != "unknown"]
        info.episode_speakers[index] = named[0][0] if named else "unknown"

    # The speaker named by native 7 wins: it is given line by line, also for lines
    # with no fighter slot (and for a fighter replaced during the battle).
    for index, counter in explicit.items():
        name = counter.most_common(1)[0][0]
        if index >= audio_map.STORY_EPISODES[0][0]:
            info.episode_speakers[index] = name
        elif index in info.offscreen_shared:
            info.shared_speakers[index] = name
    info.episode_speakers.update(checked_speakers())
    return info


def checked_speakers():
    """{index: speaker} of the episode lines checked by ear (data/story_speakers.txt)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "story_speakers.txt")
    result = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                index, name = line.split("\t")
                result[int(index)] = name.strip()
    return result
