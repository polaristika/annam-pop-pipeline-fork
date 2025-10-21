from __future__ import annotations

import os, hashlib, pandas as pd
import logging, warnings, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadWarning
from src.classify.english_vs_indic import english_vs_indic
import langid

DATA_ROOT = "data/raw/POP Bank"
INV_CSV = "pdf_inventory.csv"

FIRST_SAMPLE_PAGES = 5
MAX_CHARS = 6000
DIGITAL_CHAR_THRESHOLD = 200  # tune quickly if needed
INDIC_LANGS = {"hi","bn","ta","te","gu","kn","ml","or","pa"}


def md5sum(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _extract_sample(path: str) -> Dict[str, Any]:
    """Return dict with page_count and sample_text (may be empty)."""
    try:
        reader = PdfReader(path)
        page_count = len(reader.pages)
        buff = []
        total = 0
        for i, page in enumerate(reader.pages[:FIRST_SAMPLE_PAGES]):
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt:
                buff.append(txt)
                total += len(txt)
                if total >= MAX_CHARS:
                    break
        return {"page_count": page_count, "sample_text": "\n".join(buff)}
    except Exception as e:
        return {"error": str(e), "page_count": None, "sample_text": ""}


def _lang_detect(text: str) -> tuple[str, float]:
    if not text.strip():
        return ("", 0.0)
    lang, score = langid.classify(text[:4000])  # langid is fast; limit chars
    return lang, score


def classify_pdf_simple(path: str) -> Dict[str, Any]:
    meta = _extract_sample(path)
    if "error" in meta:
        return {
            "class": "error",
            "reason": f"parse_error={meta['error'][:120]}",
            "page_count": meta.get("page_count")
        }
    txt = meta["sample_text"]
    txt_len = len(txt)
    lang, score = _lang_detect(txt)

    # Fallback lang guess from filename if no text
    if not lang:
        lower_name = Path(path).name.lower()
        if any(tag in lower_name for tag in ["hin","hindi","mar","guj","tam","tel","kan","mal","pun","pan","ben","beng","ori","odu","urd"]):
            lang = "hi"  # pick a representative Indic tag
        else:
            lang = "en"
        score = 0.0

    is_indic = lang in INDIC_LANGS
    if txt_len >= DIGITAL_CHAR_THRESHOLD:
        klass = "digital_indic" if is_indic else "digital_en"
        decision = "digital_threshold"
    else:
        klass = "scanned_indic" if is_indic else "scanned_en"
        decision = "scanned_low_text"

    reason = f"len={txt_len} lang={lang} score={score:.2f} decision={decision}"
    return {"class": klass, "reason": reason, "page_count": meta["page_count"]}


def iter_pdfs(root: str):
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith('.pdf'):
                yield os.path.join(dirpath, f)


def _suppress_warnings_once():
    """Apply warning/log suppression (used in parent & worker processes)."""
    logging.getLogger("PyPDF2").setLevel(logging.ERROR)
    try:
        from PyPDF2.errors import PdfReadWarning  # local import safe
        warnings.filterwarnings("ignore", category=PdfReadWarning)
    except Exception:
        pass


def _process_single(path: str) -> Dict[str, Any]:
    """Worker function: compute row dict for a single PDF.

    Logic mirrors the sequential loop (no behavioral changes)."""
    _suppress_warnings_once()
    try:
        size = os.path.getsize(path)
    except OSError as e:
        # Unreadable file edge case
        return {
            "file_path": path,
            "state": Path(path).parent.name,
            "size_bytes": None,
            "md5": "",
            "page_count": None,
            "class": "error",
            "reason": f"stat_error={str(e)[:80]}",
            "status": "pending",
            "digital_guess": False,
            "lang_guess": "unsure",
            "lang_source": "osd",
            "lang_conf": 0.0,
            "lang_votes": "",
        }
    # md5 (same logic as before)
    md5 = md5sum(path)
    state = Path(path).parent.name
    result = classify_pdf_simple(path)
    probe = english_vs_indic(path, pages=2)
    digital_guess = result["class"].startswith("digital")
    return {
        "file_path": path,
        "state": state,
        "size_bytes": size,
        "md5": md5,
        "page_count": result.get("page_count"),
        "class": result["class"],
        "reason": result["reason"],
        "status": "pending",
        "digital_guess": digital_guess,
        "lang_guess": probe.get("lang_guess"),
        "lang_source": probe.get("lang_source"),
        "lang_conf": probe.get("lang_conf"),
        "lang_votes": ";".join(probe.get("osd_votes", [])),
        "garbled_detected": probe.get("garbled_detected", False),
    }


def main():
    _suppress_warnings_once()

    paths = list(iter_pdfs(DATA_ROOT))
    if not paths:
        print(f"No PDFs found under {DATA_ROOT}.")
        return

    # Worker count strategy: ENV var INVENTORY_WORKERS overrides, else CPU count.
    env_workers = os.environ.get("INVENTORY_WORKERS")
    if env_workers:
        try:
            workers = max(1, int(env_workers))
        except ValueError:
            workers = max(1, (os.cpu_count() or 4) - 1)
    else:
        # Leave one core free, cap at 32 for sanity.
        workers = min(32, max(1, (os.cpu_count() or 4) - 1))

    # Fallback to sequential if only one worker requested or just a handful of files.
    SEQ_THRESHOLD = 8
    if workers == 1 or len(paths) <= SEQ_THRESHOLD:
        rows = [_process_single(p) for p in paths]
    else:
        rows = []
        # Use ProcessPool for true parallelism (PyPDF2 + langid are CPU bound)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_single, p): p for p in paths}
            completed = 0
            total = len(futures)
            for fut in as_completed(futures):
                rows.append(fut.result())
                completed += 1
                # Lightweight progress every 5% or first 5 docs (avoid excessive prints)
                if completed <= 5 or completed % max(1, total // 20) == 0:
                    pct = (completed / total) * 100
                    print(f"Progress: {completed}/{total} ({pct:.1f}%)", end='\r', file=sys.stderr)
        # Final newline after carriage returns
        print("" , file=sys.stderr)

    df = pd.DataFrame(rows).sort_values("file_path")
    df.to_csv(INV_CSV, index=False)
    print(f"Wrote {INV_CSV} with {len(df)} rows (workers={workers})")


if __name__ == "__main__":  # pragma: no cover
    main()