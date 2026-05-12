#!/usr/bin/env python3
"""
Zoho PDF Downloader
Reads all state sheets from the Zoho workbook, collects WorkDrive PDF links,
and downloads them to data/raw/POP Bank/{State}/ matching the existing pipeline.
"""

import requests
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WORKERS = 8   # parallel download threads

TOKENS_FILE = "zoho_tokens.json"
WORKBOOK_ID = "egcqk17ec3dd273a64674b4622eae0def0bdd"
SHEET_BASE  = "https://sheet.zoho.in/api/v2"
WD_BASE     = "https://workdrive.zoho.in/api/v1"
OUTPUT_ROOT = Path("data/raw/POP Bank")
TIMEOUT     = (10, 60)   # (connect seconds, read seconds)

SKIP_SHEETS = {"Matrix"}

with open(TOKENS_FILE) as f:
    tokens = json.load(f)

HEADERS = {"Authorization": f"Zoho-oauthtoken {tokens['access_token']}"}

# Persistent session with retry — reuses TCP connections, avoids repeated DNS
session = requests.Session()
session.headers.update(HEADERS)
retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
session.mount("https://", HTTPAdapter(max_retries=retry))


# ── Helpers ────────────────────────────────────────────────────────────────

def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'\s+', " ", name).strip()
    return name[:120]


def extract_file_id(link: str) -> str | None:
    m = re.search(r'/file/([a-zA-Z0-9]+)', link)
    return m.group(1) if m else None


def extract_stem(filename: str) -> str:
    """Strip the -{id}.pdf suffix to get the base name for dedup checks."""
    return re.sub(r'-[a-zA-Z0-9]+\.pdf$', '', filename, flags=re.IGNORECASE)


def build_existing_stems(root: Path) -> set[str]:
    """Scan all PDFs already on disk and return a set of their base stems."""
    stems = set()
    for pdf in root.rglob("*.pdf"):
        stems.add(extract_stem(pdf.name))
    print(f"  {len(stems)} unique stems found across all state folders")
    return stems


# ── Zoho Sheet API ─────────────────────────────────────────────────────────

def list_worksheets() -> list[dict]:
    print("Listing worksheets ...", flush=True)
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}",
                       params={"method": "worksheet.list"}, timeout=TIMEOUT)
    return resp.json().get("worksheet_names", [])


def fetch_all_rows(worksheet_name: str) -> list[dict]:
    """Fetch all rows. The API ignores start_row_index and returns everything
    in one shot, so we just make a single large request."""
    print(f"   fetching all rows ...", flush=True)
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}", params={
        "method":          "worksheet.records.fetch",
        "worksheet_name":  worksheet_name,
        "start_row_index": 0,
        "row_count":       5000,
        "column_count":    20,
    }, timeout=TIMEOUT)
    data = resp.json()
    if "error_code" in data:
        print(f"   API error: {data}", flush=True)
        return []
    rows = data.get("records", [])
    print(f"   got {len(rows)} rows", flush=True)
    return rows


# ── WorkDrive download ─────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def download_file(file_id: str, dest_path: Path) -> bool:
    """Download a WorkDrive file by ID (each call uses its own session for thread safety)."""
    s = _make_session()
    for url in [f"{WD_BASE}/download/{file_id}",
                f"{WD_BASE}/files/{file_id}/content"]:
        resp = s.get(url, stream=True, timeout=TIMEOUT)
        if resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct or "html" in ct:
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
            return dest_path.stat().st_size > 1024
    return False


def download_one(args) -> tuple[str, bool, int]:
    """Worker function: returns (filename, status, size_kb).

    Status values: True (downloaded), 'exists' (already present), 'renamed', False (failed).
    old_dest is the legacy path without the ID suffix; if it exists we rename it in place.
    """
    i, total, filename, file_id, dest, old_dest = args
    if dest.exists() and dest.stat().st_size > 1024:
        return (filename, "exists", 0)
    if old_dest is not None and old_dest.exists() and old_dest.stat().st_size > 1024:
        old_dest.rename(dest)
        return (filename, "renamed", dest.stat().st_size // 1024)
    ok = download_file(file_id, dest)
    size_kb = dest.stat().st_size // 1024 if ok else 0
    return (filename, ok, size_kb)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    sheets = list_worksheets()
    state_sheets = [s for s in sheets if s["worksheet_name"] not in SKIP_SHEETS]
    print(f"Found {len(state_sheets)} state sheets:\n")
    for i, s in enumerate(state_sheets, 1):
        print(f"  {i:2}.  {s['worksheet_name']}")
    print()
    raw = input("Enter state numbers to download (space-separated), or press Enter for ALL: ").strip()
    if raw:
        try:
            chosen = {int(n) for n in raw.split()}
            state_sheets = [s for i, s in enumerate(state_sheets, 1) if i in chosen]
        except ValueError:
            print("Invalid input — downloading ALL states.")
    print(f"\nDownloading {len(state_sheets)} state(s): {', '.join(s['worksheet_name'] for s in state_sheets)}\n")

    print("Scanning existing downloads for duplicates ...")
    existing_stems = build_existing_stems(OUTPUT_ROOT)

    total_files = skipped = failed = downloaded = 0

    for sheet in state_sheets:
        sheet_name = sheet["worksheet_name"]
        print(f"\n{'='*50}")
        print(f"Sheet: {sheet_name}", flush=True)

        rows = fetch_all_rows(sheet_name)
        pdf_rows = [r for r in rows if r.get("Link")]
        print(f"  {len(pdf_rows)} links found in {len(rows)} rows")

        if not pdf_rows:
            continue

        state_dir = OUTPUT_ROOT / sheet_name
        state_dir.mkdir(parents=True, exist_ok=True)

        # Build work list — ID suffix makes filenames unique across duplicate names
        work = []
        seen_filenames: set[str] = set()
        for i, row in enumerate(pdf_rows, 1):
            link    = row.get("Link", "")
            file_id = extract_file_id(link)
            if not file_id:
                print(f"  [{i}/{len(pdf_rows)}] SKIP  can't parse: {link}")
                skipped += 1
                continue
            raw_name = row.get("Name of POPs") or row.get("Show Name") or file_id
            stem     = safe_filename(raw_name)
            filename = f"{stem}-{file_id}.pdf"
            if filename in seen_filenames:
                continue  # exact duplicate link, skip
            if stem in existing_stems:
                print(f"  [{i}/{len(pdf_rows)}] DUP    {stem} (exists in another folder)")
                skipped += 1
                continue
            seen_filenames.add(filename)
            existing_stems.add(stem)  # prevent cross-state dupes within this run
            dest     = state_dir / filename
            old_dest = state_dir / (stem + ".pdf")  # legacy name without ID
            work.append((i, len(pdf_rows), filename, file_id, dest, old_dest))

        total_files += len(work)

        # Parallel download
        with ThreadPoolExecutor(max_workers=WORKERS) as exe:
            futures = {exe.submit(download_one, w): w for w in work}
            for fut in as_completed(futures):
                w = futures[fut]
                i = w[0]
                n = w[1]
                filename = w[2]
                try:
                    fname, status, size_kb = fut.result()
                    if status == "exists":
                        print(f"  [{i}/{n}] EXISTS   {fname}")
                        skipped += 1
                    elif status == "renamed":
                        print(f"  [{i}/{n}] RENAMED  {fname}  ({size_kb} KB)")
                        downloaded += 1
                    elif status:
                        print(f"  [{i}/{n}] OK     {fname}  ({size_kb} KB)")
                        downloaded += 1
                    else:
                        print(f"  [{i}/{n}] FAIL   {fname}")
                        failed += 1
                except Exception as e:
                    print(f"  [{i}/{n}] ERROR  {filename}: {e}")
                    failed += 1

    print(f"\n{'='*50}")
    print(f"Done.  Downloaded: {downloaded}  Skipped: {skipped}  Failed: {failed}  Total: {total_files}")


if __name__ == "__main__":
    main()
