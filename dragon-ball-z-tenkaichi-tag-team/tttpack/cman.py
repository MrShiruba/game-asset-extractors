"""
Camera moves (.cman, signature CMAn) and their text form (--txt).

Header (little-endian), as read by the EBOOT (relocation 0x089A92D0, evaluation
0x089A9374):

    +0x00  "CMAn"
    +0x04  u32  non-zero while the offsets below are not yet turned into pointers
    +0x08  u32  offset of the channel table
    +0x0C  u32  channel count (6 in every file seen)
    +0x10  f32  0, or 10.0 in some files
    +0x14  f32  length in frames
    +0x18  u32  offset of the start values (8 floats, copied to the output first)
    +0x1C  u32  offset of an extra block, ignored when +0x20 < 2
    +0x20  u32

Channel table: 16 bytes per channel: u32 output slot, u32 offset of its keys, u32 key
count, 0. Output slots 0..2 are the camera position (x, y, z) and 3..5 its rotation
(radians; the EBOOT passes them on as one vector).

Keys: 32 bytes: u32 flags, f32 frame, f32 value, then 5 words the evaluator does not
read. With flag 0x10 the value is held until the next key, otherwise it is linearly
interpolated between the two keys around the current frame.
"""
import struct

SLOTS = ("x", "y", "z", "rot_x", "rot_y", "rot_z", "slot_6", "slot_7")
HOLD = 0x10


def parse(data):
    """{"frames", "start", "channels": [(slot, [(flags, frame, value), ...])]} or None."""
    if data[:4] != b"CMAn" or len(data) < 0x24:
        return None
    table, count = struct.unpack_from("<II", data, 8)
    frames = struct.unpack_from("<f", data, 0x14)[0]
    start_at = struct.unpack_from("<I", data, 0x18)[0]
    if not 0 < count <= 16 or table + 16 * count > len(data) or start_at + 32 > len(data):
        return None
    start = struct.unpack_from("<8f", data, start_at)
    channels = []
    for k in range(count):
        slot, keys_at, keys, _ = struct.unpack_from("<4I", data, table + 16 * k)
        if keys_at + 32 * keys > len(data):
            return None
        channels.append((slot, [struct.unpack_from("<Iff", data, keys_at + 32 * j)
                                for j in range(keys)]))
    return {"frames": frames, "start": start, "channels": channels}


def to_text(data):
    """A readable listing of a camera move, or None when it is not one."""
    move = parse(data)
    if move is None:
        return None
    lines = ["camera move, %g frames" % move["frames"],
             "start: " + ", ".join("%s=%g" % (SLOTS[k], v) for k, v in enumerate(move["start"][:6])),
             ""]
    for slot, keys in sorted(move["channels"]):
        name = SLOTS[slot] if slot < len(SLOTS) else "slot_%d" % slot
        lines.append("%s (%d keys):" % (name, len(keys)))
        for flags, frame, value in keys:
            lines.append("  frame %6g  %12.5f%s" % (frame, value, "  (hold)" if flags & HOLD else ""))
    return "\n".join(lines) + "\n"
