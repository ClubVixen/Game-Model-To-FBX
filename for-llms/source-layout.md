# Source layout audit

Tests live in `tests/`; run `python -m unittest discover -s tests` from the repository root.

All remaining root Python modules are used. `app.py` launches the GUI and workers; `multigame_gui.py` and `multigame.py` provide the shared interface and dispatcher. `converter.py`, `materials.py`, and `hair_bake.py` implement Rivals conversion. `card_reader.py` and `koikatsu_card.py` read and convert cards. `zzz_mod_prep.py` reads buffer mods. `blender_convert.py`, `multigame_blender.py`, `koikatsu_prepare.py`, and `studio_import.py` are Blender workers or their imports. `build_local.py` is the local packaging entry point.

Blender worker scripts remain at the root because subprocesses resolve them beside the executable. They are not unused merely because the main GUI does not import them directly. No conversion modules were deleted.
