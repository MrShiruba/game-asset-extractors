# Excitebike: World Rally (WiiWare) Archive Extractor

A Python script to unpack `.res`, `.trk`, and `.car` archive files extracted from *Excitebike: World Rally* (WiiWare).

The game stores its assets inside custom `0TSR` archives compressed with a modified version of **QuickLZ Level 3**. This tool decompresses the main `tocres.res` archive to retrieve the table of contents (`.toc`) files, then extracts all sub-files into organized directories based on their type.

---

## Features

- **QuickLZ L3 Decompression**: Native pure-Python implementation of the QuickLZ L3 algorithm used by the game engine.
- **TOC Parsing**: Automatically parses `tocres.res` to map every archive to its respective `.toc` index file.
- **Automatic Folder Structuring**: Categorizes extracted assets into subdirectories named after their internal type flags (e.g., textures, audio, track data) or `misc`.
- **Batch Processing**: Extracts all `.res`, `.trk`, and `.car` files found in the source directory in a single run.

---

## Requirements

- **Python 3.6+** (uses standard library modules: `os`, `struct`, `sys`). No external dependencies required.

---

## Usage

Run the script from the command line by providing the path to the extracted application directory (e.g., `00000002.app` contents):

```bash
python3 ebwr_extract.py <input_directory> [output_directory]

