Translation scripts and utilities
================================

Purpose
-------
This folder contains high-level translation scripts, CLI utilities, and pipeline helpers. These are intended to be run as scripts (entry points) and orchestrate translation of extracted documents, cleanup, and organization.

Files
-----
- `copy_indic_translated.py` — copy final translated JSONs to a user-facing directory
- `fix_translated_tables.py` — cleanup utility to fix table pipe artifacts introduced by translation
- `organize_translated_files.py` — relocate translated files into state folders and rename them
- `translate_phase2_artifacts.py` — (older) attempt / runner for translation; may be deprecated
- `translate_phase2_googletrans.py` — current Google Translate-based translation pipeline

Recommended usage
-----------------
- Run these scripts from the project root or via `python -m` if you convert them into package entry points.
- Keep scripts here and let them import `translate` (the library) or `utils` as needed.

Next steps / Suggestions
------------------------
- If several scripts share functionality, move shared helpers into `code/src/translate/` or `code/src/utils/` and keep scripts thin.
- Consider adding a small `cli.py` or `__main__` wrapper so scripts can be invoked as `python -m code.src.translation.translate_phase2_googletrans`.
- Add usage examples to this README for most common operations.
