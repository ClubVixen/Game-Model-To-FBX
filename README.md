# Marvel Rivals to Rigged FBX

Also includes a separate **Mod to FBX** batch reader/converter for Deadlock VPKs,
ZZZ buffer mods, and Koikatsu Party cards/KKBP exports. See
[multi-game setup and limitations](MULTIGAME.md). Start it with
`python multigame_gui.py`; the existing Marvel Rivals application is unchanged.

Windows batch GUI with local game material lookup, inherited base tints, UV1 hair color baking, and rig/embedded-texture validation.

Download the portable Windows ZIP from Releases, extract the entire folder, and run RivalsFbxConverter.exe. Install Blender 4.2 separately. Select your installed game's Content/Paks folder and compatible .usmap in the app. Mod and game models/textures are not included.

See README.txt for usage and limitations. FBX uses portable PBR materials; Unreal's anisotropic hair lighting and runtime effects are approximated. Baked hair retains original UV0 in a separate channel and uses mesh normals instead of the old tangent normal map.

## Build

Use Python 3.10+ and .NET SDK 10. Install requirements.txt. Follow backend-source/README.txt to build the pinned CUE4Parse backend as tools/cue4parse-materials.exe. Get a compatible mapping from https://github.com/SpaceDepot/rivals-depot/tree/main/usmap and save it as mappings/Marvel.usmap.

Run python converter.py, or package with:

    python -m PyInstaller --noconfirm --onedir --windowed --name RivalsFbxConverter converter.py

Copy blender_convert.py, tools/ and mappings/ alongside the executable. The material and hair baking modules are bundled automatically.

## Validation

The local integration suite covers eight gameplay/lobby meshes from four mods: bone/vertex/weighted-vertex counts, armature binding, posed deformation, material slots and embedded images reopened in an isolated directory. Proprietary test assets and machine-specific settings are excluded from this repository.
