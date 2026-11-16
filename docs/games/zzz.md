# Zenless Zone Zero buffer mods to FBX

[Back to the game selector](../../README.md) · [Shared installation](../../README.md#install-and-start)

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


## Convert step by step

1. Install XXMITools in the configured Blender, then prepare the reference dump and base FBX for the exact character/version.
2. Set `blender`, `reference`, `base_fbx`, `bone_map`, and `material_map` in your local JSON. Check each part's palette rather than reusing another character's mapping.
3. Launch `GameModelsToFBX.exe` (or `python app.py`), choose **zzz**, and select your JSON and output folder.
4. Use **Add mod folder** for the INI and its buffers. Click **Inspect / Read Mods**.
5. Select the intended components and toggle draw ranges in the JSON as described below.
6. Click **Convert Batch to FBX**. Inspect the exported parts and their deformation in Blender; a component-only export does not create a missing body or face.

## Components and toggles


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
