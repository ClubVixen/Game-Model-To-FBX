# Game models to rigged FBX

Convert local character models and mods from **Marvel Rivals, Deadlock, Zenless Zone Zero, and Koikatsu Party** to FBX for Blender and other model pipelines.

## Choose your game

| Game / input | Start here | Application |
|---|---|---|
| Marvel Rivals `.pak` / `.utoc` / `.ucas` | [Marvel Rivals instructions](docs/games/marvel-rivals.md) | `RivalsFbxConverter.exe` or `python converter.py` |
| Deadlock `.vpk` | [Deadlock instructions](docs/games/deadlock.md) | `python multigame_gui.py` |
| Zenless Zone Zero mod folder with INI and buffers | [ZZZ instructions](docs/games/zzz.md) | `python multigame_gui.py` |
| Koikatsu Party card, Maker export, or Studio character | [Koikatsu instructions](docs/games/koikatsu.md) | Game exporter, then `python multigame_gui.py` |

**The portable Marvel Rivals release and the multi-game GUI are separate applications.** The portable release does not include the multi-game front end. Use the source setup below for Deadlock, ZZZ, and Koikatsu.

## Install and start

### Marvel Rivals portable application

1. Download the portable Windows ZIP from [Releases](https://github.com/ClubVixen/marvel-rivals-fbx-converter/releases).
2. Extract the **entire ZIP**, keeping its files together. Install Blender separately.
3. Run `RivalsFbxConverter.exe` and follow the [Marvel Rivals guide](docs/games/marvel-rivals.md).

### Multi-game application from source

1. Install Python 3.10 or newer and Blender. Koikatsu Maker/KKBP uses an additional Blender 3.6 installation; Studio does not.
2. Clone or download this repository and open PowerShell in its folder.
3. Create a Python environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item multigame.example.json multigame.local.json
.\.venv\Scripts\python.exe multigame_gui.py
```

4. Edit `multigame.local.json` with your actual executable, game, and asset paths. JSON paths can use forward slashes, such as `C:/Tools/Blender/blender.exe`. Use the configuration keys listed in your game's guide; example paths are placeholders.
5. Select the **Source game**, **Configuration JSON**, and output folder. Add the input files or mod folder.
6. Click **Inspect / Read Mods**, resolve missing dependencies, then click **Convert Batch to FBX**.

## Find and use your output

Each conversion gets a separate job folder under the output directory you selected. Marvel Rivals places FBXs in its job's `FBX/` folder. Multi-game jobs include FBX, editable Blender scenes, external textures, and logs. Keep the FBX, `.blend`, and `textures/` together when moving multi-game exports. The Koikatsu guide explains editing the exported PNGs.

An FBX is a model interchange file, **not an installable game mod**. For Deadlock replacement skins, continue with the [hero-swap handoff](docs/deadlock-handoff.md).

## Before converting

- Supply your own game installation, mod files, and required dependencies. Game models, cards, zipmods, and vendor assemblies are not included.
- Koikatsu cards describe a character; they do not contain every required mesh or texture. Load the character with its dependencies before exporting.
- ZZZ buffer mods need a matching reference dump, skeleton, and bone map. A folder of buffers alone is insufficient for a correctly rigged character.
- FBX materials approximate game shaders. Runtime physics, jiggle, animation constraints, and special shader effects need destination-specific setup.

## More information

- [Troubleshooting](docs/troubleshooting.md)
- [Build the Marvel Rivals application from source](docs/building.md)
- [For LLMs: task entry point and technical context](for-llms/README.md)

The LLM folder contains automation instructions, code pointers, and historical validation notes; normal conversion steps are in the game guides above.
