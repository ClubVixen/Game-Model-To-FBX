# Deadlock VPK to FBX

[Back to the game selector](../../README.md) · [Shared installation](../../README.md#install-and-start)

Install [Source 2 Viewer / ValveResourceFormat](https://github.com/ValveResourceFormat/ValveResourceFormat/releases) and Blender separately. Set:

| Configuration | Value |
|---|---|
| `blender` | Full path to Blender executable; tested with 5.2 |
| `vrf` | Full path to `Source2Viewer-CLI.exe`; tested with 20.1 |
| `gameinfo` | Your installed `Deadlock/game/citadel/gameinfo.gi` |
| `model` | Optional exact internal `.vmdl_c` path from Inspect; otherwise converts every model |

Add the mod's VPK file. The installed game resolves dependencies that the mod does not include. A texture-only mod has no character geometry to export and will be rejected.

The extraction enables skeleton export but requests no animation clips. The intermediate GLB is then converted to FBX. This route does not preserve Source 2 shaders, runtime animation constraints, or jiggle simulation. Those need to be configured again in the destination pipeline. It does not install or disable mods.

## Convert step by step

1. Configure the paths above in your local JSON.
2. Launch `python app.py`, choose **deadlock**, and select that JSON and an output folder.
3. Use **Add files** to add the mod VPK. Keep any companion VPK archive chunks beside it.
4. Click **Inspect / Read Mods**. If you only want one model, copy its internal path into `model` in the JSON.
5. Click **Convert Batch to FBX** and open the timestamped output folder.
6. Import the FBX in Blender with its textures available. To build a replacement mod afterward, use the [hero-swap handoff](../deadlock-handoff.md).
