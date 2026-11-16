# Game models to rigged FBX

Convert local character models and mods from **Marvel Rivals, Deadlock, Zenless Zone Zero, and Koikatsu Party** to FBX for Blender and other model pipelines.

The repository name reflects its Marvel Rivals origins. **All four games now use the same application, download, and game selector.** Older v3 releases were Rivals-only; use v4 or newer for the combined application.

## Choose your game

| Source game | Instructions |
|---|---|
| Marvel Rivals packages | [Marvel Rivals](docs/games/marvel-rivals.md) |
| Deadlock VPK mods | [Deadlock](docs/games/deadlock.md) |
| Zenless Zone Zero INI/buffer mods | [ZZZ](docs/games/zzz.md) |
| Koikatsu cards and Maker exports | [Koikatsu](docs/games/koikatsu.md) |
| Koikatsu CharaStudio characters | [Studio export route](docs/games/koikatsu-studio.md) |

## Install and start

1. Download **GameModelsToFBX-v4.0.0-Windows.zip** from [Releases](https://github.com/ClubVixen/marvel-rivals-fbx-converter/releases/latest).
2. Extract the entire ZIP. Keep the EXE, `_internal`, tools, scripts, and other folders together. Python is included; Blender and game-specific external tools are installed separately.
3. Run **GameModelsToFBX.exe** and select your **Source game**.
4. Click **Create / Edit configuration**. Replace the example paths with yours, using forward slashes in JSON paths, and save. Only configure fields needed by your chosen game. Saving as `multigame.local.json` beside the EXE makes it load automatically next time.
5. Choose the output folder. Use **Add files** or **Add mod folder**, then **Inspect / Read Mods**.
6. Resolve any missing dependencies using the game guide above, then click **Convert Batch to FBX**.

The configuration editor serves all games. For Rivals, set `blender` and `game` (the installed `Content/Paks` folder); leave `mappings` empty to use the bundled mapping. For other games, follow their linked configuration tables. Koikatsu's card conversion button converts Sunshine cards to KK cards; assembling/exporting a character still requires Maker or Studio and its mods.

### Run the same application from source

Install Python 3.10+ and the external tools described in your game guide. In the repository folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Rivals additionally needs the locally built backend and mapping described in [building](docs/building.md). The source and packaged entry points open the same GUI. Existing `converter.py` and `multigame.py` commands remain available for older scripts.

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
- [Build the combined application locally](docs/building.md)
- [For LLMs: task entry point and technical context](for-llms/README.md)

The LLM folder contains automation instructions, code pointers, and historical validation notes; normal conversion steps are in the game guides above.
