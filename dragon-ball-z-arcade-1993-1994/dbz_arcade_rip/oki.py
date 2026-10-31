"""OKI MSM6295 sample table parsing."""

# MAME: OKIM6295(config, "oki", 1056000, PIN7_HIGH) -> 1056000 / 132 = 8000 Hz
OKI_RATE = 8000


def read_table(rom):
    """Return list of (index, start, end) for the 127 phrase slots (slot 0 unused)."""
    out = []
    for i in range(1, 128):
        e = rom[i * 8:i * 8 + 8]
        start = int.from_bytes(e[0:3], "big") & 0x3FFFF
        end = int.from_bytes(e[3:6], "big") & 0x3FFFF
        if end > start and start >= 0x400 and end < len(rom):
            out.append((i, start, end))
    return out
