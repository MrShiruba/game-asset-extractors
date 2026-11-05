# brsar-sfx

Extract every sound of a Wii game from its NW4R sound archive (`.brsar`): sound
effects, jingles and music.

It was written for **Bomberman Blast** – the Japanese Wii release that includes a
Story Mode (archive `WiiBombSND.brsar`) – but the code makes no assumption about the
game, so it should work with other NW4R games too.

```
python -m brsar_sfx WiiBombSND.brsar -o sfx
```

You get one file per sound (`SE_SYS_CURSOR.brstm`, `SE_FIRE_KANTSU_L.brstm`,
`SEQ_JG01.brstm`, …), sorted into category folders, plus a `manifest.csv` that
describes every file. Every sound of the archive is extracted: there is nothing to
enable. Use `--include` / `--exclude` if you only want part of it.

> No game data is included in this repository. Use your own copy of the game.

---

## Why a tool like BrawlBox shows (almost) nothing

If you open the archive in BrawlBox, you can only play a handful of sounds (in
Bomberman Blast: the menu sounds). The rest of the archive is not broken. It just
doesn't contain any audio files for the sound effects.

In an NW4R archive, a sound can be one of three things:

| Type | What it is | Playable as-is? |
|------|------------|-----------------|
| `WAVE` (RWSD) | a sound that plays one sample | yes – this is what BrawlBox can play |
| `STRM` | an external `.brstm` stream (usually music) | yes, but it lives outside the BRSAR |
| `SEQ` (RSEQ) | a small **program** in Nintendo's MML byte code that plays *notes* on an **instrument bank** (RBNK) whose samples are in a **wave archive** (RWAR) | **no** – it has to be *performed* by the sound engine |

Bomberman Blast has 466 sounds. **461 of them are sequences** and only 5 are wave
sounds (`SE_SYS_KETTEI_S`, `SE_SYS_COUNT_UP`, `SE_SYS_COUNT_DOWN`, `SE_SYS_WIFI_OK`,
`SE_SYS_HURRY`). A sequence is like a tiny MIDI file. An explosion, for example, is
three tracks that play pitched-down noise samples, with pitch sweeps, vibrato and
ADSR envelopes. The sound you hear only exists once the engine plays it. If you
"extract" the samples, you get the short raw instrument samples, not the sound effects.

This tool therefore contains an offline **re-implementation of the NW4R sound
engine**. It plays every sequence the way the Wii does and records the output.

## Installation

Python 3.8+ and numpy are required. scipy is optional (it speeds up the low-pass
filter used by a few sounds).

```
pip install numpy scipy
# optional, gives you a `brsar-sfx` command:
pip install .
```

## Usage

```
python -m brsar_sfx INPUT.brsar [-o OUTPUT_DIR] [-c adpcm|pcm16] [options]
```

Common examples:

```bash
# every sound of the archive, lossless (16-bit PCM inside the BRSTM, default)
python -m brsar_sfx WiiBombSND.brsar -o sfx

# smaller files: DSP-ADPCM inside the BRSTM (lossy, ~3.5x smaller)
python -m brsar_sfx WiiBombSND.brsar -o sfx -c adpcm


# only some sounds (regular expression on the name)
python -m brsar_sfx WiiBombSND.brsar --include "^SE_FIRE_" -o fire

# inspection tools
python -m brsar_sfx WiiBombSND.brsar --list                 # table of all sounds
python -m brsar_sfx WiiBombSND.brsar --disasm SE_GIM_UFO    # sequence code of a sound
python -m brsar_sfx WiiBombSND.brsar --dump-raw raw         # untouched native sub-files
```

| Option | Default | Meaning |
|--------|---------|---------|
| `-c, --codec` | `pcm16` | codec inside the `.brstm` files: `pcm16` (lossless) or `adpcm` (small, lossy) |
| `--include / --exclude REGEX` | – | filter sounds by name |
| `--loops N` | 2 | stop a looping sequence after N passes … |
| `--loop-min-seconds S` | 5 | … but only after at least S seconds |
| `--max-seconds S` | 20 | how long to keep a sound that holds a note forever (an ambience on a looped sample, for example); music and other sequences that keep progressing are not affected |
| `--fade-seconds S` | 2 | fade-out applied when the hard limit is reached |
| `--no-normalize` | off | clip instead of lowering the volume of the few sounds that exceed 0 dBFS |
| `--stereo` | off | always write 2 channels (by default, identical L/R is written as mono) |
| `--seed N` | `0x12345678` | seed of the engine's random generator (some sounds use random pitch/volume) |
| `--flat` | off | no category sub-folders |
| `-j N` | CPU count (max 8) | worker processes |

On a 2-core machine, the 466 sounds of Bomberman Blast (420 sound effects, 10 jingles,
36 music tracks) take a little over a minute in `pcm16`. The `adpcm` codec adds
the encoding time on top.
Music is long: each looping track plays its 2 loops, which takes up to almost 4 minutes.

## Output format

The output is always **BRSTM** (`.brstm`), the Wii's own audio stream format (the one
NW4R games use for streamed music), at the engine's native **32 000 Hz**. A BRSTM is
only a container. It can hold two codecs, and you pick one with `-c / --codec`:

| `--codec` | Audio inside the BRSTM | Lossless? | Bomberman Blast set |
|-----------|------------------------|-----------|---------------------|
| `pcm16` (default) | 16-bit PCM | **yes**, bit-exact render, same duration | ~118 MB |
| `adpcm` | Nintendo DSP-ADPCM, 4 bits/sample | no (re-encoded) | ~35 MB |

Identical L/R channels are written as mono, which halves the size of most sounds.

This tool doesn't convert to WAV, FLAC, etc. Existing tools do that well, for example
`vgmstream-cli -o out.wav SE_SYS_CURSOR.brstm`. Converting a `pcm16` BRSTM gives the
lossless render.

### Players and converters

* **vgmstream** (foobar2000 component, Winamp/XMPlay plugins, `vgmstream-cli`, web
  player) plays both codecs correctly. Every file produced for Bomberman Blast was
  checked with it: `pcm16` files decode bit-exact.
* **ffmpeg** (and the tools built on it) plays `adpcm` files. Its DSP-ADPCM decoder
  rounds slightly differently from the Wii hardware, so the output is clean but not
  bit-identical. **Do not use ffmpeg for `pcm16` BRSTMs.** Its demuxer applies an
  ADPCM-only size correction to the last block of PCM streams too, so the end of the
  file comes out wrong. Use vgmstream for those.
* BrawlBox / BrawlCrate, and any Wii homebrew or mod that loads BRSTMs.

### About the ADPCM encoder

The encoder is part of this project (pure Python + numpy). It searches all 8 predictors
and the best scales for every 14-sample frame, so the quality is comparable to
Nintendo's own `DSPADPCM` tool. On the Bomberman Blast set, the median SNR is about
35 dB. Noise-like sounds (buzzing, hiss) go down to about 20 dB, which is normal for
4-bit ADPCM. Use `--codec pcm16` when you need the exact render.

### "Native" in the strict sense: `--dump-raw`

Because the sound effects are sequences, there is no "original audio file" to copy out
unchanged. A BRSTM is a *re-encoded rendering* of what the engine plays. If you want
the untouched game data instead (for modding, or for feeding another tool), use
`--dump-raw DIR`. It writes every sub-file in its own format (`.brseq`, `.brbnk`,
`.brwsd`, `.brwar`) and adds an `index.json` that says which sound uses which sequence
offset, bank and wave archive.

## Output layout

```
sfx/
  System/SE_SYS_CURSOR.brstm
  Explosions/SE_FIRE_KANTSU_L.brstm
  Player Actions/Wii Remote Speaker/SE_ACT_BOMB_PUNCH_R.brstm
  ...
  manifest.csv      one row per sound
  settings.json     the options used
```

The file names are the game's internal labels. For Bomberman Blast, the folders come
from the label prefixes:

| Prefix | Folder |
|--------|--------|
| `SE_SYS_` | System (menus) |
| `SE_ACT_` | Player Actions |
| `SE_FIRE_` | Explosions |
| `SE_PNL_` | Power-Ups (panels) |
| `SE_SICK_` | Skull Ailments |
| `SE_APL_` | Taunts (appeals) |
| `SE_GIM_` | Battle Gimmicks |
| `SE_RSLT_` | Results |
| `SE_ST_MENU_` / `CMN_` / `ZK_` / `BS_` / `GIM_` | Story Mode – Shop & Menus / Common / Enemies (*zako*) / Bosses / Stage Gimmicks |
| `SE_DMO_` | Story Mode – Cutscenes (`OP` opening, `ED` ending) |
| `SE_HJ_` | Bomberman for Beginners (*Hajimete no Bomberman*, the tutorial mode) |
| `SEQ_JG` | Jingles |
| `SEQ_MU` | Music |

`A1`–`A6` in the names are the story areas, and `VO` is a boss voice. A name that
ends in `_R` is the variant the game sends to the **Wii Remote speaker**. Those go
into a `Wii Remote Speaker` sub-folder. For other games, the folder is the name of
the archive "player" the sound uses (for example `PLY_SE_SYS`).

`manifest.csv` columns: `name, folder, type, channels, seconds, volume, looped, capped,
normalized_gain_db, notes`:

* `looped`: the sequence loops forever in the game. It was stopped after `--loops`
  passes, and its notes were released naturally, like when the game stops the sound.
* `capped`: the sound never ends on its own and stops progressing (for example an
  ambience that holds a note on a looped sample). It was kept for `--max-seconds`
  and then faded out. Music is never cut this way.
* `normalized_gain_db`: a negative value means the render went above 0 dBFS, and the
  file was turned down by that amount to avoid clipping. On the Wii, the final mix
  would clip.

## Accuracy

The engine follows the NW4R runtime as documented by the
[`doldecomp/ogws`](https://github.com/doldecomp/ogws) decompilation (`SeqPlayer`,
`SeqTrack`, `MmlParser`, `Channel`, `EnvGenerator`, `Lfo`, `Voice`, `Util`):

* 3 ms engine frames (96 samples), with the same tick and tempo maths;
* all MML commands: notes, waits, calls, loops, jumps, `opentrack`, variables,
  conditionals, random arguments, `tie`, mute, damper;
* instrument lookup through the bank's key and velocity split tables;
* ADSR envelope with the runtime's attack table and decay/release rates, LFO
  (pitch/volume/pan, depth/speed/range/delay), sweep pitch and portamento, pitch bend
  and range, transposition, instrument tuning;
* the volume laws (velocity², track volume², main volume², sound volume), the NW4R pan
  curves (sqrt by default: −3 dB at the centre), main send, and the AX one-pole
  low-pass filter;
* 4-point interpolated resampling of every sample (11–44.1 kHz) to 32 kHz, with
  loop points.

What is **not** reproduced:

* **Effects sends** (reverb, delay…): the game sets up these AUX effects at run time,
  and they are not stored in the archive. The renders are "dry".
* Surround / Dolby Pro Logic II, the Wii Remote speaker filter, and 3D positioning
  (the game pans some sounds based on where things happen on screen).
* Voice stealing between sounds, and sequence variables that the game sets from its
  code (they keep their default value, −1).
* Sounds that use random parameters are rendered with one fixed seed (`--seed`), so
  one possible variation.

## How it works

```
brsar_sfx/
  rsar.py        BRSAR container: symbols, sound/bank/player/file/group tables
  formats.py     RSEQ, RBNK, RWAR, RWAV, RWSD parsers
  dsp.py         DSP-ADPCM decoder, coefficient design and lane-vectorised encoder
  player.py      the sound engine: sequence interpreter, channels, envelopes, mixing
  writers.py     BRSTM writer (DSP-ADPCM or PCM16)
  extract.py     selection, parallel rendering, encoding, manifest, raw dump
  disasm.py      MML disassembler (--disasm)
  categories.py  output folder names
  cli.py         command line
```

1. **Parse** the BRSAR (`rsar.py`). Each sound points to a file id. A sequence
   sound also has a start offset inside its RSEQ and a bank id. Files are located
   through the groups that pack them.
2. **Play** (`player.py`). Track 0 starts at the sound's offset, and tracks are
   parsed tick by tick. Each note asks the bank for an instrument (program → key
   split → velocity split → wave) and allocates a *channel*. Every 3 ms, each channel
   computes its pitch, volume envelope ramp, pan gains and filter, exactly like
   `Channel::Update`. Those per-frame parameters are recorded, and once the channel
   ends, they are rendered in one vectorised pass and mixed into the output.
3. **Encode** (`dsp.py`, `adpcm` codec only). The DSP-ADPCM recursion can't be vectorised along time,
   so it is vectorised *across streams*: all channels of all sounds are encoded
   together, one frame at a time, as numpy "lanes". This keeps pure Python fast.
4. **Write** the BRSTM files and the manifest.

## Tests

```
pip install pytest
python -m pytest tests
BRSAR=/path/to/WiiBombSND.brsar python -m pytest tests   # + integration test
```

## Credits

* NW4R runtime behaviour: the [doldecomp/ogws](https://github.com/doldecomp/ogws)
  decompilation project.
* Format knowledge: the BrawlBox / BrawlCrate, vgmstream and VGMTrans communities.
