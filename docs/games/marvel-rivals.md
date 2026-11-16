# Marvel Rivals to FBX

[Back to the game selector](../../README.md)

## What you need

- The complete portable release, or a source-built backend ([build instructions](../building.md)).
- Blender installed separately; the portable workflow was developed with Blender 4.2.
- Your installed game's `Content/Paks` folder, including its `global.utoc` and `global.ucas`.
- A compatible `.usmap` mapping. The release includes a mapping; after a game update you may need a matching replacement.
- Unpacked mod files. Keep companion `.utoc`, `.ucas`, and `.pak` files together.

## Convert

1. Run `GameModelsToFBX.exe` (or `python app.py`) and choose **rivals**.
2. Click **Create / Edit configuration**. Set `blender` to Blender's executable and `game` to the installed game's `Content/Paks` directory. Leave `mappings` empty to use the bundled mapping, or provide a matching `.usmap` path. Save the JSON.
3. Use **Add files** for a `.utoc` package, or **Add mod folder** to search recursively. Keep `.pak`/`.ucas` companions together and add each package only once. Unpack ZIP/7z downloads first.
4. Choose an output folder, click **Inspect / Read Mods**, then **Convert Batch to FBX**.
5. Open the new job folder, then `FBX/`. Import the desired gameplay or lobby FBX into Blender. A failed package does not stop other queued packages.

## Textures and limitations

Textures are embedded in the FBX; separate PNGs and original material parameters are retained under `extracted/`. The installed game supplies dependencies missing from the mod. Each mod is staged separately, and source archives are not modified.

Hair color baking uses the source UV sets and inherited material tints. The original first UV channel is retained as `Original_UV0` when an atlas is needed. FBX cannot reproduce Unreal shader graphs, original control rigs, runtime physics, or all effects. See [troubleshooting](../troubleshooting.md) for missing dependencies.
