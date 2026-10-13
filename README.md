# game-asset-extractors

Tools to extract the assets of video games: music, voices, sound effects, images, sprites,
scripts. Each folder holds the tool for one game, with its own README describing how to
use it and the file formats of the game.

No game data is included: you need your own copy of each game.

## Games

| Game | Platform | What the tool does |
|---|---|---|
| [Dragon Ball Z: Budokai 2](dragon-ball-z-budokai-2-gamecube) | GameCube | vgmstream config to play the `.sd` / `.st` sound banks |
| [DreamMix TV World Fighters](dream-mix-tv-world-fighters) (ドリームミックスTV ワールドファイターズ) | GameCube, PS2 | extracts the `.zb` archives (models, textures, sounds, text) |
| [Excitebike: World Rally](excite-bike-world-rally-wiiware) | WiiWare | extracts the `.res`, `.trk` and `.car` archives |
| [KonoSuba: Love For These Clothes Of Desire!](konosuba-clothes-of-desire) | | rebuilds the event CGs from their scrambled atlases |
| [Lucky Star: Net Idol Meister](lucky-star-net-idol-meister) (らき☆すた ネットアイドル・マイスター) | PSP | extracts and sorts voices, music, CGs, sprites, scripts and the quiz |
| [Sora no Otoshimono: DokiDoki Summer Vacation](sora-no-otoshimono-dokidoki-summer-vacation) (そらのおとしもの) | PSP | extracts the `.ptd` archives, voices included |
| [Super Dragon Ball Z](super-dragon-ball-z) (超ドラゴンボールZ) | PS2 | extracts `GAME.DAT`, plus a vgmstream config for the `.ase` sound banks |

## Requirements

Python 3. Some tools also need numpy or Pillow to convert images, and the sound banks are
played with [vgmstream](https://vgmstream.org); see the README of each game.

## License

[The Unlicense](LICENSE) (public domain).
