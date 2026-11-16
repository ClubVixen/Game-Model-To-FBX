# Troubleshooting

[Back to README](../README.md)

| Problem | What to check |
|---|---|
| `WinError 2` / executable not found | Verify the full paths to Blender and the selected game's extraction tool. For Deadlock, `vrf` must name `Source2Viewer-CLI.exe`, not its folder or GUI application. |
| Rivals package cannot be read | Keep companion archives together; supply installed-game global metadata and a mapping compatible with the package's game version. |
| Deadlock input has no meshes | A texture-only VPK cannot produce character geometry. Select a model-containing package. |
| ZZZ missing bone indices or bad buffer bounds | Use the exact matching reference dump, per-part bone map, and active component/draw selection. Do not guess unmapped bone names. |
| Koikatsu hair, hat, or accessories missing | Load the character in the game with the required zipmods and correct outfit slot before exporting. The card preview alone is not the assembled model. |
| Sunshine card missing from Maker | Convert a copy with **Sunshine to KK card** and restart/reload as appropriate. Compatibility is not guaranteed for every plugin set. If it loads correctly in CharaStudio, use the Studio route. |
| Transparent, flat, or wrong-colored materials | Inspect the image alpha, material masks and front/back face direction separately. FBX cannot reproduce all game shaders. Do not force every material opaque: that exposes black pixels around cutout clothing, eyebrows and hair. |
| Clothing or tip bones do not follow physics after retargeting | Inspect the actual weighted bone hierarchy. Imported secondary bones may be siblings of the spine; they do not automatically inherit a breast/hair spring. Configure this in the destination pipeline. |
| Output loses textures when moved | Keep multi-game FBX, Blender scene, and external `textures/` together. Use `00_materials.json` for Koikatsu texture assignments. |

Read the failing job's logs and `report.json`. Preserve original inputs and retry into a new output directory after correcting configuration.
