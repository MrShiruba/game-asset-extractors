# File formats

All integers are big-endian (SH-2 CPU) unless stated otherwise.

## LZSS compression

On the audio side it is used by the `.PCM` voices (byte mode). The game also uses it for its graphics.

```
u32 header
    bit 31     : mode (0 = bytes, 1 = 16-bit words)
    bits 0-30  : number of decompressed units - 1
```

**Byte mode** (bit 31 = 0)
- One flag byte, read from bit 0 to bit 7. `1` = literal (1 byte), `0` = reference.
- A reference is a **little-endian** `u16` `w`: `distance = w >> 4`, `length = (w & 0xF) + 3`.
- Copy `length` bytes starting at `output[position - distance]`. The copy may overlap the bytes being written, and anything before the start of the buffer reads as 0.

**Word mode** (bit 31 = 1)
- One big-endian `u16` of flags, read from bit 15 to bit 0. `1` = literal (one 16-bit word).
- A reference is a big-endian `u16` with the same split. Distance and length are counted in words.

The stream may be followed by a few padding bytes.

## TON banks (`*_V.BIN`, `*V.BIN`, `WV_*.BIN`, `HAI_*V.BIN`)

This is the Saturn SDK sound bank format, played by the `SDDRVS.TSK` driver (68000/SCSP).

```
u16 offsets[] : [0] mixer, [1] velocity, [2] PEG, [3] PLFO, [4..] voices
                (offsets[0] = table size)
voice         : 4 bytes (byte 2 = layer count - 1, signed), then 32-byte layers
layer:
  +00 u8  key low         +01 u8  key high
  +02 u16 bits 0-3 = address (bits 16-19), bit 4 = 8-bit PCM, bits 5-6 = loop mode
  +04 u16 address (bits 0-15)  -> direct offset into the file
  +06 u16 loop start (in samples)
  +08 u16 end (LEA); sample count = LEA + 1
  +0A..   SCSP registers (envelope, LFO, level...)
  +19 u8  base note
```

Samples are signed PCM, either 8-bit or 16-bit big-endian. The game's sequences play sounds on **key 60**, as checked in `GKSE1.BIN` and `SEALL`. The SCSP plays at 44,100 Hz when the played key equals the base note, so:

```
sample rate = 44100 × 2^((60 − base note) / 12)
              base 72 → 22,050 Hz, base 84 → 11,025 Hz, base 96 → 5,512 Hz
```

The matching sequences (`SEALL`, `XXSE1/2/10/20.BIN`, `WIN_*.BIN`, `HAI_*`...) use the Saturn SDK SEQ format.

## `.PCM` voices

A `.PCM` voice is an LZSS block (byte mode) that decompresses to signed 8-bit mono PCM. The file does not store a sample rate: the voices in `KOJIN/`, `YBT/` and `END/` play at 11,025 Hz, and `BOOG_1.PCM` at 22,050 Hz (checked by listening).
