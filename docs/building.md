# Build the combined application locally

[Back to README](../README.md)

All games share one Python entry point. Only the Rivals extraction backend needs .NET.

1. Install Python 3.10+, .NET SDK 10, and Blender.
2. Install `requirements.txt` into your Python environment.
3. Follow [the pinned backend build instructions](../backend-source/README.txt) to produce `tools/cue4parse-materials.exe`.
4. Obtain a compatible mapping from [rivals-depot](https://github.com/SpaceDepot/rivals-depot/tree/main/usmap) and save it as `mappings/Marvel.usmap` or select its actual path in the app.
5. Run `python app.py` to open the shared GUI.

## Package on Windows

Build on your Windows computer; no GitHub Actions build is required or configured.

```powershell
python -m pip install -r requirements.txt pyinstaller
python build_local.py --assets C:/Build/ConverterAssets --output C:/Build/GameModelsToFBX
```

`--assets` points to a local directory containing `tools/cue4parse-materials.exe`, `mappings/Marvel.usmap`, and the accompanying `licenses/` and tool notices. These may come from your local backend build or a previous complete portable release. Keep third-party notices when redistributing.

The script builds `dist/GameModelsToFBX/GameModelsToFBX.exe`, copies the conversion scripts, readers, guides and assets, and creates a Windows ZIP and SHA-256 file. Upload those locally built artifacts to a GitHub release. Do not upload personal configuration, input models, game files, or exported characters.

The package includes Python and its dependencies. Blender, Source 2 Viewer, XXMITools, and the Koikatsu game/exporter dependencies remain external and are described in the individual game guides. The Studio bridge source and setup steps are included; vendor game assemblies are not.
