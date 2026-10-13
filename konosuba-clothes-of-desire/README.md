# KonoSuba: Clothes of Desire – CG unscrambler

A tool to rebuild the event CGs of **KonoSuba: God's Blessing on this Wonderful World! Love
For These Clothes Of Desire!** (この素晴らしい世界に祝福を！ この欲深い衣装に寵愛を！).

The game does not store its CGs as plain images. Each CG is cut into small square pieces,
the pieces are shuffled into one or more texture atlases, and a JSON file says where each
piece goes. Identical pieces (a plain background, for instance) are stored only once. This
script reads the JSON and puts the pieces back together, giving the full CG.

---

## Requirements

- **Python 3.6 or later**
- **Pillow**: `pip install pillow` (in a virtual environment on recent Linux distributions)

---

## Getting the files

You need your own copy of the game. The game is made with Unity, and each CG is made of
two kinds of assets, to export with a Unity asset tool:

- a **MonoBehaviour** named after the CG (e.g. `EV019`), exported as JSON: `EV019.json`.
  It is the description of the CG; it holds no pixels;
- the **Texture2D** atlas(es) it refers to, exported as PNG: `EV019_Atlas0.png`.

The JSON gives the name of each atlas it needs (`atlasName`), so export both and put the
PNG files in one folder: the script finds them by name.

---

## Usage

```sh
python unscramble_atlas.py <cg.json> [atlas_folder] [output_folder]
```

| Argument | Meaning |
|---|---|
| `cg.json` | JSON description of the CG: the only file to give, the atlases are found by name |
| `atlas_folder` | folder holding the atlas PNG files (default: the folder of the JSON) |
| `output_folder` | where the rebuilt CGs are written (default: the atlas folder) |

Example:

```sh
python unscramble_atlas.py EV019.json              # atlases next to the JSON
python unscramble_atlas.py EV019.json atlases out  # atlases in atlases/, CGs written to out/
```

One JSON can describe several images (CG variants): `EV019.json` gives `EV019A1.png`,
`EV019A2.png`… Variants share most of their pieces, which is why they are stored together. Images without transparency are saved as
RGB, the others keep their alpha channel.

---

## Format

The JSON fields used:

| Field | Meaning |
|---|---|
| `cellSize` | size of an atlas cell (64) |
| `padding` | border around each piece inside its cell (3); the border repeats the edge pixels |
| `textureDataList` | one entry per image |
| `name` | image name |
| `atlasName` | atlas holding the pieces of this image (name of the PNG, without extension) |
| `width`, `height` | size of the rebuilt image (e.g. 2560 x 1440) |
| `cellIndexList` | for each piece of the image, the atlas cell to copy |
| `transparentIndex` | cell index meaning "empty, leave transparent" (optional) |

How the pieces are placed:

- Each atlas cell holds one usable piece of `cellSize - 2 x padding` = 58 x 58 pixels.
- The image is a grid of `ceil(width / 58)` x `ceil(height / 58)` pieces
  (2560 x 1440 gives 45 x 25 = 1125 pieces).
- `cellIndexList[k]` is the atlas cell to put at position `k` of that grid.
- Both the atlas cells and the image grid are counted row by row **from the bottom**
  (Unity's convention: the origin of a texture is its bottom-left corner).

---

## Disclaimer

- This project is **not affiliated** with the publishers or developers of the game.
- **No game data** is included or distributed here: you need your own copy of the game.
- The script is an independent implementation, written from the structure of the game's
  files. It contains no code from the game.

## License

This project is released under **The Unlicense** (public domain). See the `LICENSE` file
at the root of the repository.
