#!/usr/bin/env python3
"""
zoho_pdf_download_v2.py

Selectively downloads only the PDFs whose WorkDrive links appear in the
'primary_link' column of --link (output of the dedup step).
Credentials are read from .pop_2_env at project root.

Usage:
    python zoho_pdf_download_v2.py --link unique_urls.xlsx
"""

import argparse
import json
import os
import re
import sys
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ── Config defaults (overridden at runtime via .pop_2_env) ────────────────────
WORKERS     = 8
TOKENS_FILE = "zoho_tokens.json"
WORKBOOK_ID = "egcqk17ec3dd273a64674b4622eae0def0bdd"
SHEET_BASE  = "https://sheet.zoho.in/api/v2"
WD_BASE     = "https://workdrive.zoho.in/api/v1"
OUTPUT_ROOT = Path("data/raw/POP Bank")
TIMEOUT     = (10, 60)
SKIP_SHEETS = {"Matrix"}

# ── Runtime state (populated by _setup) ──────────────────────────────────────
_tokens        = {}
_CLIENT_ID     = ""
_CLIENT_SECRET = ""
_REFRESH_TOKEN = ""
_ACCESS_TOKEN  = ""
_refresh_lock  = threading.Lock()
session        = None


# ── Env loader ────────────────────────────────────────────────────────────────

def _load_pop2_env():
    candidates = [
        Path(__file__).resolve().parent.parent / ".pop_2_env",
        Path(".pop_2_env"),
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break


def _setup():
    global _tokens, _CLIENT_ID, _CLIENT_SECRET, _REFRESH_TOKEN, _ACCESS_TOKEN, session
    global TOKENS_FILE, WORKBOOK_ID

    _load_pop2_env()

    TOKENS_FILE = os.environ.get("ZOHO_TOKENS_FILE", TOKENS_FILE)
    WORKBOOK_ID = os.environ.get("ZOHO_WORKBOOK_ID", WORKBOOK_ID)

    with open(TOKENS_FILE) as f:
        _tokens = json.load(f)

    _CLIENT_ID     = _tokens.get("client_id", "")
    _CLIENT_SECRET = _tokens.get("client_secret", "")
    _REFRESH_TOKEN = _tokens.get("refresh_token", "")
    _ACCESS_TOKEN  = _tokens["access_token"]

    session = requests.Session()
    session.headers.update({"Authorization": f"Zoho-oauthtoken {_ACCESS_TOKEN}"})
    sheet_retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
    session.mount("https://", HTTPAdapter(max_retries=sheet_retry))


# ── Auth ──────────────────────────────────────────────────────────────────────

def _auth_header() -> str:
    return f"Zoho-oauthtoken {_ACCESS_TOKEN}"


def _refresh_access_token() -> bool:
    global _ACCESS_TOKEN
    with _refresh_lock:
        if not (_REFRESH_TOKEN and _CLIENT_ID and _CLIENT_SECRET):
            print("[AUTH] Missing credentials in tokens file.")
            return False
        try:
            resp = requests.post(
                "https://accounts.zoho.in/oauth/v2/token",
                params={
                    "refresh_token": _REFRESH_TOKEN,
                    "client_id":     _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "grant_type":    "refresh_token",
                },
                timeout=(10, 30),
            )
            data = resp.json()
        except Exception as e:
            print(f"[AUTH] Refresh request failed: {e}")
            return False
        new_token = data.get("access_token")
        if not new_token:
            print(f"[AUTH] Refresh failed: {data}")
            return False
        _ACCESS_TOKEN = new_token
        session.headers.update({"Authorization": _auth_header()})
        try:
            _tokens["access_token"] = new_token
            tmp = TOKENS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(_tokens, f, indent=2)
            os.replace(tmp, TOKENS_FILE)
        except Exception as e:
            print(f"[WARN] Could not persist refreshed token: {e}")
        print("[AUTH] Access token refreshed.")
        return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'\s+', " ", name).strip()
    return name[:120]


def extract_file_id(link: str) -> str | None:
    m = re.search(r'/file/([a-zA-Z0-9]+)', link)
    return m.group(1) if m else None


# ── Zoho Sheet API ────────────────────────────────────────────────────────────

def list_worksheets() -> list[dict]:
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}",
                       params={"method": "worksheet.list"}, timeout=TIMEOUT)
    data = resp.json()
    if "error_code" in data or not data.get("worksheet_names"):
        print(f"  [Sheet API raw response]: {data}")
        if data.get("error_code") in ("1004", "1001") or "token" in str(data).lower():
            print("  [AUTH] Token may be expired — refreshing ...")
            if _refresh_access_token():
                resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}",
                                   params={"method": "worksheet.list"}, timeout=TIMEOUT)
                data = resp.json()
    return data.get("worksheet_names", [])


def fetch_all_rows(worksheet_name: str) -> list[dict]:
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}", params={
        "method":          "worksheet.records.fetch",
        "worksheet_name":  worksheet_name,
        "start_row_index": 0,
        "row_count":       5000,
        "column_count":    20,
    }, timeout=TIMEOUT)
    data = resp.json()
    if "error_code" in data:
        print(f"  API error for {worksheet_name}: {data}")
        return []
    return data.get("records", [])


# ── WorkDrive download ────────────────────────────────────────────────────────

def _make_dl_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": _auth_header()})
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def download_file(file_id: str, dest_path: Path) -> bool:
    s = _make_dl_session()
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


def download_one(args) -> tuple[str, object, int]:
    filename, file_id, dest = args
    if dest.exists() and dest.stat().st_size > 1024:
        return (filename, "exists", 0)
    ok = download_file(file_id, dest)
    size_kb = dest.stat().st_size // 1024 if ok else 0
    return (filename, ok, size_kb)


# ── Link loader ───────────────────────────────────────────────────────────────

def load_primary_links(path: str) -> set[str]:
    df = pd.read_excel(path, engine="openpyxl")
    col = next(
        (c for c in df.columns if c.strip().lower().replace(" ", "_") == "primary_link"),
        None,
    )
    if col is None:
        sys.exit(f"ERROR: no 'primary_link' column in {path}. Columns: {list(df.columns)}")
    links = df[col].dropna().astype(str).str.strip().tolist()
    print(f"Loaded {len(links)} primary links from {path}")
    return set(links)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    _setup()

    parser = argparse.ArgumentParser(
        description="Download PDFs from Zoho WorkDrive filtered by primary_link list."
    )
    parser.add_argument("--link", required=True,
                        help="XLSX with 'primary_link' column (output of the dedup step)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: download max 5 files")
    args = parser.parse_args()

    primary_links = load_primary_links(args.link)

    print("Listing worksheets ...")
    sheets = list_worksheets()
    state_sheets = [s for s in sheets if s["worksheet_name"] not in SKIP_SHEETS]
    print(f"Found {len(state_sheets)} state sheet(s)\n")

    work: list[tuple] = []
    seen_filenames: set[str] = set()

    for sheet in state_sheets:
        sheet_name = sheet["worksheet_name"]
        rows = fetch_all_rows(sheet_name)
        state_dir = OUTPUT_ROOT / sheet_name

        for row in rows:
            link = row.get("Link", "")
            if not isinstance(link, str) or not link.strip():
                continue
            link = link.strip()
            if link not in primary_links:
                continue

            file_id = extract_file_id(link)
            if not file_id:
                print(f"  [SKIP] Can't parse file ID: {link}")
                continue

            raw_name = row.get("Name of POPs") or row.get("Show Name") or file_id
            stem     = safe_filename(raw_name)
            filename = f"{stem}-{file_id}.pdf"

            if filename in seen_filenames:
                continue
            seen_filenames.add(filename)

            dest = state_dir / filename
            work.append((filename, file_id, dest))

    if args.test and len(work) > 5:
        print(f"[TEST MODE] Capping download queue from {len(work)} to 5 files.")
        work = work[:5]

    print(f"\n{len(work)} files matched. Starting downloads with {WORKERS} workers.\n")

    downloaded = skipped = failed = 0
    total = len(work)

    with ThreadPoolExecutor(max_workers=WORKERS) as exe:
        futures = {exe.submit(download_one, w): w for w in work}
        for i, fut in enumerate(as_completed(futures), 1):
            w = futures[fut]
            filename = w[0]
            try:
                fname, status, size_kb = fut.result()
                if status == "exists":
                    print(f"  [{i}/{total}] EXISTS  {fname}")
                    skipped += 1
                elif status:
                    print(f"  [{i}/{total}] OK      {fname}  ({size_kb} KB)")
                    downloaded += 1
                else:
                    print(f"  [{i}/{total}] FAIL    {fname}")
                    failed += 1
            except Exception as e:
                print(f"  [{i}/{total}] ERROR   {filename}: {e}")
                failed += 1

    print(f"\nDone.  Downloaded: {downloaded}  Exists/skipped: {skipped}  Failed: {failed}")


if __name__ == "__main__":
    main()
