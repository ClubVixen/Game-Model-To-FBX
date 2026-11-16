# From FBX to a Deadlock mod

[Back to README](../README.md)

This is the next pipeline stage, not part of FBX extraction. Use the [Deadlock hero-swap repository](https://github.com/ClubVixen/deadlock-hero-swap-pipeline) for the Blender add-on and full build setup.

Import the resulting FBX, identify the character armature, and import the target hero skeleton. Keep **Preserve Proportions** enabled. Review every auto-detected bone before fitting; controller bones are not substitutes for weighted wrist/ankle bones.

For the tested KKBP naming convention, map `Left/Right shoulder`, `arm`, `elbow`, `wrist`, `leg`, `knee`, `ankle`, and `toe` to their corresponding hero roles. Use Hips for the pelvis and Spine → Chest → Upper Chest for the torso. Finger names are Thumb0–2 and Index/Middle/Ring/LittleFinger1–3 with `_L`/`_R` suffixes. Do not choose FootPin, MasterFootIK, or cf_pv_hand controllers.

Fit, inspect hands/feet/outfit, then configure secondary motion on weighted hair/skirt/body chains. Keep the root/attachment bones fixed. An imported physics bone does not automatically become a working Deadlock jiggle bone.

KKBP can bake padded, non-power-of-two images (for example 516×516 eyes). Source 2's alpha-weighted mip generation can reject them. Resize those baked textures to a suitable power of two, such as 512×512, in the editable scene before exporting the Deadlock build.

Export DMX, build the VPK with direct installation disabled, then import the VPK through **Deadlock Mod Manager → Add mods → Add Local Mod**. The manager handles toggling. FBX and DMX are intermediate files; neither is a substitute for a compiled VPK.
