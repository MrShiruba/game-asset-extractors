""".evt event scripts: dialogue export.

Layout: 8-byte header, then commands: u32 opcode, u32 payload size, payload.
Text commands (null-terminated Shift-JIS):
  0x32  speaker name          0x34  one line of dialogue
  0x36  end of message box    0x26  choice offered to the player
  0xEE  label                 0xEF  jump to a label
"""
import struct

OP_CHOICE, OP_SPEAKER, OP_LINE, OP_END_MSG = 0x26, 0x32, 0x34, 0x36
OP_LABEL, OP_JUMP = 0xEE, 0xEF


def commands(d):
    p = 8
    while p + 8 <= len(d):
        op, size = struct.unpack_from('<II', d, p)
        if p + 8 + size > len(d):
            raise ValueError('command at 0x%x runs past the end of the file' % p)
        yield p, op, d[p + 8:p + 8 + size]
        p += 8 + size
    if p != len(d):
        raise ValueError('%d trailing bytes' % (len(d) - p))


def _s(payload):
    return payload.split(b'\0')[0].decode('cp932', 'replace')


def evt_to_txt(d):
    """Dialogue of one script, in reading order. Returns '' if the script has no text."""
    out, speaker, msg = [], None, []

    def flush():
        if msg:
            out.append(('%s: ' % speaker if speaker else '') + msg[0])
            out.extend(' ' * (len(speaker) + 2 if speaker else 0) + l for l in msg[1:])
            msg.clear()

    has_text = False
    for _, op, pl in commands(d):
        if op == OP_SPEAKER:
            flush(); speaker = _s(pl) or None
        elif op == OP_LINE:
            msg.append(_s(pl)); has_text = True
        elif op == OP_END_MSG:
            flush(); speaker = None
        elif op == OP_CHOICE:
            flush(); out.append('  > ' + _s(pl)); has_text = True
        elif op == OP_LABEL:
            flush(); out.append(''); out.append('[%s]' % _s(pl))
        elif op == OP_JUMP:
            flush(); out.append('  -> %s' % _s(pl))
    flush()
    return ('\n'.join(out).strip('\n') + '\n') if has_text else ''
