# Mod to FBX setup

Convert locally owned character assets into rigged FBX for the Deadlock hero-swap pipeline. The new batch GUI is launched separately from the existing Marvel Rivals converter:

```powershell
python -m pip install -r requirements.txt
python multigame_gui.py
```

Copy `multigame.example.json` to a local configuration file. Use absolute paths, select that file in **Configuration JSON**, choose the source game and output directory, and add inputs. **Inspect / Read Mods** inventories inputs. **Convert Batch to FBX** creates a timestamped directory per input, with logs, editable Blender files, FBX, and `report.json`. Failed inputs do not stop the rest of a batch.

The existing portable Marvel Rivals release does not yet contain this new front end. Run this source checkout with Python 3.10+.

## Deadlock VPK

Install [Source 2 Viewer / ValveResourceFormat](https://github.com/ValveResourceFormat/ValveResourceFormat/releases) and Blender separately. Set:

| Configuration | Value |
|---|---|
| `blender` | Full path to Blender executable; tested with 5.2 |
| `vrf` | Full path to `Source2Viewer-CLI.exe`; tested with 20.1 |
| `gameinfo` | Your installed `Deadlock/game/citadel/gameinfo.gi` |
| `model` | Optional exact internal `.vmdl_c` path from Inspect; otherwise converts every model |

Add the mod's VPK file. The installed game resolves dependencies that the mod does not include. A texture-only mod has no character geometry to export and will be rejected.

The extraction enables skeleton export but requests no animation clips. The intermediate GLB is then converted to FBX. This route does not preserve Source 2 shaders, runtime animation constraints, or jiggle simulation. Those need to be configured again in the destination pipeline. It does not install or disable mods.

## Zenless Zone Zero buffer mods

The bundled `zzz_mod_prep.py` reader comes from the existing ZZZ mod preparation project. It reads `.ini` resource declarations and interleaves Position/Blend/Texcoord buffers into `.vb0/.ib/.fmt` for XXMITools. Use **Add mod folder** to select a folder containing the mod's INI and buffers.

Install [XXMITools](https://github.com/leotorrez/XXMITools/releases) into the Blender version configured above. Supply a matching original dump from [ZZ-Model-Importer-Assets](https://github.com/leotorrez/ZZ-Model-Importer-Assets) and the same character's extracted base FBX rig. A buffer mod contains numeric skin indices, not a complete named skeleton.

Set `reference` to the matching dump folder, `base_fbx` to its base rig, `bone_map` to an explicit JSON mapping, and `material_map` to diffuse texture paths. An optional `zzz_reader` overrides the bundled reader.

Example bone map (names must actually exist on your base rig):

```json
{
  "ExampleBodyA": {"0": "Bip001 Pelvis", "1": "Bip001 Spine"},
  "ExampleHairA": {"0": "Bip001 Head", "1": "Hair_01"}
}
```

Use the prepared part's filename stem as the key. `"*"` is a fallback only when all parts genuinely share the same palette. Never assume index 0 means the same bone in every part. Every numeric vertex group must resolve to a real bone or conversion fails.

`material_map` similarly maps part stems to PNG/DDS diffuse images. Shader masks, toggles, component-specific UV conventions, and physics require inspection. Matching a base character's name alone is insufficient. A reference-format or palette mismatch can produce a valid-looking file with incorrect deformation.

The raw-buffer route has now passed a selected-component test with Sixth Streetwear Belle (original hair + headband). This is not a complete-character validation. The Belle/Pheony Deadlock skins above originate from already extracted FBXs and remain separate samples.

## Koikatsu Party cards

Two paths are supported: the existing **Character Maker + KKBP** path below, and the separate [CharaStudio bridge](KOIKATSU_STUDIO.md). Keep both plugins installed. Studio exports the selected character directly, including its loaded accessories, without requiring the card to appear in Maker.

### Sunshine cards and accessory dependencies

Choose **koikatsu**, add card PNGs and click **Sunshine to KK card**. This implements the two Parameter version changes described by [astralash's converter](https://github.com/astralash/ConvertKKS-CC-to-KK-CC), using kkloader. It writes a new `_KK.png` in a timestamped folder, preserves the preview and non-Parameter blocks, and never overwrites the original. Unknown versions are rejected. File compatibility checks do not guarantee acceptance by every game/plugin: the Applejack sample loads in Studio but still does not appear in the Maker browser.

Set `koikatsu_mods` to the game's `mods` folder and `koikatsu_outfit` to the zero-based outfit slot. **Inspect / Read Mods** reports the card's Sideloader GUIDs and installed zipmods, including hair stored as an accessory. Conversion writes `card-report.json`. Missing GUIDs and unreadable archives are reported. The game must assemble those assets before export; the reader does not install mods or reconstruct arbitrary Unity bundles itself. GUID presence alone does not prove item/version compatibility.

### Character Maker export

A card PNG contains a preview plus appended parameter/plugin data. It does **not** contain all the meshes and textures. The card reader checks that payload and reports its SHA256 and plugin identifiers without executing it. All four supplied example cards passed envelope inspection.

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

## Feeding the Deadlock hero-swap pipeline

Import the resulting FBX, identify the character armature, and import the target hero skeleton. Keep **Preserve Proportions** enabled. Review every auto-detected bone before fitting; controller bones are not substitutes for weighted wrist/ankle bones.

For the tested KKBP naming convention, map `Left/Right shoulder`, `arm`, `elbow`, `wrist`, `leg`, `knee`, `ankle`, and `toe` to their corresponding hero roles. Use Hips for the pelvis and Spine → Chest → Upper Chest for the torso. Finger names are Thumb0–2 and Index/Middle/Ring/LittleFinger1–3 with `_L`/`_R` suffixes. Do not choose FootPin, MasterFootIK, or cf_pv_hand controllers.

Fit, inspect hands/feet/outfit, then configure secondary motion on weighted hair/skirt/body chains. Keep the root/attachment bones fixed. An imported physics bone does not automatically become a working Deadlock jiggle bone.

KKBP can bake padded, non-power-of-two images (for example 516×516 eyes). Source 2's alpha-weighted mip generation can reject them. Resize those baked textures to a suitable power of two, such as 512×512, in the editable scene before exporting the Deadlock build.

Export DMX, build the VPK with direct installation disabled, then import the VPK through **Deadlock Mod Manager → Add mods → Add Local Mod**. The manager handles toggling. FBX and DMX are intermediate files; neither is a substitute for a compiled VPK.

## Validation scope

Each successful FBX conversion compares vertex count, bone count, vertices with positive weights on actual bones, and bound mesh count after reimport. Helper vertex groups are not counted as skinning. This checks structural preservation, not gameplay, shader parity, or animation contact quality.

Recorded local tests:

| Input | Result |
|---|---|
| Queen Geist VPK | 273,498 vertices / 899 bones / 2 bound meshes preserved |
| St. Louis KKBP prepared scene | 60,709 vertices / 904 bones / 4 bound meshes; 60,377 bone-weighted vertices preserved |
| Celestia KKBP PMX → automatic bake → FBX | 34,206 vertices / 804 bones / 3 bound meshes preserved; 29 materials baked. Installed-game appearance differs from card preview |
| Four example Koikatsu PNGs | Appended card payloads inspected successfully |
| ZZZ Sixth Streetwear Belle, selected hair draw ranges | 3,534 vertices / 292 bones / 1 bound mesh preserved; all vertices weighted. Neutral render inspected; all 3,534 vertices respond to a 25-degree head rotation. Full outfit blocked by incomplete bone mapping |

Generated models, game files, cards, personal configuration and vendor binaries are excluded from this source repository. Treat a successful file conversion and an in-game-tested mod as separate milestones.

### Deadlock sample skins (2026-11-14)

Built and imported through Deadlock Mod Manager 2.2.0:

| Skin | Target | Runtime observation |
|---|---|---|
| StLouis_Lash | Lash | Textured model loaded and followed the hideout idle animation; naval accessories retained |
| Belle_McGinnis | McGinnis | Textured model loaded and animated; wrist/weapon contact needs further tuning |
| Pheony_Apollo | Apollo | Textured model loaded and animated; long hair has substantial secondary motion and needs further tuning |

These are initial playable test builds, not full combat-validation passes. Movement, firing, reloads, abilities and physics extremes still need dedicated testing. Hideout screenshots were saved locally; they are not proof of those remaining checks.

After the tests, the existing Buck McGinnis and Lashlyn skins were restored as active. Belle and St. Louis remain available as disabled alternatives in the library. Apollo remains enabled. To switch alternatives, enable the desired skin and choose **Swap mods**, then restart Deadlock; do not enable two replacements for the same hero together.


### ZZZ component and toggle selection

The reader enumerates resources; it does not execute a mod INI or automatically resolve every conditional draw. A toggle mod can contain several mutually exclusive hairstyles in the same vertex/index buffers. Select the actual draw ranges for one configuration, using `drawindexed = count, first_index, base_vertex` from its INI:

```json
{
  "components": ["BelleHairA"],
  "draw_ranges": {
    "BelleHairA": [[6282, 0, 0], [930, 6282, 0], [7059, 7212, 0]]
  },
  "zzz_axis_forward": "Y",
  "zzz_axis_up": "Z"
}
```

This specific example selects Sixth Streetwear Belle's shared hair, headband and original hairstyle. These numbers are sample-specific, not universal defaults. Without draw ranges all triangles in a selected buffer are imported. Only vertices referenced by the selected triangles are retained. A component-only export does not add missing face/body meshes from the base FBX.

Both a simple per-part dictionary and the existing Rig Transfer `parts -> part -> map` JSON schema are supported. Many-to-one mappings combine weights rather than creating nonbinding `.001` groups. Missing weighted indices fail explicitly; uncertain saved mappings still need deformation inspection. The base FBX's current pose becomes the binding rest pose, and parenting preserves mesh world transforms. Verify that the supplied base pose matches the raw model before accepting a new character.

The real sample exposed an inactive BodyB resource referencing indices 27,669-27,682 despite a 27,669-vertex buffer, and BodyA uses weighted index 71 absent from its saved map. The converter rejects these cases rather than inventing a bone assignment. Choose only active components and repair the body map against the matching source skeleton before exporting a full character. Reference element bounds, triangle counts, draw ranges and index bounds are checked before Blender import.

A neutral Blender render of the selected hairstyle was inspected and saved alongside the local FBX.

The image shows only the selected component. Original ZZZ shader rendering, full-character deformation and in-game behavior are not established by this test.
