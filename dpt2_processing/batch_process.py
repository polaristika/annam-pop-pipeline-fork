"""
dpt2_processing/batch_process.py  –  Step 1: DPT-2 PDF → JSON/MD

Reads garbled_pdfs.csv (or unprocessed_pdfs.csv with --all),
calls the Landing AI DPT-2 API for each PDF, translates to English,
and writes outputs to processed_data/<state>/<pdf_name>/.

This is a thin wrapper that re-exports the logic from the original
dpt2_batch_process.py so the unified CLI can call it cleanly.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── allow running as a script from anywhere ───────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config.settings import (
    DEFAULT_GARBLED_CSV,
    DEFAULT_UNPROCESSED_CSV,
    PROCESSED_ROOT,
    LOG_DIR,
)

# The original file contains all the heavy logic; import it.
# Place the original dpt2_batch_process.py at REPO_ROOT/dpt2_processing/
# and this wrapper will delegate to it.

def run(args) -> int:
    """
    Entry-point called by the unified CLI (pop_pipeline.py).

    args attributes consumed:
      all, input_csv, limit, force, timeout, verbose,
      pdf_root, output_root, log_path, overwrite_log,
      strict_paths, missing_as_failure,
      lang_filter, lang_priority, skip,
      master_xlsx, link_map_xlsx
    """
    # Resolve CSV
    if args.input_csv:
        csv_path = Path(args.input_csv)
    else:
        csv_path = DEFAULT_UNPROCESSED_CSV if args.all else DEFAULT_GARBLED_CSV

    if not csv_path.exists():
        fallback = DEFAULT_UNPROCESSED_CSV if csv_path == DEFAULT_GARBLED_CSV else DEFAULT_GARBLED_CSV
        if fallback.exists():
            print(f"[warn] CSV not found: {csv_path} – falling back to {fallback}")
            csv_path = fallback
        else:
            print(f"[error] Input CSV not found: {csv_path}")
            return 1

    log_path    = Path(args.log_path)   if args.log_path    else LOG_DIR / "step1_dpt2.log"
    output_root = Path(args.output_root) if args.output_root else PROCESSED_ROOT
    pdf_root    = Path(args.pdf_root).resolve() if args.pdf_root else None
    master_xlsx = Path(args.master_xlsx).resolve() if args.master_xlsx else None
    link_map_xlsx = Path(args.link_map_xlsx).resolve() if args.link_map_xlsx else None

    lang_filters  = [p.strip() for p in (args.lang_filter or "").split(",")  if p.strip()]
    lang_priority = [p.strip() for p in (args.lang_priority or "unsure,indic").split(",") if p.strip()]

    # ── Lazy import so machines without GPU/API deps can still use other steps
    try:
        from dpt2_processing.core import process_batch, setup_logging
    except ImportError:
        # Fall back to the original monolith if core hasn't been extracted yet
        import importlib.util, types
        spec = importlib.util.spec_from_file_location(
            "dpt2_orig",
            REPO_ROOT / "dpt2_processing" / "dpt2_batch_process.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        process_batch = mod.process_batch
        setup_logging  = mod.setup_logging

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(
        verbose=args.verbose,
        log_path=log_path,
        overwrite_log=getattr(args, "overwrite_log", False),
    )

    return process_batch(
        csv_path=csv_path,
        limit=args.limit,
        force=args.force,
        timeout=args.timeout,
        logger=logger,
        output_root=output_root,
        pdf_root=pdf_root,
        strict_paths=getattr(args, "strict_paths", False),
        missing_as_failure=getattr(args, "missing_as_failure", False),
        lang_filters=lang_filters,
        lang_priority=lang_priority,
        skip=getattr(args, "skip", 0),
        master_xlsx=master_xlsx,
        link_map_xlsx=link_map_xlsx,
    )


def add_args(sub):
    """Register step-1 arguments onto an argparse sub-parser."""
    sub.add_argument("--all",          action="store_true",
                     help="Use unprocessed_pdfs.csv instead of garbled_pdfs.csv")
    sub.add_argument("--input-csv",    default=None,
                     help="Override input CSV path")
    sub.add_argument("--limit",        type=int, default=None,
                     help="Process only first N rows")
    sub.add_argument("--force",        action="store_true",
                     help="Overwrite already-processed outputs")
    sub.add_argument("--timeout",      type=int, default=300,
                     help="Per-PDF API timeout (seconds)")
    sub.add_argument("--verbose",      action="store_true")
    sub.add_argument("--pdf-root",     default=None,
                     help="Root dir containing your PDF dataset")
    sub.add_argument("--output-root",  default=None,
                     help="Where to write processed_data/")
    sub.add_argument("--log-path",     default=None)
    sub.add_argument("--overwrite-log",action="store_true")
    sub.add_argument("--strict-paths", action="store_true")
    sub.add_argument("--missing-as-failure", action="store_true")
    sub.add_argument("--lang-filter",  default="",
                     help="Comma-separated lang_guess filter, e.g. 'unsure,indic'")
    sub.add_argument("--lang-priority",default="unsure,indic")
    sub.add_argument("--skip",         type=int, default=0,
                     help="Skip first N rows")
    sub.add_argument("--master-xlsx",  default=None)
    sub.add_argument("--link-map-xlsx",default=None)
