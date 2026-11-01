"""Sorted mode: moves the extracted files into categories with readable names.

Every extracted file ends up somewhere (nothing is dropped); index.csv maps each
sorted path back to its path in raw mode (files/...).
"""
import os
import re
import shutil
import struct

from .cgfx import cgfx_category, cgfx_contents, cgfx_label
from .filetypes import safe
from .swif import layout_texture_names, swif_kind
from .text import is_message_table

SOUND_EXT = (".adx", ".bcwav", ".hca")
# language prefixes used in texture names (ge = German, sp = Spanish, du = Dutch)
LANGUAGES = ("en", "fr", "ge", "it", "sp", "du", "jp")
LANG_RE = re.compile(r"^(%s)_" % "|".join(LANGUAGES))


def _id_path(rel):
    """'0111/0001.swif' -> '0111-0001'"""
    return os.path.splitext(rel)[0].replace(os.sep, "-").replace("/", "-")


def _top_number(rel):
    m = re.match(r"^(\d+)", rel.replace(os.sep, "/").split("/")[0])
    return int(m.group(1)) if m else None


def _join(*parts):
    return "_".join(p for p in parts if p)


class Sorter:
    def __init__(self, out_root, raw_root, names):
        self.out = out_root
        self.raw = raw_root
        self.names = names
        self.index = []
        self.problems = []
        self._taken = set()
        self._cgfx = {}
        self._rejected = set()
        self._folder_labels = {}
        self._folder_langs = {}
        self._prev_lang = {}

    # ---------------------------------------------------------------- helpers
    def name_of(self, number):
        if number in self._rejected:
            return ""
        entry = self.names.get(number)
        return safe(entry[0]) if entry and entry[0] else ""

    def check_names(self, acb_names):
        """Drops the names whose check value does not match the ACB content.

        acb_names: {acb_number: [names of its waveforms, from the cue names]}.
        """
        for number, entry in self.names.items():
            check = entry[3] if len(entry) > 3 else ""
            got = sorted(acb_names.get(number) or [])
            if check and got and got[0] != check:
                self._rejected.add(number)
                self.problems.append("names.csv: %04d does not look like '%s' (expected %s, found %s),"
                                     " left unnamed" % (number, entry[0], check, got[0]))

    def cgfx(self, path):
        """(category, label) of a CGFX file, from its table of contents."""
        if path not in self._cgfx:
            try:
                with open(path, "rb") as f:
                    c = cgfx_contents(f.read())
                label = cgfx_label(c)
                if not c:
                    self._cgfx[path] = ("other", "empty")
                else:
                    self._cgfx[path] = (cgfx_category(c), safe(label) if label.strip() else "")
            except (OSError, ValueError, struct.error) as e:
                self.problems.append("%s: unreadable CGFX table (%s)"
                                     % (os.path.relpath(path, self.raw), e))
                self._cgfx[path] = ("other", "")
        return self._cgfx[path]

    def move(self, src, dest_rel, record=True):
        dest = os.path.join(self.out, dest_rel)
        base, ext = os.path.splitext(dest)
        k = 2
        while dest.lower() in self._taken or os.path.exists(dest):
            dest = "%s_%d%s" % (base, k, ext)
            k += 1
        self._taken.add(dest.lower())
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(src, dest)
        if record:
            self.index.append((os.path.relpath(dest, self.out),
                               "files/" + os.path.relpath(src, self.raw).replace(os.sep, "/")))

    # ------------------------------------------------------------ main logic
    def destination(self, path, stream_owner):
        """Sorted relative path for one raw file."""
        rel = os.path.relpath(path, self.raw)
        parts = rel.replace(os.sep, "/").split("/")
        ext = os.path.splitext(path)[1].lower()
        idp = _id_path(rel)
        top = _top_number(rel)

        stem = os.path.splitext(parts[0])[0]
        if stem in stream_owner and (ext == ".cpk" and len(parts) == 1 or parts[0] == stem):
            # streamed AWB of an ACB: the raw CPK becomes <acb>.awb next to the
            # .acb (vgmstream opens the .awb and reads the cue names from the
            # .acb). The waveforms extracted from it are then redundant.
            acb_num = stream_owner[stem]
            bank = _join("%04d" % acb_num, self.name_of(acb_num))
            awb_raw = os.path.join(self.raw, stem + ".cpk")
            if ext == ".cpk" and len(parts) == 1:
                return os.path.join("sound", bank + ".awb")
            if os.path.isfile(awb_raw):
                return None, os.path.join("sound", bank + ".awb")
            return os.path.join("sound", bank + "_stream", "/".join(parts[1:]))
        if ext in (".acb", ".acf", ".awb"):
            return os.path.join("sound", _join(idp, self.name_of(top) if len(parts) == 1 else "") + ext)
        if ext in SOUND_EXT:
            return os.path.join("sound", "_loose", idp + ext)

        label = self.name_of(top) if len(parts) == 1 else ""
        cat, lab = self.classify(path)
        if not lab and not label and cat in ("text", "fonts"):
            lab = self.context_label(path, "font" if ext == ".bcfnt" else "text")
        if cat in ("textures", "layouts", "text", "fonts"):
            # one sub-folder per language. The language comes from the folder
            # (one game screen) or the language block the file belongs to,
            # not from the file name alone: localised blocks keep a few
            # textures with their original jp_* names.
            lang = self.language_of(path, lab, cat)
            if lang:
                return os.path.join(cat, lang, _join(idp, label or lab) + ext)
        return os.path.join(cat, _join(idp, label or lab) + ext)

    def context_label(self, path, kind):
        """Label for a text or font from the files around it (they hold no name).

        In a folder (one screen of the game), texts and fonts take the name of
        the main texture/layout/model of the folder, e.g. 1667/0001.bin ->
        'en_aquba0'. Otherwise (top-level files, folders holding only texts
        and fonts) they take the language of the closest previous entry with
        a language prefix (en_logo, en_word01... -> 'en_text', 'en_font').
        """
        folder = os.path.dirname(path)
        if os.path.normpath(folder) != os.path.normpath(self.raw):
            lab = self._folder_label(folder)
            if lab:
                return lab
            number_of = os.path.basename(folder)
        else:
            number_of = os.path.basename(path)
        m = re.match(r"^(\d+)", number_of)
        if not m:
            return ""
        num, width = int(m.group(1)), len(m.group(1))
        lang = self._previous_language(num, width)
        return lang + "_" + kind if lang else ""

    def _folder_label(self, folder):
        if folder not in self._folder_labels:
            found = []
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith((".bcres", ".swif")):
                    cat, lab = self.classify(os.path.join(folder, f), False)
                    if lab and lab != "empty":
                        found.append((cat not in ("textures", "layouts", "models"), lab))
            lang = self._folder_language(folder)
            # prefer a name in the folder's language (localised blocks keep a
            # few jp_* names), then textures/layouts/models, then the rest
            found = [(not (lang and lab.startswith(lang + "_")), other, lab) for other, lab in found]
            self._folder_labels[folder] = min(found)[2] if found else ""
        return self._folder_labels[folder]

    def language_of(self, path, label="", cat=""):
        """Language sub-folder for a file ('' = shared / not localised)."""
        guess = cat in ("text", "fonts")      # nameless: deduce from the block
        mm = LANG_RE.match(label or "")
        folder = os.path.dirname(path)
        if os.path.normpath(folder) != os.path.normpath(self.raw):
            lang = self._folder_language(folder)
            if lang:
                return lang
            if not guess:
                return mm.group(1) if mm else ""
            m = re.match(r"^(\d+)", os.path.basename(folder))
        else:
            if mm and mm.group(1) != "jp":
                return mm.group(1)
            if not (guess or mm):
                return ""
            m = re.match(r"^(\d+)", os.path.basename(path))
        lang = self._previous_language(int(m.group(1)), len(m.group(1))) if m else ""
        return lang or (mm.group(1) if mm else "")

    def _folder_language(self, folder):
        """Main language of a folder: the most common language prefix of its
        graphics, jp only if no other language is present ('' if none)."""
        if folder not in self._folder_langs:
            counts = {}
            for f in os.listdir(folder):
                if f.lower().endswith((".bcres", ".swif")):
                    mm = LANG_RE.match(self.classify(os.path.join(folder, f), False)[1])
                    if mm:
                        counts[mm.group(1)] = counts.get(mm.group(1), 0) + 1
            other = {k: v for k, v in counts.items() if k != "jp"}
            pick = other or counts
            self._folder_langs[folder] = max(pick, key=pick.get) if pick else ""
        return self._folder_langs[folder]

    def _previous_language(self, num, width, limit=400):
        """Language of the closest previous top-level entries (language blocks:
        en_logo, en_word01... come first in each block). jp only if nothing
        else is found."""
        key = (num, width)
        if key in self._prev_lang:
            return self._prev_lang[key]
        found_jp = False
        result = ""
        for k in range(1, min(limit, num) + 1):
            name = "%0*d" % (width, num - k)
            cand = os.path.join(self.raw, name)
            lang = ""
            if os.path.isdir(cand):
                lang = self._folder_language(cand)
            else:
                for e in (".bcres", ".swif"):
                    if os.path.isfile(cand + e):
                        mm = LANG_RE.match(self.classify(cand + e, False)[1])
                        lang = mm.group(1) if mm else ""
                        break
            if lang == "jp":
                found_jp = True
            elif lang:
                result = lang
                break
        if not result and found_jp:
            result = "jp"
        self._prev_lang[key] = result
        return result

    def classify(self, path, follow_siblings=True):
        """(category, label) for a non-sound file."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".bcres":
            return self.cgfx(path)
        if ext == ".swif":
            inner = os.path.splitext(path)[0] + ".bcres"
            if os.path.isfile(inner):
                return "textures", self.cgfx(inner)[1]
            try:
                with open(path, "rb") as f:
                    blob = f.read()
                kind = swif_kind(blob)
            except (OSError, ValueError, struct.error):
                return "other", ""
            if kind == "layout":
                names = [n for n in layout_texture_names(blob) if n not in ("xx", "jp")]
                return "layouts", safe(names[0]) if names else ""
            return ("textures" if kind == "texture" else "other"), ""
        if ext == ".stat" and follow_siblings:
            # a .stat goes with the other files of its folder
            folder = os.path.dirname(path)
            if os.path.normpath(folder) != os.path.normpath(self.raw):
                sib = sorted(f for f in os.listdir(folder)
                             if not f.lower().endswith(".stat")
                             and os.path.isfile(os.path.join(folder, f)))
                if sib:
                    return self.classify(os.path.join(folder, sib[0]), False)
            return "other", ""
        if ext == ".bcfnt":
            return "fonts", ""
        if ext == ".txt":
            return "text", ""
        if ext == ".bin":
            try:
                with open(path, "rb") as f:
                    text = is_message_table(f.read())
            except OSError:
                text = False
            if text:
                return "text", ""
            # story mode: NNNN.bin is the shot list of the episode whose scene
            # is NNNN+1.bcres (epi000_..., epi001_...)
            rel = os.path.relpath(path, self.raw)
            m = re.match(r"^(\d+)\.bin$", rel)
            if m:
                nxt = os.path.join(self.raw, "%0*d.bcres" % (len(m.group(1)), int(m.group(1)) + 1))
                if os.path.isfile(nxt):
                    lab = self.cgfx(nxt)[1]
                    if re.match(r"^epi\d+", lab):
                        return "data", lab.split("_")[0] + "_shots"
            return "data", ""
        if ext == ".coli":
            return "collision", ""
        return "other", ""

    def run(self, stream_folders, acb_names=None):
        """stream_folders: {acb_relpath: stream_folder_relpath} (relative to raw)."""
        stream_owner = {}
        for acb_rel, folder_rel in stream_folders.items():
            n = _top_number(acb_rel)
            if n is not None:
                stream_owner[folder_rel.replace(os.sep, "/")] = n

        self.check_names(acb_names or {})

        # every raw file. Decide all destinations first (siblings are read),
        #    then move.
        plan = []
        for dp, _, fns in os.walk(self.raw):
            for fn in sorted(fns):
                p = os.path.join(dp, fn)
                plan.append((p, self.destination(p, stream_owner)))
        dropped = [(src, d[1]) for src, d in plan if isinstance(d, tuple)]
        for src, dest in sorted((x for x in plan if not isinstance(x[1], tuple)), key=lambda x: x[1]):
            self.move(src, dest)
        for src, inside in dropped:          # already inside an .awb
            self.index.append((inside.replace(os.sep, "/") + " (entry %s)" % os.path.basename(src),
                               "files/" + os.path.relpath(src, self.raw).replace(os.sep, "/")))
            os.remove(src)
        shutil.rmtree(self.raw, ignore_errors=True)

        with open(os.path.join(self.out, "index.csv"), "w", encoding="utf-8") as f:
            f.write("# sorted path;path in raw mode (--mode raw)\n")
            for a, b in sorted(self.index):
                f.write("%s;%s\n" % (a.replace(os.sep, "/"), b))
        return len(plan)
