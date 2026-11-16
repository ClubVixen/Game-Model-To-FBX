# For LLMs: character-to-FBX task entry point

Use this folder when a user asks: **“Extract this character from this game as an FBX.”** Read the current source and relevant game guide before acting; these notes are context, not authorization to change unrelated files or install mods.

## Work sequence

1. Identify the game, input file/folder, desired character/outfit/components, installed dependencies, and output directory. Inspect connected/local files before asking for paths already available.
2. Read the matching [game guide](../README.md#choose-your-game). Distinguish portable Rivals from source-only multi-game execution.
3. Check configured executable paths and input companions. Use a local JSON copied from `multigame.example.json`; never commit personal paths, game files, cards, zipmods, keys, generated meshes, or vendor assemblies.
4. Run inspection before conversion. For Koikatsu PNGs, inspect dependencies and assemble in Maker or Studio first. For ZZZ, resolve every weighted palette index against the correct rig and select active draw ranges.
5. Convert into a new job directory. Preserve input files, user Blender scenes, and installed mods. FBX extraction does not require installing/disabling any Deadlock mod.
6. Read the job report; inspect the actual FBX in Blender for textures, accessories, normals, skinning and proportions. A structural check is not evidence of game-render parity or physics behavior.
7. Return exact output paths, the editable textures/scene, and concrete limitations. Do not label untested in-game behavior verified.

## CLI examples

Run from the repository root after installing requirements and configuring external tools:

```powershell
python converter.py "C:/Inputs/RivalsMod" --output "C:/Exports/Rivals" --game "C:/Games/Marvel/Content/Paks" --blender "C:/Tools/Blender/blender.exe" --mappings "C:/Mappings/Marvel.usmap"
python multigame.py inspect deadlock "C:/Inputs/character_dir.vpk" --config multigame.local.json --output "C:/Exports"
python multigame.py convert deadlock "C:/Inputs/character_dir.vpk" --config multigame.local.json --output "C:/Exports"
python multigame.py convert zzz "C:/Inputs/ZZZMod" --config multigame.local.json --output "C:/Exports"
python multigame.py convert-card koikatsu "C:/Inputs/card.png" --config multigame.local.json --output "C:/Exports"
python multigame.py convert koikatsu "C:/Inputs/StudioExport/character.studio.json" --config multigame.local.json --output "C:/Exports"
```

These are placeholder paths. Read `--help` in the checked-out revision before scripting. Card compatibility conversion produces another card, not FBX; PNG-to-FBX requires a matching prepared assembly.

## Code map

| File / folder | Responsibility |
|---|---|
| `converter.py` | Rivals GUI/CLI, staging and batch orchestration |
| `materials.py`, `hair_bake.py` | Rivals material resolution and UV hair baking |
| `blender_convert.py` | Rivals Blender export worker |
| `backend-source/` | Pinned CUE4Parse backend sources/build instructions |
| `multigame_gui.py`, `multigame.py` | Multi-game UI, inspect/convert dispatch and external tool calls |
| `multigame_blender.py` | Blender assembly, FBX output and structural checks |
| `zzz_mod_prep.py` | INI/buffer preparation, components and draw ranges |
| `card_reader.py`, `koikatsu_card.py` | Card envelopes, compatibility conversion and zipmod dependency reports |
| `koikatsu_prepare.py` | Maker/KKBP preparation and baking |
| `studio-exporter/`, `studio_import.py` | Studio capture bridge and Blender assembly |
| `test_*.py` | Focused source tests; inspect individual requirements before running |

## Important distinctions

- ZZZ part indices are palette-local. A matching character name is not a sufficient bone map.
- Studio captures the current pose as rest pose. Ask for or prepare a neutral pose for retargeting; do not silently replace a user's scene.
- Koikatsu `cf_s_bust*` and `cf_s_bnip*` helpers may be independently parented to the spine after import. Inspect all weighted descendants when preparing secondary motion; never infer a complete chain from bone names alone.
- Angle-dependent missing surfaces can be reversed face winding, not alpha. A signed volume is not a reliable outward-direction test for every open surface. Inspect individual parts; broad normal recalculation or forced opacity can break previously correct regions.
- Preserve RGB and alpha independently when editing textures. Keep intentional cutouts for eyebrows, eyeliner and clothing.
- Destination mod creation is separate: FBX → fitted rig/materials → DMX → compiled VPK. Keep extraction instructions separate from that build workflow.

[Historical validation and implementation reference](historical-validation.md) contains older sample results and the former detailed Rivals README. Treat it as evidence with limited scope, not a current task checklist. No proprietary sample assets are required in this folder.
