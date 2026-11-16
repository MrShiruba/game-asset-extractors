"""
Tests that need no game data (synthetic files), plus an optional run on a real sample:

    python3 -m unittest discover tests
    TTT_SAMPLE=sample.bin python3 -m unittest discover tests     # also extract a sample

A sample is made with tools/make_sample.py from your own PACKFILE.BIN.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tttpack import archive, audio_map, cman, effect, identify, layout, names, pgd, sound_bank, unlocks  # noqa: E402,E501
from tttpack.packfile import KEY, PackFile, align                                         # noqa: E402


def make_archive(parts):
    """Nested big-endian archive: u32 count, count + 1 offsets, parts aligned."""
    table = 4 + 4 * (len(parts) + 1)
    pos = align(table, archive.ALIGN)
    offsets, body = [], b""
    for part in parts:
        offsets.append(pos + len(body))
        body += part + bytes(align(len(part), archive.ALIGN) - len(part))
    offsets.append(pos + len(body))
    head = struct.pack(">I%dI" % len(offsets), len(parts), *offsets)
    return head + bytes(pos - len(head)) + body


def make_cman(frames=120.0):
    """6 channels, 2 keys each (slot k goes from k to k + 10)."""
    table, start, keys = 0x50, 0x30, 0xB0
    data = bytearray(keys + 6 * 2 * 32)
    struct.pack_into("<4sIIIffII", data, 0, b"CMAn", 6, table, 6, 0.0, frames, start, 0)
    struct.pack_into("<8f", data, start, *range(8))
    for k in range(6):
        at = keys + k * 64
        struct.pack_into("<4I", data, table + 16 * k, k, at, 2, 0)
        struct.pack_into("<Iff", data, at, 0x22, 0.0, float(k))
        struct.pack_into("<Iff", data, at + 32, 0x10, frames, float(k + 10))
    return bytes(data)


def make_packfile(path, blobs):
    """A PACKFILE with the given entries (stored, not compressed)."""
    table, data, sector = b"", b"", 0
    for index, blob in enumerate(blobs):
        table += struct.pack("<4I", sector ^ KEY, len(blob) ^ index, 0 ^ KEY, 0 ^ index)
        padded = blob + bytes(align(len(blob), 0x800) - len(blob))
        data += padded
        sector += len(padded) // 0x800
    head = b"PacK" + struct.pack("<I", len(blobs)) + bytes(8) + table
    with open(path, "wb") as f:
        f.write(head + bytes(align(len(head), 0x1000) - len(head)) + data)


class Formats(unittest.TestCase):
    def test_archive_parts(self):
        parts = [b"a" * 64, b"", b"x" * 128]        # parts keep their padding: aligned here
        self.assertEqual(archive.parts(make_archive(parts)), parts)
        self.assertIsNone(archive.parts(b"\0\0\0\x05garbage"))

    def test_cman(self):
        move = cman.parse(make_cman())
        self.assertEqual(move["frames"], 120.0)
        self.assertEqual([slot for slot, _ in move["channels"]], list(range(6)))
        self.assertEqual(move["channels"][2][1], [(0x22, 0.0, 2.0), (0x10, 120.0, 12.0)])
        text = cman.to_text(make_cman())
        self.assertIn("rot_x (2 keys):", text)
        self.assertIn("(hold)", text)
        self.assertIsNone(cman.parse(b"nope" * 20))

    def test_unlock_list(self):
        data = struct.pack("<I3i3i", 2, 0, 77, 5, 5, 143, -1)
        text = unlocks.to_text(data, "unlocks_by_battles_played")
        self.assertIn("character;77;5", text)
        self.assertIn("customize item;143;-1", text)
        self.assertIsNone(unlocks.to_text(data, "something_else"))

    def test_effect_header(self):
        head = bytearray(0x80)                           # 0x40 header + one 0x20 layer, padded
        head[0], head[4] = 0x20, 1                       # flags, one layer
        head[0x40:0x44] = bytes((0x10, 1, 1, 0))         # glows: 1 item, 1 texture
        self.assertEqual(effect.header(bytes(head)), [(0x10, 1, 1)])
        self.assertIsNone(effect.header(bytes(0x81)))

    def test_aes(self):                                  # FIPS-197 appendix C.1
        keys = pgd._expand(bytes(range(16)))
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        cipher = pgd._encrypt_block(keys, plain)
        self.assertEqual(cipher.hex(), "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual(pgd._decrypt_block(keys, cipher), plain)
        self.assertIsNone(pgd.decrypt(b"\0PGD" + bytes(0x100)))

    def test_vag(self):
        header = bytearray(0x40)
        header[:4] = b"PPHD"
        struct.pack_into("<I", header, 0x18, 0x10)       # PPVA at 0x10
        header[0x10:0x14] = b"PPVA"
        struct.pack_into("<I", header, 0x24, 0)          # last slot 0: one sample
        struct.pack_into("<4I", header, 0x30, 0, 22050, 32, 0xFFFFFFFF)
        (slot, label, data), = sound_bank.split_vags(bytes(32), bytes(header))
        self.assertIsNone(label)                         # 1 slot: no name list
        self.assertEqual(data[:4], b"VAGp")
        self.assertEqual(struct.unpack_from(">II", data, 12), (32, 22050))
        self.assertEqual(len(data), 48 + 32)

    def test_sample_names(self):
        names_ch = sound_bank._sample_names("sfx_ch.txt")
        self.assertEqual((len(names_ch), names_ch[0], names_ch[32]), (97, "hurt_1_normal", "sonic_sway"))
        self.assertEqual(sound_bank._sample_names("sfx_bt.txt")[6], "strong_whiffed_hit_1")

    def test_ags_name(self):
        ags = b"AGS\0" + bytes(12) + b"00_open\0WINDOW\0BUTTON_01\0\0"
        self.assertEqual(identify.ags_name(ags), "window_button")

    def test_language_slots(self):
        from tttpack.archive import _language_slot
        R, A, E = b"RHG\0", b"AGS\0", b""
        # US title screen: images en/es/fr + empty de/it, then 1 animation + 6 images
        us = [A, E, R, R, R, E, E, A, E, R, R, R, E, E, A]
        self.assertEqual([_language_slot(us, k) for k in (2, 3, 4, 9, 10, 11)],
                         ["en", "es", "fr", "en", "es", "fr"])
        jp = [A, R, E, E, E, E, E, A, R, E, E, E, E, E, A]
        self.assertEqual(_language_slot(jp, 8), "jp")


class Names(unittest.TestCase):
    def test_folders(self):
        folder = lambda index: layout.entry_folder(index, names.entry(index), "bin")
        self.assertEqual(folder(1427), "character/fighters/01427_goku")
        self.assertEqual(folder(14020), "character/render")
        self.assertEqual(folder(13267), "battle")
        self.assertEqual(folder(13261), "battle")
        self.assertEqual(folder(25), "menu/free_battle")
        self.assertEqual(folder(0), "system")
        self.assertEqual(folder(17), "menu/main")
        self.assertEqual(folder(10), "menu/title")
        self.assertEqual(folder(1389), "character/extra")
        self.assertEqual(folder(1004), "story_mode/board")

    def test_audio_paths(self):
        self.assertEqual(audio_map.audio_relpath(4441),
                         "audio/battle_voice/04441_goku/04441_000_intro_1.at3")
        self.assertTrue(audio_map.audio_relpath(4425).startswith("audio/battle_common/04425_"))

    def test_system_parts(self):
        unlock = struct.pack("<I3i", 1, 5, 143, 0) + bytes(48)
        self.assertEqual(names.system_part(0, (35,), unlock), "starting_items")
        self.assertIsNone(names.system_part(0, (35,), b""))

    def test_data_extensions(self):
        cases = {"font_14px": "fnt", "fx03_effect": "fxh", "fx03_particles_2": "fxs",
                 "fx03_particles_2_colors": "fxc", "glow_1_settings_4": "fxs",
                 "particles_colors_3": "fxc", "lighting": "lgt", "waypoints": "wpt",
                 "unlocks_by_story": "unl", "common_param": "dat", "opponents": "dat"}
        for label, ext in cases.items():
            self.assertEqual(names.data_extension(label), ext, label)

    def test_board_object_parts(self):
        sm_obj = next(i for i in range(1000, 1200) if (names.entry(i) or "").startswith("sm_obj_"))
        self.assertEqual(names.archive_part(sm_obj, (50,), 497), "stand")
        self.assertEqual(names.archive_part(sm_obj, (495, 2), 5, (497,)), "charge")


class Extraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_tool(self, packfile, *options):
        out = os.path.join(self.tmp, "out")
        result = subprocess.run([sys.executable, os.path.join(ROOT, "ttt_unpack.py"), packfile, out,
                                 *options], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Errors: 0", result.stdout)
        return out

    def test_synthetic_packfile(self):
        path = os.path.join(self.tmp, "PACKFILE.BIN")
        make_packfile(path, [b"", make_archive([make_cman(), b"plain data"])])
        self.assertEqual(len(PackFile(path).entries), 2)
        out = self.run_tool(path, "--txt")
        written = [os.path.join(d, f) for d, _, files in os.walk(out) for f in files]
        cmans = [f for f in written if f.endswith(".cman")]
        self.assertEqual(len(cmans), 1)
        self.assertTrue(os.path.exists(cmans[0][:-5] + ".txt"))
        with open(os.path.join(out, "index.csv"), encoding="utf-8") as f:
            rows = f.read().splitlines()[1:]
        self.assertEqual(len(rows), 2)                   # the empty entry 0 is listed too
        self.assertEqual(rows[0].split(";")[5:7], ["empty", ""])

    @unittest.skipUnless(os.environ.get("TTT_SAMPLE"), "set TTT_SAMPLE to a sample PACKFILE")
    def test_sample(self):
        out = self.run_tool(os.environ["TTT_SAMPLE"])
        self.assertFalse(os.path.exists(os.path.join(out, "unnamed.txt")),
                         "files with no descriptive name: see unnamed.txt")


if __name__ == "__main__":
    unittest.main()
