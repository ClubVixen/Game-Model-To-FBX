# Build from source

[Back to README](../README.md)

The multi-game GUI only needs the [Python setup](../README.md#multi-game-application-from-source) plus its game-specific external tools. The .NET backend below is for Marvel Rivals.

1. Install Python 3.10+, .NET SDK 10, and Blender.
2. Install `requirements.txt` into your Python environment.
3. Follow [the pinned backend build instructions](../backend-source/README.txt) to produce `tools/cue4parse-materials.exe`.
4. Obtain a compatible mapping from [rivals-depot](https://github.com/SpaceDepot/rivals-depot/tree/main/usmap) and save it as `mappings/Marvel.usmap` or select its actual path in the app.
5. Run `python converter.py`.

To package the Windows GUI, install PyInstaller, then run:

```powershell
python -m PyInstaller --noconfirm --onedir --windowed --name RivalsFbxConverter converter.py
```

Copy `blender_convert.py`, `tools/`, and `mappings/` alongside the executable. Material and hair-baking modules are bundled automatically. Keep licenses and third-party notices with the distribution.
