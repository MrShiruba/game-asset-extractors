"""Extraction of every PACKFILE entry, with audio sorted by category and character."""
import argparse
import collections
import os
import re
import zlib

from . import audio_map, pgd
from .atrac3 import make_at3
from .formats import AUDIO_TYPES, SCREEN, guess_ext, screens
from .packfile import PackFile
from .story import analyse as analyse_story
from .intro import INTRO_TABLE_ENTRIES, read_pairs
from .text import find_text_tables, format_text_table
from .movelist import read_move_list, format_move_list
from .params import STAT_FILES, character_stats, stats_csv
from . import bbq as bbq_script
from . import layout as layout_rules
from .sound_bank import find_banks, sound_bank_pair
from .archive import parts as archive_parts, unpack, write_leaf
from . import names, texture


# Last entry: 68 MiB of uniformly random bytes (no header, no repeated blocks, not zlib),
# referenced by no code: filler for the UMD.
PADDING_ENTRY = 14096


def entry_category(index, label, ext):
    """Top folder of a non-audio entry (see layout.py)."""
    return layout_rules.top_folder(index, label, ext)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="ttt_unpack.py",
        description="Extract PACKFILE.BIN of Dragon Ball Z Tenkaichi Tag Team (PSP: ULJS00311, ULUS10537, ULES01456).")
    p.add_argument("packfile", help="PSP_GAME/USRDIR/PACKFILE.BIN")
    p.add_argument("output", nargs="?", default="packfile_out", help="output folder (default: packfile_out)")
    p.add_argument("--png", action="store_true",
                   help="also write a PNG next to every image file (.tex, .rhg, .map textures, .fb)")
    p.add_argument("--txt", action="store_true",
                   help="also write what the tool decodes as text: text tables, move lists, "
                        "story scripts, camera moves and unlock lists as .txt, "
                        "character/character_stats.csv")
    p.add_argument("--no-unpack", action="store_true",
                   help="write nested archives as one NNNNN_<name>.pak file instead of a folder")
    return p.parse_args(argv)


def read_story(pack):
    """First pass: read the GSCF story scripts to know who says each story line."""
    scripts = []
    for index in audio_map.GSCF_SCRIPTS:
        if index < len(pack.entries) and pack.entries[index].size:
            try:
                data = pack.read(pack.entries[index])
            except (ValueError, zlib.error):
                continue
            if data[:4] == b"GSCF":
                scripts.append(data)
    return analyse_story(scripts) if scripts else None


def read_intro(pack):
    """First pass: read the pre-battle dialogue pair table (battle_ui archive)."""
    for index in INTRO_TABLE_ENTRIES:
        if index < len(pack.entries) and pack.entries[index].size:
            try:
                pairs = read_pairs(pack.read(pack.entries[index]))
            except (ValueError, zlib.error):
                continue
            if pairs:
                return pairs
    return {}


def output_path(index, ext, story, intro, label=None):
    """Path of an entry: audio/ or music/ for audio, else <category>/NNNNN_<name>.<ext>."""
    if ext == "at3":
        path = audio_map.audio_relpath(index, story=story, intro=intro)
        return path or "audio/%05d.at3" % index
    shown = names.shown(label)
    return "%s/%05d%s.%s" % (layout_rules.entry_folder(index, label, ext), index,
                             "_" + shown if shown else "", ext)


def layout_file(layout, path):
    """File written for the part at `path` (part numbers) of an unpacked archive, or None."""
    nodes = layout
    for depth, k in enumerate(path):
        if nodes is None or k >= len(nodes) or not nodes[k]:
            return None
        node = nodes[k]
        if depth == len(path) - 1:
            return node.get("file")
        nodes = node.get("arc")
    return None


def layout_files(layout):
    """Every file written for an unpacked archive."""
    for node in layout or ():
        if node:
            if "file" in node:
                yield node["file"]
            yield from layout_files(node.get("arc"))


def write_move_lists(layout, output, system_texts):
    """A .txt next to every move list of a character archive. Returns the count."""
    count = 0
    for rel in layout_files(layout):
        if not rel.endswith("_move_list_name.dat"):
            continue
        with open(os.path.join(output, rel), "rb") as f:
            moves = read_move_list(f.read())
        if not moves:
            continue
        for lang, texts in system_texts.items():
            suffix = ".txt" if len(system_texts) == 1 else "_%s.txt" % lang
            with open(os.path.join(output, rel[:-4] + suffix), "w", encoding="utf-8") as out:
                out.write(format_move_list(moves, texts))
        count += 1
    return count


def read_stats(layout, output, system_texts):
    """Stats row of a character archive (None if it has no parameter files)."""
    files = {}
    for rel in layout_files(layout):
        stem = os.path.splitext(os.path.basename(rel))[0]
        for kind in STAT_FILES:
            if stem.endswith("_" + kind) and stem.count("_") >= 2:
                with open(os.path.join(output, rel), "rb") as f:
                    files[kind] = f.read()
    if "blast_param" not in files:
        return None
    moves = read_move_list(files["move_list_name"]) if "move_list_name" in files else None
    texts = next(iter(system_texts.values()), None)
    return character_stats(files, moves, texts)


def write_story_scripts(stage_scripts, story_texts, system_texts, output):
    """A .txt (dialogue, messages, battles) next to every Dragon Walker stage script."""
    count = 0
    for chapter, rel, only in stage_scripts:
        langs = sorted(lang for ch, lang in story_texts if ch == chapter and only in (None, lang))
        if not langs:
            continue
        with open(os.path.join(output, rel), "rb") as f:
            data = f.read()
        for lang in langs:
            interface = system_texts.get(lang) or next(iter(system_texts.values()), None)
            listing = bbq_script.story_script(data, story_texts[(chapter, lang)], interface, names.entry)
            if not listing:
                continue
            suffix = ".txt" if len(langs) == 1 or only else "_%s.txt" % lang
            with open(os.path.join(output, os.path.splitext(rel)[0] + suffix), "w", encoding="utf-8") as out:
                out.write(listing)
            count += 1
    return count


VOICE_RATE, MUSIC_RATE = 22050, 44100     # music: stereo; voices / sounds: mono, some at
                                          # 44100 (audio_map.RATE_44100)


def wrap_audio(index, data):
    """Add a RIFF header to raw ATRAC3. Returns (data, is_music)."""
    if data[:4] == b"RIFF":
        return data, False
    if (audio_map.classify(index) or (None,))[0] == "bgm":
        return make_at3(data, channels=2, rate=MUSIC_RATE), True
    return make_at3(data, channels=1, rate=audio_map.sample_rate(index, VOICE_RATE)), False


def run(argv=None):
    args = parse_args(argv)
    pack = PackFile(args.packfile)
    print("%d entries, data from 0x%x" % (len(pack.entries), pack.data_start))

    story = read_story(pack)
    if story:
        print("Story scripts: %d shared line blocks, %d episode lines with a speaker"
              % (len(story.shared_blocks), len(story.episode_speakers)))
    intro = read_intro(pack)
    if intro:
        print("Pre-battle dialogue: %d lines" % len(intro))

    if os.path.isdir(args.output) and os.listdir(args.output):
        print("Warning: %s is not empty: files of an earlier extraction stay there "
              "(delete the folder first for a clean output)" % args.output)
    os.makedirs(args.output, exist_ok=True)
    index_csv = open(os.path.join(args.output, "index.csv"), "w", encoding="utf-8")
    index_csv.write("index;unknown;offset;size;packed_size;type;path;internal_name\n")

    types = collections.Counter()
    leaves = collections.Counter()
    top_textures = collections.Counter()
    categories = collections.Counter()
    errors = 0
    text_files = 0
    system_texts = {}   # language -> interface text table (entries 0..5, part 2)
    move_lists = 0
    stats = []          # (index, label, row) of every character archive
    story_texts = {}    # (chapter, language) -> story text table
    stage_scripts = []  # (chapter, rel) of the Dragon Walker stage scripts
    banks = 0
    music = []
    for entry in pack.entries:
        if entry.size == 0:          # nothing to write, but listed: type "empty", no path
            index_csv.write("%d;%#x;0x%x;0;0;empty;;%s\n" % (
                entry.index, entry.unknown, pack.offset(entry), audio_map.internal_name(entry.index) or ""))
            continue
        try:
            data = pack.read(entry)
        except (ValueError, zlib.error) as ex:
            errors += 1
            print("Entry %d: %s" % (entry.index, ex))
            continue

        ext = guess_ext(data)
        unpacked = ext == "bin" and not args.no_unpack and archive_parts(data) is not None
        is_texture = ext == "bin" and not unpacked and texture.decode(data) is not None
        n_screens = screens(data) if ext == "bin" and not unpacked and not is_texture else 0
        if ext == "bin" and entry.index == PADDING_ENTRY:
            ext = "padding"           # 68 MiB of random bytes: filler of the UMD
        if unpacked:
            ext = "arc"
        elif is_texture:
            ext = "tex"
        elif n_screens:
            ext = "fb"
        elif ext == "bin" and archive_parts(data) is not None:
            ext = "pak"               # --no-unpack: an archive kept whole (.pak, as in the
                                      # community's lists)
        types[ext] += 1
        label = names.entry(entry.index)
        if unpacked:
            shown = names.shown(label)
            rel = "%s/%05d%s" % (layout_rules.entry_folder(entry.index, label, ext), entry.index,
                                 "_" + shown if shown else "")
        else:
            rel = output_path(entry.index, ext, story, intro, label)
        if ext == "at3":
            categories[(audio_map.classify(entry.index, story, intro) or ("unmapped",))[0]] += 1

        layout = None
        pair = sound_bank_pair(data) if unpacked else None
        if pair:       # the entry is one sound bank
            for part_ext, part in zip(("pbd", "phd"), pair):
                dest = os.path.join(args.output, "%s.%s" % (rel, part_ext))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as out:
                    out.write(part)
                leaves[part_ext] += 1
        elif unpacked:
            layout = unpack(data, os.path.join(args.output, rel), "%05d" % entry.index, types=leaves,
                            png=args.png, index=entry.index, root=args.output)
        elif is_texture:
            folder, name = os.path.split(os.path.join(args.output, rel))
            os.makedirs(folder, exist_ok=True)
            write_leaf(data, folder, os.path.splitext(name)[0], top_textures, png=args.png)
        elif n_screens:
            dest = os.path.join(args.output, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(data)
            if args.png:
                images = []
                for k in range(n_screens):
                    raw = data[k * SCREEN:(k + 1) * SCREEN]
                    rows = [raw[y * 480 * 4:(y + 1) * 480 * 4] for y in range(272)][::-1]
                    rgba = bytearray(b"".join(rows))
                    rgba[3::4] = b"\xff" * (480 * 272)
                    images.append((480, 272, bytes(rgba)))
                with open("%s.png" % os.path.splitext(dest)[0], "wb") as out:
                    out.write(texture.to_png(*texture.sheet(images)))
                top_textures["png images"] += 1
        else:
            if ext == "at3":
                data, is_music = wrap_audio(entry.index, data)
                if is_music:
                    music.append(entry.index)
            dest = os.path.join(args.output, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(data)
            if ext == "pgd":          # encrypted: also written decrypted (pgd.py)
                plain = pgd.decrypt(data)
                if plain is None:
                    print("Entry %d: PGD not decrypted (%s)" % (entry.index, pgd.why(data)))
                else:
                    with open(re.sub(r"_encrypted$", "", os.path.splitext(dest)[0])
                              + "_decrypted.dat", "wb") as out:
                        out.write(plain)

        # Sound banks (written as .pbd + .phd by the archive code, or just above)
        if ext not in AUDIO_TYPES:
            banks += sum(1 for _ in find_banks(data))

        # Text tables: decoded to a .txt next to the table.
        if ext not in AUDIO_TYPES:
            for sub, texts in find_text_tables(data):
                part = layout_file(layout, sub) if layout and sub else None
                if not sub and not unpacked:
                    txt = os.path.splitext(rel)[0] + ".txt"
                elif part:
                    txt = os.path.splitext(part)[0] + ".txt"
                else:
                    txt = rel + "".join("_%d" % k for k in sub) + ".txt"
                if args.txt:
                    dest = os.path.join(args.output, txt)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "w", encoding="utf-8") as out:
                        out.write(format_text_table(texts))
                text_files += 1
                chapter = re.search(r"sm_txt_ch(\d+)_([a-z]+)", label or "")
                if chapter and getattr(texts, "base", 0) == 10000:
                    story_texts[(int(chapter.group(1)), chapter.group(2))] = texts
                if entry.index <= 5 and sub == (2,):
                    system_texts[label.rsplit("_", 1)[-1] if label else str(entry.index)] = texts

        # Move lists: names and inputs from the interface text tables.
        if layout and system_texts and args.txt:
            move_lists += write_move_lists(layout, args.output, system_texts)
        if layout and entry_category(entry.index, label, ext) == "character":
            row = read_stats(layout, args.output, system_texts)
            if row:
                stats.append((entry.index, names.shown(label), row))

        stage = re.match(r"sm_ch(\d+)_\d+$", label or "")
        if ext == "bbq" and stage:
            stage_scripts.append((int(stage.group(1)), rel, None))
        localized = re.search(r"sm_txt_ch(\d+)_([a-z]+)$", label or "")
        if localized and layout:      # EU / US: the chapter script of each language
            for part in layout_files(layout):
                if part.endswith(".bbq"):
                    stage_scripts.append((int(localized.group(1)), part, localized.group(2)))

        index_csv.write("%d;%#x;0x%x;%d;%d;%s;%s;%s\n" % (
            entry.index, entry.unknown, pack.offset(entry), entry.size, entry.packed_size, ext, rel,
            audio_map.internal_name(entry.index) or ""))

    index_csv.close()
    story_files = (write_story_scripts(stage_scripts, story_texts, system_texts, args.output)
                   if args.txt else 0)
    derived = write_derived_texts(args.output) if args.txt else 0
    vags = write_vags(args.output)
    if stats and args.txt:
        os.makedirs(os.path.join(args.output, "character"), exist_ok=True)
        with open(os.path.join(args.output, "character", "character_stats.csv"), "w",
                  encoding="utf-8-sig") as out:
            out.write(stats_csv(stats))
    pack.close()
    print("Errors: %d | text tables: %d | sound banks: %d" % (errors, text_files, banks))
    if move_lists:
        print("Character move lists: %d (%s)" % (move_lists, ", ".join(system_texts)))
    if story_files:
        print("Story scripts as text: %d" % story_files)
    if derived:
        print("Camera moves and unlock lists as text: %d" % derived)
    if vags:
        print("Sound bank samples (.vag): %d" % vags)
    if stats and args.txt:
        print("Character stats: %d rows in character/character_stats.csv" % len(stats))
    if music:
        print("Music (%d): %s" % (len(music), ", ".join("%05d" % m for m in music)))
    print("Types:", ", ".join("%s=%d" % kv for kv in types.most_common()))
    images = leaves.pop("png images", 0) + top_textures["png images"]
    inflated = leaves.pop("zlib", 0)
    if leaves:
        print("Inside archives (%d files): %s" % (sum(leaves.values()),
              ", ".join("%s=%d" % kv for kv in leaves.most_common())))
    if inflated:
        print("Compressed parts written decompressed: %d" % inflated)
    if images:
        print("PNG sheets (one per image file): %d" % images)
    if categories:
        print("Audio:", ", ".join("%s=%d" % kv for kv in categories.most_common()))
    unnamed = write_unnamed_list(args.output)
    if unnamed:
        print("Files with no descriptive name yet: %d (listed in unnamed.txt)" % unnamed)
    print("Done:", args.output)


def write_vags(root):
    """Every sound bank NAME.phd + NAME.pbd becomes NAME/PREFIX_SSS_<name>.vag (PREFIX = the
    entry and part numbers of the bank, SSS = slot); the .phd / .pbd are removed.
    Returns the number of .vag written."""
    from .sound_bank import split_vags
    written = 0
    for folder, _, files in os.walk(root):
        for name in files:
            stem, ext = os.path.splitext(name)
            if ext != ".phd" or stem + ".pbd" not in files:
                continue
            phd, pbd = os.path.join(folder, stem + ".phd"), os.path.join(folder, stem + ".pbd")
            with open(phd, "rb") as f:
                header = f.read()
            with open(pbd, "rb") as f:
                body = f.read()
            samples = split_vags(body, header)
            if not samples:
                print("Sound bank kept as .phd + .pbd (its samples could not be split): %s"
                      % os.path.relpath(phd, root))
                continue
            prefix = re.match(r"\d+(?:_\d{3})*", stem).group(0)
            out = os.path.join(folder, stem)
            os.makedirs(out, exist_ok=True)
            for slot, label, data in samples:
                vag_name = "%s_%03d%s.vag" % (prefix, slot, "_" + label if label else "")
                with open(os.path.join(out, vag_name), "wb") as f:
                    f.write(data)
                written += 1
            os.remove(phd)
            os.remove(pbd)
    return written


def write_derived_texts(root):
    """--txt: a .txt next to every camera move (.cman) and unlock list. Returns the count."""
    from . import cman, unlocks
    written = 0
    for folder, _, files in os.walk(root):
        for name in files:
            stem, ext = os.path.splitext(name)
            if ext == ".cman":
                convert = cman.to_text
            elif ext == ".unl" and re.match(r"\d+_\d+_", stem):
                label = re.sub(r"^\d+_\d+_", "", stem)
                if label not in unlocks.REQUIREMENT:
                    continue
                convert = lambda data, label=label: unlocks.to_text(data, label)
            else:
                continue
            with open(os.path.join(folder, name), "rb") as f:
                text = convert(f.read())
            if text:
                with open(os.path.join(folder, stem + ".txt"), "w", encoding="utf-8") as out:
                    out.write(text)
                written += 1
    return written


def write_unnamed_list(root):
    """unnamed.txt: every file whose name is only numbers (NNNNN_KKK.ext), counted by
    folder and type, to see what is left to identify. Returns the number of files."""
    found = collections.Counter()
    for folder, _, files in os.walk(root):
        for name in files:
            m = re.fullmatch(r"[0-9_]+\.([a-z0-9]+)", name)
            if m and m.group(1) not in ("png", "txt", "padding"):
                rel = os.path.relpath(folder, root).replace(os.sep, "/")
                found[(re.sub(r"\d{5}", "NNNNN", rel), m.group(1))] += 1
    path = os.path.join(root, "unnamed.txt")
    if not found:
        if os.path.exists(path):
            os.remove(path)
        return 0
    with open(path, "w", encoding="utf-8") as out:
        out.write("count\ttype\tfolder (NNNNN = any entry number)\n")
        for (folder, ext), count in sorted(found.items(), key=lambda kv: (-kv[1], kv[0])):
            out.write("%d\t%s\t%s\n" % (count, ext, folder))
    return sum(found.values())
