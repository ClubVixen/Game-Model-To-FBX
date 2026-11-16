# Marvel Rivals to FBX

[Back to the game selector](../../README.md)

## What you need

- The complete portable release, or a source-built backend ([build instructions](../building.md)).
- Blender installed separately; the portable workflow was developed with Blender 4.2.
- Your installed game's `Content/Paks` folder, including its `global.utoc` and `global.ucas`.
- A compatible `.usmap` mapping. The release includes a mapping; after a game update you may need a matching replacement.
- Unpacked mod files. Keep companion `.utoc`, `.ucas`, and `.pak` files together.

## Convert

1. Run `RivalsFbxConverter.exe` (or `python converter.py` from a configured source checkout).
2. Select your Blender executable, installed game `Content/Paks` directory, and mapping file.
3. Click **Add files** for package files, or add a folder recursively. Unpack ZIP/7z downloads first. A matching `.utoc`/`.ucas` pair is one conversion job.
4. Choose an output folder and click **Convert batch**.
5. Open the new job folder, then `FBX/`. Import the desired gameplay or lobby FBX into Blender. A failed job does not stop other queued inputs.

## Textures and limitations

Textures are embedded in the FBX; separate PNGs and original material parameters are retained under `extracted/`. The installed game supplies dependencies missing from the mod. Each mod is staged separately, and source archives are not modified.

Hair color baking uses the source UV sets and inherited material tints. The original first UV channel is retained as `Original_UV0` when an atlas is needed. FBX cannot reproduce Unreal shader graphs, original control rigs, runtime physics, or all effects. See [troubleshooting](../troubleshooting.md) for missing dependencies.
