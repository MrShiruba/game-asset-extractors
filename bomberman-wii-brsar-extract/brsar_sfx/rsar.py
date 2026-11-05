"""Parser for NW4R sound archives (.brsar, magic ``RSAR``).

A BRSAR is a container: the INFO block describes sounds, banks, players,
files and groups, and the FILE block holds the actual sub-files (RSEQ, RBNK,
RWSD, RWAR...) packed by group.  Every sub-file is identified by a *file id*;
a file can appear in several groups, so we just use the first location.

Only what is needed to locate and play sounds is parsed here.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SOUND_TYPE_SEQ = 1
SOUND_TYPE_STRM = 2
SOUND_TYPE_WAVE = 3

SOUND_TYPE_NAMES = {SOUND_TYPE_SEQ: "SEQ", SOUND_TYPE_STRM: "STRM", SOUND_TYPE_WAVE: "WAVE"}


class FormatError(Exception):
    """Raised when a file does not look like the expected NW4R format."""


class Reader:
    """Tiny big-endian reader over a bytes-like object."""

    __slots__ = ("data",)

    def __init__(self, data: bytes):
        self.data = data

    def u8(self, o: int) -> int:
        return self.data[o]

    def s8(self, o: int) -> int:
        v = self.data[o]
        return v - 256 if v >= 128 else v

    def u16(self, o: int) -> int:
        return struct.unpack_from(">H", self.data, o)[0]

    def s16(self, o: int) -> int:
        return struct.unpack_from(">h", self.data, o)[0]

    def u32(self, o: int) -> int:
        return struct.unpack_from(">I", self.data, o)[0]

    def s32(self, o: int) -> int:
        return struct.unpack_from(">i", self.data, o)[0]

    def f32(self, o: int) -> float:
        return struct.unpack_from(">f", self.data, o)[0]

    def magic(self, o: int) -> bytes:
        return bytes(self.data[o:o + 4])

    def ref(self, o: int) -> Tuple[int, int, int]:
        """NW4R ``DataRef``: (refType, dataType, value). refType 1 = offset."""
        return self.data[o], self.data[o + 1], self.u32(o + 4)

    def cstr(self, o: int) -> str:
        end = self.data.index(b"\0", o)
        return bytes(self.data[o:end]).decode("ascii", "replace")


@dataclass
class SoundEntry:
    index: int
    name: str
    sound_type: int
    file_id: int
    player_id: int
    volume: int            # 0-127, applied linearly (volume / 127)
    player_priority: int
    remote_filter: int
    pan_mode: int
    pan_curve: int
    # SEQ
    seq_offset: int = 0    # start offset inside the RSEQ data
    bank_id: int = -1
    alloc_track: int = 0
    channel_priority: int = 64
    # WAVE (RWSD)
    wsd_index: int = 0
    # STRM
    strm_start: int = 0

    @property
    def type_name(self) -> str:
        return SOUND_TYPE_NAMES.get(self.sound_type, str(self.sound_type))


@dataclass
class BankEntry:
    index: int
    name: str
    file_id: int


@dataclass
class GroupItem:
    file_id: int
    offset: int       # absolute offset of the sub-file in the BRSAR
    size: int
    wave_offset: int  # absolute offset of the attached wave archive (RWAR)
    wave_size: int


@dataclass
class GroupEntry:
    index: int
    name: str
    items: List[GroupItem] = field(default_factory=list)


@dataclass
class FileEntry:
    index: int
    header_size: int
    wave_size: int
    external_name: Optional[str]
    positions: List[Tuple[int, int]]  # (group index, item index)


class Rsar:
    def __init__(self, data: bytes):
        self.data = data
        r = self.r = Reader(data)
        if r.magic(0) != b"RSAR":
            raise FormatError("not a BRSAR file (missing RSAR magic)")
        if r.u16(4) != 0xFEFF:
            raise FormatError("unsupported byte order")
        self.version = r.u16(6)
        symb, _symb_size, info, _info_size = struct.unpack_from(">4I", data, 0x10)
        self.strings = self._read_strings(symb)
        self.sounds: List[SoundEntry] = []
        self.banks: List[BankEntry] = []
        self.files: List[FileEntry] = []
        self.groups: List[GroupEntry] = []
        self._read_info(info)

    # -- SYMB -------------------------------------------------------------
    def _read_strings(self, symb: int) -> List[str]:
        r = self.r
        if r.magic(symb) != b"SYMB":
            raise FormatError("SYMB block not found")
        base = symb + 8
        table = base + r.u32(base)
        return [r.cstr(base + r.u32(table + 4 + 4 * i)) for i in range(r.u32(table))]

    def string(self, idx: int) -> str:
        if 0 <= idx < len(self.strings):
            return self.strings[idx]
        return ""

    # -- INFO -------------------------------------------------------------
    def _table(self, base: int, ref_offset: int) -> List[int]:
        r = self.r
        tab = base + r.ref(ref_offset)[2]
        return [base + r.ref(tab + 4 + 8 * i)[2] for i in range(r.u32(tab))]

    def _read_info(self, info: int) -> None:
        r = self.r
        if r.magic(info) != b"INFO":
            raise FormatError("INFO block not found")
        base = info + 8

        for i, so in enumerate(self._table(base, base + 0)):
            s = SoundEntry(
                index=i,
                name=self.string(r.u32(so)) or f"SOUND_{i:04d}",
                file_id=r.u32(so + 4),
                player_id=r.u32(so + 8),
                volume=r.u8(so + 0x14),
                player_priority=r.u8(so + 0x15),
                sound_type=r.u8(so + 0x16),
                remote_filter=r.u8(so + 0x17),
                pan_mode=r.u8(so + 0x28),
                pan_curve=r.u8(so + 0x29),
            )
            det = base + r.ref(so + 0x18)[2]
            if s.sound_type == SOUND_TYPE_SEQ:
                s.seq_offset = r.u32(det)
                s.bank_id = r.u32(det + 4)
                s.alloc_track = r.u32(det + 8)
                s.channel_priority = r.u8(det + 12)
            elif s.sound_type == SOUND_TYPE_WAVE:
                s.wsd_index = r.u32(det)
                s.alloc_track = r.u32(det + 4)
                s.channel_priority = r.u8(det + 8)
            elif s.sound_type == SOUND_TYPE_STRM:
                s.strm_start = r.u32(det)
            self.sounds.append(s)

        for i, bo in enumerate(self._table(base, base + 8)):
            self.banks.append(BankEntry(i, self.string(r.u32(bo)), r.u32(bo + 4)))

        self.players: List[str] = [self.string(r.u32(po)) for po in self._table(base, base + 16)]

        for i, fo in enumerate(self._table(base, base + 24)):
            ext_type, _, ext_off = r.ref(fo + 0x0C)
            ext = None
            if ext_off:
                ext = r.cstr(base + ext_off)
            positions = []
            for po in self._table(base, fo + 0x14):
                positions.append((r.u32(po), r.u32(po + 4)))
            self.files.append(FileEntry(i, r.u32(fo), r.u32(fo + 4), ext, positions))

        for i, go in enumerate(self._table(base, base + 32)):
            name = self.string(r.u32(go))
            g_off, _g_size, w_off, _w_size = struct.unpack_from(">4I", self.data, go + 0x10)
            grp = GroupEntry(i, name)
            for io in self._table(base, go + 0x20):
                fid, o, sz, wo, wsz = struct.unpack_from(">5I", self.data, io)
                grp.items.append(GroupItem(fid, g_off + o, sz, w_off + wo, wsz))
            self.groups.append(grp)

        self._file_location: Dict[int, GroupItem] = {}
        for grp in self.groups:
            for it in grp.items:
                self._file_location.setdefault(it.file_id, it)

    # -- file access ------------------------------------------------------
    def has_file(self, file_id: int) -> bool:
        return file_id in self._file_location

    def get_file(self, file_id: int) -> Tuple[bytes, bytes]:
        """Return ``(file_data, wave_archive_data)`` for a file id.

        ``wave_archive_data`` is the RWAR attached to banks / RWSDs (may be empty).
        """
        it = self._file_location.get(file_id)
        if it is None:
            ext = self.files[file_id].external_name if file_id < len(self.files) else None
            if ext:
                raise FormatError(f"file {file_id} is external ({ext}) and not inside the BRSAR")
            raise FormatError(f"file {file_id} is not stored in any group")
        main = self.data[it.offset:it.offset + it.size]
        wave = self.data[it.wave_offset:it.wave_offset + it.wave_size] if it.wave_size else b""
        return main, wave

    def file_groups(self, file_id: int) -> List[str]:
        if file_id >= len(self.files):
            return []
        return [self.groups[g].name for g, _ in self.files[file_id].positions if g < len(self.groups)]
