"""Dialogue extraction from Fate/tiger colosseum .pac scripts.

.pac files are bytecode: 4-byte instructions "25 GG OO 00" (GG = group, OO = opcode)
followed by their arguments. Strings are Shift-JIS (cp932) at the end of the file;
'/' is a line break. Known instructions:
  25 01 0E 00 <u32 offset>  -> setMessageLabel (dialogue line)
  25 03 11 00 <u32 offset>  -> GameSystemCommand.setVersusRuleMessageLabel (mission text)
Right after a dialogue line the script pushes the voice ID (float, parameter index 1)
and calls the voice routine; the ID indexes voiceidtable.pac.
"""
import csv
import os
import struct

OPCODES = {b"\x25\x01\x0e\x00": "dialogue", b"\x25\x03\x11\x00": "mission"}
DIALOGUE = b"\x25\x01\x0e\x00"
PUSH_PARAM_1 = b"\x25\x00\x07\x00\x04\x00\x00\x00\x01\x00\x00\x00\x10\x00\x00\x00"


def load_voice_table(path):
    """voiceidtable.pac: 32-byte records (u32 id, char[28] path), ends with FFFFFFFF."""
    voices = []
    if not os.path.exists(path):
        return voices
    d = open(path, "rb").read()
    for i in range(0, len(d) - 31, 32):
        idx = struct.unpack_from("<I", d, i)[0]
        if idx == 0xFFFFFFFF or idx != len(voices):
            break
        voices.append(d[i + 4:i + 32].split(b"\0")[0].decode("ascii", "replace"))
    return voices


def _read_string(d, off):
    end = d.find(b"\0", off)
    if end < 0:
        return None
    try:
        return d[off:end].decode("cp932")
    except UnicodeDecodeError:
        return None


def _find_voice(d, pos, voices):
    """Look for the voice ID pushed right after the line (before the next line)."""
    limit = min(len(d), pos + 0x60)
    p = d.find(PUSH_PARAM_1, pos + 8, limit)
    nxt = d.find(DIALOGUE, pos + 8, limit)
    if p < 0 or 0 <= nxt < p:
        return ""
    val = struct.unpack_from("<f", d, p + 16)[0]
    if val < 0 or val != int(val):
        return ""
    i = int(val)
    return voices[i] if i < len(voices) else "id:%d" % i


def extract_lines(pac_path, voices):
    """Return [(offset, kind, speaker, voice, text)] in script order."""
    d = open(pac_path, "rb").read()
    lines = []
    for pos in range(0, len(d) - 8, 4):
        kind = OPCODES.get(d[pos:pos + 4])
        if not kind:
            continue
        off = struct.unpack_from("<I", d, pos + 4)[0]
        if not pos < off < len(d):
            continue
        text = _read_string(d, off)
        if not text:
            continue
        voice = _find_voice(d, pos, voices) if kind == "dialogue" else ""
        # The speaker is the 3-letter prefix of the voice file (sbw100040.at3 -> sbw).
        speaker = os.path.basename(voice)[:3] if voice and not voice.startswith("id:") else ""
        lines.append((pos, kind, speaker, voice, text))
    return lines


def write_lines(lines, base_path):
    """Write <base>.txt (readable) and <base>.csv (spreadsheet).

    The CSV is UTF-8 with a BOM so that Excel shows the Japanese text correctly.
    """
    with open(base_path + ".txt", "w", encoding="utf-8") as txt, \
         open(base_path + ".csv", "w", encoding="utf-8-sig", newline="") as f:
        out = csv.writer(f)
        out.writerow(["offset", "type", "speaker", "voice", "text"])
        for pos, kind, speaker, voice, text in lines:
            tag = "[%s]" % speaker if speaker else ("[mission]" if kind == "mission" else "[?]")
            txt.write("%s %s\n%s\n\n" % (tag, voice, text.rstrip("/").replace("/", "\n")))
            out.writerow(["0x%x" % pos, kind, speaker, voice, text])


def dump(src, out_dir):
    """src: a .pac file or the script/ folder. Returns {file name: line count}."""
    os.makedirs(out_dir, exist_ok=True)
    folder = src if os.path.isdir(src) else os.path.dirname(src)
    voices = load_voice_table(os.path.join(folder, "voiceidtable.pac"))
    if os.path.isdir(src):
        files = sorted(os.path.join(src, f) for f in os.listdir(src) if f.endswith(".pac"))
    else:
        files = [src]
    results = {}
    for pac in files:
        lines = extract_lines(pac, voices)
        if lines:
            name = os.path.splitext(os.path.basename(pac))[0]
            write_lines(lines, os.path.join(out_dir, name))
            results[os.path.basename(pac)] = len(lines)
    return results, len(voices)
