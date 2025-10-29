#!/usr/bin/env python3
"""
Translate all DPT-2 markdown files using googletrans-only translator.
Saves `dpt2_result_translated.md` alongside each source file and writes a CSV summary.
"""
import sys
from pathlib import Path
import logging
import pandas as pd
import time
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# locate googletrans translator module
this_dir = Path(__file__).resolve().parents[2]
google_mod_path = this_dir / 'code' / 'src' / 'translation' / 'translate_phase2_googletrans.py'
if not google_mod_path.exists():
    # alternative fallback inside dpt2_processing/code
    google_mod_path = Path(__file__).resolve().parents[0] / 'translate_phase2_googletrans.py'

if not google_mod_path.exists():
    logger.error(f"googletrans translator module not found: {google_mod_path}")
    sys.exit(1)

# dynamic import
import importlib.util
spec = importlib.util.spec_from_file_location('translate_phase2_googletrans', str(google_mod_path))
google_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(google_mod)
translate_md_content = getattr(google_mod, 'translate_md_content')
detect_language = getattr(google_mod, 'detect_language')

# find all dpt2_result.md files under dpt2_processing/processed_data
repo_root = Path(__file__).resolve().parents[2]
processed_root = repo_root / 'dpt2_processing' / 'processed_data'
if not processed_root.exists():
    logger.error(f"Processed data directory not found: {processed_root}")
    sys.exit(1)

files = list(processed_root.rglob('dpt2_result.md'))
logger.info(f"Found {len(files)} DPT-2 markdown files to translate")

results = []
start_all = time.time()

from concurrent.futures import ThreadPoolExecutor, as_completed
import os


def process_file(md_path):
    """Worker to translate a single md file. Returns result dict."""
    try:
        md_text = md_path.read_text(encoding='utf-8')
        detected = detect_language(md_text[:2000]) if detect_language else None
        src = 'auto'
        logger.info(f"  Detected source language: {detected}; using source_lang={src} for translation ({md_path})")

        t0 = time.time()
        translated = translate_md_content(md_text, source_lang=src)
        took = time.time() - t0

        out_path = md_path.parent / 'dpt2_result_translated.md'
        out_path.write_text(translated, encoding='utf-8')

        logger.info(f"  Saved translated file: {out_path} (took {took:.1f}s)")
        return {
            'file': str(md_path),
            'translated_path': str(out_path),
            'source_lang': src,
            'duration_s': round(took, 2),
            'status': 'success',
            'error': None
        }
    except Exception as e:
        logger.exception(f"  Failed to translate {md_path}: {e}")
        return {
            'file': str(md_path),
            'translated_path': None,
            'source_lang': None,
            'duration_s': 0,
            'status': 'failed',
            'error': str(e)
        }


# Choose a conservative number of workers to avoid rate-limiting
max_workers = int(os.environ.get('DPT2_GOOGLE_WORKERS', '6'))
logger.info(f"Starting translation with up to {max_workers} workers")

with ThreadPoolExecutor(max_workers=max_workers) as exe:
    futures = {exe.submit(process_file, p): p for p in files}
    for i, fut in enumerate(as_completed(futures), 1):
        res = fut.result()
        results.append(res)
        logger.info(f"Progress: {len(results)}/{len(files)} files completed")

# write summary CSV
summary_path = repo_root / f"dpt2_googletrans_results_{int(time.time())}.csv"
pd.DataFrame(results).to_csv(summary_path, index=False)
logger.info(f"Wrote summary to {summary_path}")
logger.info("All done")
