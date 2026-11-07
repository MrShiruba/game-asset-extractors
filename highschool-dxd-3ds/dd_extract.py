"""dd_extract.py - asset extractor for High School DxD (3DS, Kadokawa Games, 2013)

Usage: python dd_extract.py ExtractedRomFS [output]

Writes everything to "output" (default: an "out" folder next to ExtractedRomFS),
mirroring the RomFS folder layout:
  out/data/event/...                the 795 .evt scripts of data/event.enc (original paths),
                                    + a .txt with the dialogue of each script that has text
  out/<dir>/<archive>/...           contents of every other .enc archive (LZO1X):
                                    .ctx textures (+ .png), .bin tables
  out/<dir>/<texture>.png           every .ctx texture of the RomFS
  out/se/                           the sounds of se/se.acb as .bcwav, named after their cues (+ list.txt)
  out/text/                         text/*.bin as .txt (UTF-8)
  out/data/event/flag.txt, tutorial.txt   data/event/flag.dat and tutorial.dat as text
The RomFS is never modified; running it again simply overwrites the output folder.

Requires Python 3; numpy + Pillow for PNG output (pip install numpy pillow).
"""
import os
import argparse

from dd_formats.enc import read_enc, guess_ext
from dd_formats.acb import acb_cwav
from dd_formats.text import strings_bin_to_txt
from dd_formats.event_data import flag_dat_to_txt, tutorial_dat_to_txt
from dd_formats.evt import evt_to_txt

try:
    from PIL import Image
    from dd_formats.ctx import decode
except ImportError:   # numpy or Pillow missing: no PNG output
    Image = None
    decode = None


# plain data files converted to text (path in the RomFS -> converter)
TEXT_FILES = {
    'data/event/flag.dat': flag_dat_to_txt,
    'data/event/tutorial.dat': tutorial_dat_to_txt,
}


def main():
    ap = argparse.ArgumentParser(
        description="Asset extractor for High School DxD (3DS). Writes the extracted files to an "
                    "output folder that mirrors the RomFS layout.")
    ap.add_argument('romfs', help='already extracted RomFS folder (ExtractedRomFS)')
    ap.add_argument('output', nargs='?', help="output folder (default: 'out' next to the RomFS folder)")
    a = ap.parse_args()

    root = os.path.abspath(a.romfs)
    out_root = os.path.abspath(a.output) if a.output else os.path.join(os.path.dirname(root), 'out')
    if out_root == root or out_root.startswith(root + os.sep):
        ap.error('the output folder must be outside the RomFS folder')
    print('Output: %s' % out_root)
    if Image is None:
        print('WARNING: numpy/Pillow not found (pip install numpy pillow), skipping PNG conversion.')

    names_evt = None
    p = os.path.join(root, 'data', 'event', 'eventFileListTbl.dat')
    if os.path.exists(p):
        t = open(p, 'rb').read()
        names_evt = [t[i:i + 64].rstrip(b' \0').decode('ascii', 'replace') for i in range(0, len(t), 64)]

    st = {'enc': 0, 'files': 0, 'png': 0, 'snd': 0, 'txt': 0, 'err': []}

    def write(path, data, key='files'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'wb').write(data)
        st[key] += 1

    def png(ctx_bytes, path_noext):
        if Image is None:
            return
        try:
            img, _ = decode(ctx_bytes)
            os.makedirs(os.path.dirname(path_noext), exist_ok=True)
            Image.fromarray(img).save(path_noext + '.png')
            st['png'] += 1
        except Exception as e:
            st['err'].append('%s.ctx : %s' % (path_noext, e))

    # list the sources first
    sources = []
    for dp, dn, fn in os.walk(root):
        dn.sort()
        sources += [os.path.join(dp, f) for f in sorted(fn)]

    for src in sources:
        rel = os.path.relpath(src, root)
        d_src, f = os.path.split(src)
        stem, ext_src = os.path.splitext(f)
        low = ext_src.lower()
        out_dir = os.path.normpath(os.path.join(out_root, os.path.relpath(d_src, root)))
        try:
            if low == '.enc':
                ents = read_enc(open(src, 'rb').read())
                st['enc'] += 1
                for i, b in enumerate(ents):
                    if not b:
                        continue
                    if stem == 'event' and names_evt and i < len(names_evt) and names_evt[i]:
                        # data/event.enc -> out/data/event/main/M0000.evt (+ M0000.txt: dialogue)
                        evt_path = os.path.join(out_dir, names_evt[i])
                        write(evt_path, b)
                        try:
                            txt = evt_to_txt(b)
                        except ValueError as e:
                            st['err'].append('%s : %s' % (names_evt[i], e)); txt = ''
                        if txt:
                            open(os.path.splitext(evt_path)[0] + '.txt', 'w', encoding='utf-8').write(txt)
                            st['txt'] += 1
                        continue
                    # data/npc/CTR/bustup/BU_AKN_000.enc -> out/data/npc/CTR/bustup/BU_AKN_000/BU_AKN_000_01.ctx/.png
                    sub = os.path.join(out_dir, stem, '%s_%02d' % (stem, i))
                    ext = guess_ext(b)
                    write(sub + ext, b, 'snd' if ext == '.bcwav' else 'files')
                    if ext == '.ctx':
                        png(b, sub)
            elif low == '.ctx':
                png(open(src, 'rb').read(), os.path.join(out_dir, stem))
            elif low == '.acb':
                r = acb_cwav(open(src, 'rb').read())
                if r is None:
                    continue  # no embedded CWAV: vgmstream reads it as is
                files, log = r
                # se/se.acb -> out/se/ (other ACBs -> out/<dir>/<name>/)
                od = out_dir if os.path.basename(d_src) == stem else os.path.join(out_dir, stem)
                for nm, c in files:
                    write(os.path.join(od, nm + guess_ext(c)), c, 'snd')
                open(os.path.join(od, 'list.txt'), 'w', encoding='utf-8').write('\n'.join(log) + '\n')
            elif rel.replace('\\', '/') in TEXT_FILES or (
                    rel.replace('\\', '/').startswith('text/') and low == '.bin'):
                conv = TEXT_FILES.get(rel.replace('\\', '/'), strings_bin_to_txt)
                txt = conv(open(src, 'rb').read())
                os.makedirs(out_dir, exist_ok=True)
                open(os.path.join(out_dir, stem + '.txt'), 'w', encoding='utf-8').write(txt)
                st['txt'] += 1
        except Exception as e:
            st['err'].append('%s : %s' % (rel, e))
        print('\r%d archives | %d files | %d PNG | %d sounds | %d texts'
              % (st['enc'], st['files'], st['png'], st['snd'], st['txt']), end='', flush=True)
    print()
    for e in st['err']:
        print('ERROR', e)
    print('Done.')


if __name__ == '__main__':
    main()
