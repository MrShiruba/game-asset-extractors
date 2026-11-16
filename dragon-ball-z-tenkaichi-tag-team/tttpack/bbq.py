"""
BBQ scripts (".BBQ1.00"): the Dragon Walker (story mode) stage scripts, one per chapter
part (PACKFILE entries 13274.. "sm_chNN_K"), run by a stack VM of the EBOOT.

Header: ".BBQ1.00", u32 hash, u32 0, u32 0x18, u32 section count, then one section per
5 u32: (type, table offset, entry count, data offset, data size), offsets from 0x18.
Section 6 is the code.

Instruction: u8 opcode, u8 flags, u8 operand count, u8 0, then the operand words.
    op 0x00 (flags 0x0C, 1 operand)  push a constant
    op 0x01 (flags 0x0C, 1 operand)  push a variable
    op 0x10                          OR of the 2 values on top of the stack
    op 0x2E (2 operands)             call native (native number, argument count)
    op 0x2D (4 operands)             call script function (0x10000 | number, address,
                                     argument count, argument bytes)
Natives and script functions used for the story (the script functions are the same
library compiled into every stage script; their numbers differ between releases, so
they are found by their arguments):
    function 15 (portrait entry, name, side 0 / 1)  puts a character on screen for the
        dialogue that follows: the portrait is a PACKFILE entry (13644.. "sm_hud_*"), the
        name a text id of the interface text table.
    function 16 (text id, side)    a dialogue line (text id in the chapter's text table),
                                   said by the character put on that side by function 15
    native 93 (text id)            a line in the message box (narration, tutorial)
    native 188 (enemy partner, enemy leader, player partner, player leader, ...)
        start a battle; characters as audio_map.STORY_CHARACTER_IDS numbers, -1 = nobody
"""
import collections
import struct

from . import audio_map

SCENE, SPEAKER, LINE, MESSAGE, BATTLE = "F7", "F15", "F16", "N93", "N188"
NAME_SHIFT = 0
CODE_SECTION = 6
PORTRAITS = (13644, 13733)     # "sm_hud_*" PACKFILE entries


def instructions(data):
    """Yield (offset in the code, opcode, flags, operands)."""
    if data[:8] != b".BBQ1.00" or len(data) < 0x40:
        return
    count = struct.unpack_from("<I", data, 0x14)[0]
    code = None
    for k in range(min(count, 32)):
        if 0x18 + 20 * (k + 1) > len(data):
            break
        kind, _, _, offset, size = struct.unpack_from("<5I", data, 0x18 + 20 * k)
        if kind == CODE_SECTION:
            code = (0x18 + offset, size)
    if code is None:
        return
    start, size = code
    end = min(start + size, len(data))
    pos = start
    while pos + 4 <= end:
        op, flags, count, zero = data[pos:pos + 4]
        if zero or pos + 4 + 4 * count > end:
            return
        yield pos - start, op, flags, list(struct.unpack_from("<%di" % count, data, pos + 4))
        pos += 4 + 4 * count


def calls(data):
    """Yield (name, args): 'N<native>' / 'F<function>', args = ints or None (not constant)."""
    stack = []
    for _, op, flags, ops in instructions(data):
        if op in (0, 1) and flags == 0x0C and len(ops) == 1:
            stack.append(ops[0] if op == 0 else None)
        elif op == 0x10 and len(stack) >= 2:
            b, a = stack.pop(), stack.pop()
            stack.append(a | b if a is not None and b is not None else None)
        elif op == 0x2E and len(ops) == 2:
            yield "N%d" % ops[0], stack[-ops[1]:] if ops[1] else []
            stack = []
        elif op == 0x2D and len(ops) == 4:
            yield "F%d" % (ops[0] & 0xFFFF), stack[-ops[2]:] if ops[2] else []
            stack = []
        elif op not in (0x28, 0x29):
            stack = []


def _character(number):
    from .official import official
    names = {k: official(v) for k, v in audio_map.CHARACTERS}
    if number is not None and 0 <= number < len(audio_map.STORY_CHARACTER_IDS):
        return names.get(audio_map.STORY_CHARACTER_IDS[number], "#%d" % number)
    return None


def dialogue_functions(events):
    """(speaker function, line function) of a script, found by their arguments: the
    numbers of the script functions differ between releases (JP: F15 / F16)."""
    speaker, line = collections.Counter(), collections.Counter()
    for name, args in events:
        if not name.startswith("F"):
            continue
        if len(args) == 3 and args[0] is not None and PORTRAITS[0] <= args[0] <= PORTRAITS[1]:
            speaker[name] += 1
        elif len(args) == 2 and args[0] is not None and 10000 <= args[0] < 20000 and args[1] in (0, 1):
            line[name] += 1
    return (speaker.most_common(1)[0][0] if speaker else SPEAKER,
            line.most_common(1)[0][0] if line else LINE)


def story_script(data, texts, interface=None, portrait_name=None):
    """Readable listing of the story events of a stage script, in script order.

    texts: the chapter's text table (Texts, .base = 10000); interface: the interface
    text table (speaker names); portrait_name: function(entry) -> name, as fallback.
    """
    from .text import readable

    def text(ident):
        k = ident - getattr(texts, "base", 0) if ident is not None and texts else -1
        if 0 <= k < len(texts) and texts[k] is not None:
            return readable(texts[k]).replace("\n", " ")
        return "#%s" % ident

    events = list(calls(data))
    speaker_fn, line_fn = dialogue_functions(events)
    lines, scene = [], {}
    for name, args in events:
        if name == speaker_fn and len(args) == 3:
            entry, who, side = args
            if side == 0 and lines and lines[-1] and not lines[-1].startswith("\t"):
                lines.append("")      # a new dialogue scene
                scene = {}
            speaker = None
            if interface and who is not None and 0 <= who + NAME_SHIFT < len(interface):
                speaker = interface[who + NAME_SHIFT]
            if not speaker and portrait_name and entry is not None:
                speaker = (portrait_name(entry) or "").replace("sm_hud_", "")
            scene[side] = speaker or "?"
        elif name == line_fn and len(args) == 2:
            lines.append("%s\t%s\t%s" % (args[0], scene.get(args[1], "?"), text(args[0])))
        elif name == MESSAGE and len(args) == 1:
            lines.append("%s\t[message]\t%s" % (args[0], text(args[0])))
        elif name == BATTLE and len(args) >= 4:
            enemy = [c for c in map(_character, (args[1], args[0])) if c]
            player = [c for c in map(_character, (args[3], args[2])) if c]
            lines.append("\t[battle]\t%s vs %s" % (" & ".join(player) or "?", " & ".join(enemy) or "?"))
    return "\n".join(lines) + "\n" if lines else ""
