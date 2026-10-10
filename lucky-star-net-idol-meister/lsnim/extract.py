"""Extraction of the archives and command line."""
import argparse
import csv
import os
import sys

from .tables import (
    ALBUM_RANK, CELL_LAYOUTS, FONT_IDS, MINIGAME_SFX, OTHER_VOICES, PALETTE_COUNTS,
    PIECE_LAYOUTS, SOUND_FILES, menu_voice_path, minigame_voice_folder, png_folder, quiz_voice_path,
    script_folder,
)
from .cpk import decompress_crilayla, list_entries
from .audio import detect_type, split_acx
from .images import (
    Image, decode_font, decode_gim, decode_images, decode_with_palettes, lay_out_pieces,
    np, place_cells, rebuild_sprite,
)
from .scripts import build_voice_names, convert
from .loose import LOOSE_FILES


def extract(path, output_dir, verbose=False, archive_label='', voice_names=None, raw_type=('bin', '.bin')):
    counts = {}
    index_rows = []
    file_rows = []
    with open(path, 'rb') as f:
        entries = list_entries(f)
        if voice_names is not None and len(voice_names) != len(entries):
            print('warning: %d voice names for %d files, keeping numeric IDs'
                  % (len(voice_names), len(entries)))
            voice_names = None
        for index, (name, offset, size) in enumerate(entries, 1):
            f.seek(offset)
            data = f.read(size)
            if data[:8] == b'CRILAYLA':
                data = decompress_crilayla(data)

            type_name, extension = detect_type(data[:0x2000])
            if type_name == 'bin':
                type_name, extension = raw_type
                if not data.strip(b'\x00').strip(b'\x11'):
                    # empty placeholder (zeros + 16 bytes of 0x11 padding), e.g. union 02927, 02935
                    type_name, extension = 'bin-dummy', '.bin'
            stem, current_ext = os.path.splitext(name)
            original_id, detected, written = stem, type_name, []
            if current_ext.lower() in ('', '.bin'):
                current_ext = extension
            if voice_names is not None:
                file_id = int(stem)
                new_stem, row = voice_names[file_id]
                index_rows.append(['%05d' % file_id, new_stem + current_ext] + row)
                stem = new_stem
                # sorted like the scripts, then one folder per script
                type_name = os.path.join(type_name, script_folder(int(row[0])), 'sc' + row[0])
            elif archive_label == 'union' and stem.isdigit() and type_name.startswith('adx'):
                if int(stem) in SOUND_FILES:
                    group, number = SOUND_FILES[int(stem)]
                    type_name = 'adx/' + group                       # e.g. adx/bgm/000.adx
                    stem = '%03d' % int(stem) + ('-' + number if number else '')
            elif archive_label == 'union' and stem.isdigit() and type_name.startswith('ahx'):
                voice = menu_voice_path(int(stem)) or quiz_voice_path(int(stem))
                voice = OTHER_VOICES.get(int(stem), voice)
                if voice:
                    type_name, stem = voice
            font = FONT_IDS.get(archive_label, {}).get(int(stem)) if stem.isdigit() else None
            if type_name == 'bin' and np is not None and font:
                images = [decode_font(data, *font)]
            else:
                images = []
                suffixes = []
                if type_name == 'bin' and np is not None:
                    if b'MAP\x00' in data[:0x2000]:                      # character sprite
                        sprite = rebuild_sprite(data)
                        images = [sprite] if sprite is not None else []
                    override = PALETTE_COUNTS.get(archive_label, {}).get(int(stem)) if stem.isdigit() else None
                    if override:
                        named = decode_with_palettes(data, override)
                        images = [rgba for _, rgba in named]
                        suffixes = [suffix for suffix, _ in named]
                    images = images or decode_images(data)
                    layouts = CELL_LAYOUTS.get(archive_label, {}).get(int(stem)) if stem.isdigit() else None
                    if layouts and suffixes:
                        images = [place_cells(rgba, layouts[int(suffix[1:3])])
                                  if int(suffix[1:3]) in layouts else rgba
                                  for rgba, suffix in zip(images, suffixes)]
                    pieces = PIECE_LAYOUTS.get(archive_label, {}).get(int(stem)) if stem.isdigit() else None
                    if pieces and suffixes:
                        images = [lay_out_pieces(rgba, pieces[int(suffix[1:3])])
                                  if int(suffix[1:3]) in pieces and suffix[3:] == '' else rgba
                                  for rgba, suffix in zip(images, suffixes)]
            if type_name == 'gim' and np is not None:     # keep the GIM, add PNG frames
                type_name = 'gim-converted-to-png'       # the PNG in png/ are what to use
                frames = decode_gim(data)
                for k, rgba in enumerate(frames):
                    name = stem + ('_%02d' % k if len(frames) > 1 else '') + '.png'
                    written.append(os.path.join(png_folder(archive_label, stem), name))
                    target = os.path.join(output_dir, written[-1])
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    Image.fromarray(np.ascontiguousarray(rgba), 'RGBA').save(target)
            if type_name == 'acx':
                # vgmstream plays ACX of ADX but not ACX of AHX: those (union: per-character
                # mini-game voices) are split into <id>_00.ahx, <id>_01.ahx...
                streams = split_acx(data)
                kinds = {detect_type(stream[:0x20]) for stream in streams}
                if len(kinds) == 1 and next(iter(kinds))[1] == '.ahx':
                    type_name, extension = kinds.pop()
                    if archive_label == 'union' and stem.isdigit():
                        type_name = minigame_voice_folder(int(stem)) or type_name
                    for k, stream in enumerate(streams):
                        relative = os.path.join(type_name, '%s_%02d%s' % (stem, k, extension))
                        written.append(relative)
                        target = os.path.join(output_dir, relative)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with open(target, 'wb') as out:
                            out.write(stream)
                    relative = os.path.join(type_name, '%s_00-%02d%s' % (stem, len(streams) - 1, extension))
                    data = b''                               # nothing else to write
                elif archive_label == 'union' and stem.isdigit() and int(stem) in MINIGAME_SFX:
                    type_name = os.path.join('acx', 'ミニゲーム-sfx', MINIGAME_SFX[int(stem)])
            if images:
                type_name = png_folder(archive_label, stem)
                for k, rgba in enumerate(images):
                    if suffixes:
                        name = stem + suffixes[k] + '.png'
                    else:
                        name = stem + ('_%02d' % k if len(images) > 1 else '') + '.png'
                    if archive_label == 'union' and stem.isdigit() and int(stem) in ALBUM_RANK:
                        name = '%03d-%s' % (ALBUM_RANK[int(stem)], name)
                    relative = os.path.join(type_name, name)
                    written.append(relative)
                    target = os.path.join(output_dir, relative)
                    os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
                    Image.fromarray(rgba, 'RGBA').save(target)
            elif data:
                if type_name == 'png':                   # real PNG file (union 02933, save icon)
                    type_name = png_folder(archive_label, stem)
                name = stem + current_ext
                sorted_in = script_folder(int(stem)) if type_name == 'sc' and stem.isdigit() else ''
                relative = os.path.join(type_name, sorted_in, name)
                written.append(relative)
                target = os.path.join(output_dir, relative)
                os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
                with open(target, 'wb') as out:
                    out.write(data)
                if type_name == 'sc':                    # scripts: also write the decoded text
                    text = convert(data)[0]
                    if text:
                        name = stem + '.txt'
                        relative = os.path.join('txt', sorted_in, name)
                        written.append(relative)
                        target = os.path.join(output_dir, relative)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with open(target, 'w', encoding='utf-8') as out:
                            out.write(text + '\n')

            if detected == 'bin' and written and written[0].endswith('.png'):
                detected = 'font' if font else 'image'      # the game's own image / font formats
            file_rows.append([original_id, size, len(data) or size, detected,
                              ' ; '.join(w.replace(os.sep, '/') for w in written)])
            grouped = 'ミニゲーム' in type_name or 'system-voices' in type_name
            group = os.path.join(*type_name.split(os.sep)[:2]) if grouped else type_name
            if voice_names is not None:
                group = type_name.split(os.sep)[0]
            counts[group] = counts.get(group, 0) + 1
            if verbose:
                print('%-50s %9d -> %9d  %s' % (relative, size, len(data) or size, type_name))
            elif index % 200 == 0 or index == len(entries):
                print('\r  %d/%d' % (index, len(entries)), end='', flush=True)

    # list of every file of the archive and what it was written as (no game text in it)
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, 'files.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'stored_size', 'size', 'format', 'written_as'])
        writer.writerows(file_rows)
    if index_rows:
        with open(os.path.join(output_dir, 'voices.csv'), 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['vo_id', 'file', 'sc_id', 'msg_id', 'character_id', 'speaker', 'text'])
            writer.writerows(index_rows)
    print('\n  %d files:' % len(entries))
    for type_name, count in sorted(counts.items(), key=lambda item: -item[1]):
        print('    %-16s %6d' % (type_name, count))


def main():
    parser = argparse.ArgumentParser(description='Extract the CPK archives of Lucky Star: Net Idol Meister.')
    parser.add_argument('input', nargs='?', default='.',
                        help='DATA folder (with sc.cpk, union.cpk, vo.cpk, lt.bin, pr.bin) or a single '
                             'file (default: current folder)')
    parser.add_argument('output_dir', nargs='?', default='out',
                        help='output folder, one subfolder per archive (default: out)')
    parser.add_argument('--sc', help='path to sc.cpk, to name the voices when extracting vo.cpk alone')
    parser.add_argument('-v', '--verbose', action='store_true', help='print every file')
    args = parser.parse_args()

    if os.path.isdir(args.input):
        names = sorted(os.listdir(args.input))
        archives = [os.path.join(args.input, n) for n in names if n.lower().endswith('.cpk')]
        loose = [os.path.join(args.input, n) for n in names if n.lower() in LOOSE_FILES]
    elif os.path.basename(args.input).lower() in LOOSE_FILES:
        archives, loose = [], [args.input]
    else:
        archives, loose = [args.input], []
    if not archives and not loose:
        sys.exit('no .cpk, lt.bin or pr.bin found in %s' % os.path.abspath(args.input))
    sc_path = args.sc or next((a for a in archives if os.path.basename(a).lower() == 'sc.cpk'), None)

    for archive in archives:
        label = os.path.splitext(os.path.basename(archive))[0]
        print('%s:' % os.path.basename(archive))
        voice_names = None
        if label.lower() == 'vo':
            if sc_path and os.path.exists(sc_path):
                voice_names = build_voice_names(sc_path)
            else:
                print('  sc.cpk not found (use --sc): voices keep their numeric IDs')
        raw_type = ('sc', '.sc') if label.lower() == 'sc' else ('bin', '.bin')
        extract(archive, os.path.join(args.output_dir, label), archive_label=label.lower(),
                verbose=args.verbose, voice_names=voice_names, raw_type=raw_type)

    for path in loose:
        name = os.path.basename(path).lower()
        print('%s:' % os.path.basename(path))
        if np is None:
            print('  numpy + Pillow needed to convert it, skipped')
            continue
        LOOSE_FILES[name](path, os.path.join(args.output_dir, os.path.splitext(name)[0]))
