# Dragon Ball Z: Budokai 2 (GameCube) – sound banks for vgmstream

A [vgmstream](https://vgmstream.org) configuration to play the `.sd` / `.st` sound banks of
**Dragon Ball Z: Budokai 2** on **GameCube**.

vgmstream cannot open these banks by itself. The `.sd.txth` file in this folder describes
their format, so that vgmstream can read every sound they hold. Nothing needs to be run:
there is no script.

---

## Requirements

- [vgmstream](https://vgmstream.org), or a player that uses it (for example foobar2000 with
  the vgmstream component)

---

## Usage

1. Get the `.sd` and `.st` files from your own copy of the game.
2. Copy `.sd.txth` into the same folder (keep the name as it is, with the leading dot).
3. Open a `.sd` file with vgmstream. Each sound of the bank is a subsong.

---

## Format

A sound bank is a pair of files with the same name:

- `.st`: the header (sound table and decoding coefficients);
- `.sd`: the sound data, mono GameCube DSP ADPCM.

All values are big-endian.

**`.st` file**

| Offset | Size | Meaning |
|---|---|---|
| 0x00 | u32 | number of sounds N |
| 0x04 | N x 0x1C | one entry per sound (see below) |
| 0x04 + N x 0x1C | N x 0x5C | one block of DSP decoding coefficients per sound |

**Sound entry** (0x1C bytes):

| Offset | Size | Meaning |
|---|---|---|
| 0x08 | u32 | sample rate |
| 0x14 | u32 | end address, in nibbles |
| 0x18 | u32 | start address, in nibbles |

Addresses count 4-bit nibbles in the `.sd` file. DSP data is made of 16-byte frames, each
holding 2 header nibbles and 28 samples, which is what the sample count formula in
`.sd.txth` accounts for. vgmstream evaluates TXTH formulas strictly from left to right,
without brackets, so that computation is split into two lines.

---

## Disclaimer

- This project is **not affiliated** with Bandai Namco, Dimps, Atari or Nintendo.
- **No game data** is included or distributed here: you need your own copy of the game.

## License

This project is released under **The Unlicense** (public domain). See the `LICENSE` file
at the root of the repository.
