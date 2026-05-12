Translate package (library)
===========================

Purpose
-------
This package contains programmatic code for running translation models (IndicTrans runner and related utilities).
It is structured as a Python package (contains `__init__.py`) and is intended to be imported by higher-level scripts or other modules.

Files
-----
- `indictrans_runner.py` — model runner / wrapper for IndicTrans-style translation model; designed for programmatic use.
- `__init__.py` — package initializer.

Recommended usage
-----------------
- Import `translate.indictrans_runner` from scripts or higher-level modules when you need model-level access.
- Keep library-level helper functions and model wrappers here. Avoid placing CLI-only scripts in this folder.

Next steps / Suggestions
------------------------
- Add unit tests for the runner under `code/src/tests/` if there are model-specific functions.
- If `indictrans_runner.py` is purely a CLI script, consider moving it to `code/src/translation/` and keeping only reusable helper functions here.
- Maintain a stable small public API in `__init__.py` (e.g., export Runner class/function) so scripts can import it cleanly.
