# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate environment (required before any command)
source venv/bin/activate

# Scan and classify all PDFs (builds pdf_inventory.csv)
python pop_cli.py inventory --scan

# Process PDFs by phase
python pop_cli.py process --phase 1 --count 5       # 5 English PDFs
python pop_cli.py batch --phase 2 --all              # All Indic PDFs
python pop_cli.py process-file path/to/file.pdf      # Any single PDF directly

# Inspect state
python pop_cli.py status --summary
python pop_cli.py list --phase 1 --limit 10

# Configuration
python pop_cli.py config --show
python pop_cli.py config --create-default            # Write config/pop_cli.yaml
python pop_cli.py config --set processing.max_parallel_processes 2

# Logs
tail -f logs/pop_cli.log
```

There is no test suite wired into a test runner. The project docs reference `python test_cli_system.py` but no such file exists on this branch.

Install dependencies:
```bash
./venv/bin/pip install -r requirements_cli.txt
```

## Architecture

### Data flow

```
data/raw/POP Bank/          (565 PDFs, not in git)
        │
        ▼ inventory --scan
pdf_inventory.csv           (master index, 15 columns)
        │
        ├─► Phase 1: lang_guess=en, digital_guess=True → artifacts/phase1_english/
        └─► Phase 2: lang_guess=indic, digital_guess=True → artifacts/phase2_indic/
```

Each processed document gets its own directory named by the first 12 chars of its MD5 hash, containing `doc.json`, `doc.md`, and an `images/` subfolder.

### Module layout

| Layer | Path | Role |
|---|---|---|
| CLI entry point | `pop_cli.py` | Parses args, routes to command classes |
| Command classes | `pop_cli_commands/commands/` | One file per subcommand; each extends `BaseCommand` |
| Config | `pop_cli_commands/core/config.py` | `load_config()` deep-merges `config/pop_cli.yaml` into `DEFAULT_CONFIG`; supports dot-notation access |
| Processing wrappers | `pop_cli_commands/utils/processors.py` | `process_with_docling` (Phase 1), `process_with_phase2` (Phase 2), `process_with_phase6` (garbled, falls back to Phase 2) |
| Classification | `code/src/classify/english_vs_indic.py` | FastText `lid.176.bin` (root-level) votes per page; returns `lang_guess, lang_conf, garbled_detected` |
| Inventory | `code/src/ingest/inventory.py` | Scans `data/raw/POP Bank/`, extracts metadata, calls classify, writes `pdf_inventory.csv` |
| Extraction | `code/src/extract/` | `docling_runner.py` (Phase 1 structure), `direct_doc_generator.py` (Phase 2 OCR+VLM), `ocr_runner.py` (EasyOCR) |
| Structure | `code/src/structure/` | `md_to_json_converter_ultra.py` converts Markdown → typed JSON; `stitcher.py` replaces garbled text with OCR results |
| Translation | `code/src/translate/indictrans_runner.py` | `deep_translator` (Google Translate) for Indic → English |
| Phase pipelines | `code/src/pipeline/` | `run_phase2.py`, `phase6_improved_v2_json.py` — orchestrate multi-step runs |

`pop_cli.py` inserts both the project root and `code/src/` into `sys.path`, so source modules import without package prefixes (e.g. `from extract.docling_runner import run_docling`).

### Configuration

`config/pop_cli.yaml` is the primary config file. It is deep-merged on top of the hardcoded `DEFAULT_CONFIG` in `pop_cli_commands/core/config.py`. Use dot-notation keys (`paths.inventory_csv`, `phase1.criteria.lang_conf_min`, etc.) everywhere the `Config.get()` API is used.

### DPT-2 processing (temporary workflow)

`dpt2_processing/` contains scripts to send remaining PDFs to Landing AI's DPT-2 API as a stopgap. It is not part of the main open-source pipeline. Requires `DPT2_API_KEY` env var. Outputs land in `dpt2_processing/processed_data/`.

### Key data files (not in git)

- `data/raw/POP Bank/` — source PDFs organized by state (~1–2 GB)
- `lid.176.bin` — FastText language model (126 MB, root-level)
- `artifacts/` — all generated JSON/Markdown outputs
- `venv/` — Python 3.12 virtual environment (~13 GB)
