# Koikatsu Party to FBX

[Back to the game selector](../../README.md) · [Shared installation](../../README.md#install-and-start)

Start by choosing **Maker + KKBP** for its material-baking workflow or **[CharaStudio](koikatsu-studio.md)** to export a character already loaded in Studio with visible accessories. Both routes remain supported.

Two paths are supported: the existing **Character Maker + KKBP** path below, and the separate [CharaStudio bridge](koikatsu-studio.md). Keep both plugins installed. Studio exports the selected character directly, including its loaded accessories, without requiring the card to appear in Maker.

### Sunshine cards and accessory dependencies

Choose **koikatsu**, add card PNGs and click **Sunshine to KK card**. This implements the two Parameter version changes described by [astralash's converter](https://github.com/astralash/ConvertKKS-CC-to-KK-CC), using kkloader. It writes a new `_KK.png` in a timestamped folder, preserves the preview and non-Parameter blocks, and never overwrites the original. Unknown versions are rejected. File compatibility checks do not guarantee acceptance by every game/plugin: the Applejack sample loads in Studio but still does not appear in the Maker browser.

Set `koikatsu_mods` to the game's `mods` folder and `koikatsu_outfit` to the zero-based outfit slot. **Inspect / Read Mods** reports the card's Sideloader GUIDs and installed zipmods, including hair stored as an accessory. Conversion writes `card-report.json`. Missing GUIDs and unreadable archives are reported. The game must assemble those assets before export; the reader does not install mods or reconstruct arbitrary Unity bundles itself. GUID presence alone does not prove item/version compatibility.

### Character Maker export

A card PNG contains a preview plus appended parameter/plugin data. It does **not** contain all the meshes and textures. The card reader checks that payload and reports its SHA256 and plugin identifiers without executing it.

1. Use an existing Koikatsu Party installation with BepInEx, KKAPI, Sideloader, and the card's required zipmods. Put cards in `UserData/chara/female` or a subfolder.
2. Install the **Koikatsu net3.5** build of KKBP Exporter 4.30 in `BepInEx/plugins`. The Sunshine/net4.6 build is not interchangeable. Restart the game and confirm the exporter loaded.
3. In Character Maker, load the card and inspect the selected outfit. The preview may show a different outfit slot. If faces, hair, or accessories differ from the card preview, resolve missing assets before accepting a conversion.
4. In **Export Model for KKBP → Show Options**, enable **Export Single Outfit**. Disable variations, hit meshes, pushups, and Keep Current Pose for a neutral rig export. Keep physics export enabled. Export; the game creates `Export_PMX/<timestamp_character>/model.pmx` plus outfit/textures/JSON. Keep the whole folder together.
5. Use a **separate Blender 3.6 installation** with KKBP 6.6.3 and mmd_tools 2.9.2. A compatible importer/exporter bundle is available from [the Blender 3.6 KKBP fork](https://github.com/spawner1145/KK-Blender-Porter-Pack-3-6); mmd_tools is available from [its releases](https://github.com/UuuNyaa/blender_mmd_tools/releases/tag/v2.9.2). These third-party packages are not included here.
6. Set `kkbp_blender` to that Blender 3.6 executable. If using unpacked addons, set `kkbp_addons` to the directory containing importable `kkbp` and `mmd_tools` folders. Add the **top-level** exported `model.pmx` to this converter, choose **koikatsu**, and convert.

The PMX bridge opens a disposable graphics-enabled Blender window because KKBP's LUT conversion requires a GPU context. It imports, saves an assembled scene, bakes light-color textures, makes simple Principled materials, hides gag-eye/tear alternatives, and saves `kkbp/prepared.blend`. The main Blender worker then exports/reimports FBX. Recovery files are isolated in the job directory.

You can also prepare and bake the model manually, then convert the `.blend` directly. Hidden collections and hidden objects are excluded; visible mesh/armature objects are exported. Outline geometry modifiers are not applied during FBX export. Review the source shape keys and selected outfit before conversion.

To batch card PNGs after manual assembly, map each card's reported SHA256 to its own prepared file:

```json
{"assemblies": {"CARD_SHA256_FROM_INSPECT": "C:/Models/MyCharacter/prepared.blend"}}
```

This prevents accidentally exporting the same assembled character for every card in a batch. Custom KKBP shaders and simulation do not transfer directly into FBX; baked textures and bone weights do.

### Editable textures and accessory checks

Both paths write separate PNGs under `textures/<FBX filename>/` beside the FBX and Blender scene. `00_materials.json` maps object/material/image names to these files. Edit the PNGs, reload images in Blender and re-export. Keep the FBX, `.blend` and textures together: this multi-game path uses relative external textures, not embedded-only images. Original game files are untouched.

Optional configuration arrays `required_mesh_names` and `required_material_names` contain case-insensitive substrings that must appear in the export inventory. Obtain these names from a known-good model, not guessed zipmod filenames. Missing requirements fail conversion explicitly.
