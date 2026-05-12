#!/usr/bin/env python3
"""
Check how many links in the Zoho workbook are accessible vs broken.

Usage:
    python pop_2/zoho_sheet_explorer.py [--workers N] [--timeout S]

Requires zoho_tokens.json (with access_token) in the current directory,
or ZOHO_TOKENS_FILE env var pointing elsewhere.
"""

import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        return it

# ── Config ────────────────────────────────────────────────────────────────────
TOKENS_FILE  = os.environ.get("ZOHO_TOKENS_FILE", "zoho_tokens.json")
WORKBOOK_ID  = os.environ.get("ZOHO_WORKBOOK_ID", "egcqk17ec3dd273a64674b4622eae0def0bdd")
SHEET_BASE   = "https://sheet.zoho.in/api/v2"
WD_BASE      = "https://workdrive.zoho.in/api/v1"
SKIP_SHEETS  = {"Matrix"}
TIMEOUT      = (10, 30)
MAX_WORKERS  = 8

_FILE_ID_RE = re.compile(r'/file/([a-zA-Z0-9]+)')


# ── Session setup ─────────────────────────────────────────────────────────────

def _make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Zoho-oauthtoken {token}"
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _load_tokens() -> dict:
    candidates = [
        Path(TOKENS_FILE),
        Path(__file__).resolve().parent.parent / TOKENS_FILE,
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    sys.exit(f"[ERROR] Could not find tokens file: {TOKENS_FILE}")


# ── Zoho Sheet API ─────────────────────────────────────────────────────────────

def list_worksheets(session: requests.Session) -> list[dict]:
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}",
                       params={"method": "worksheet.list"}, timeout=TIMEOUT)
    data = resp.json()
    if resp.status_code == 401 or "error_code" in data:
        sys.exit(
            f"[AUTH] Zoho token invalid or expired: {data.get('message', data)}\n"
            "Run: python pop_cli.py zoho-auth"
        )
    return data.get("worksheet_names", [])


def fetch_all_rows(session: requests.Session, worksheet_name: str) -> list[dict]:
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}", params={
        "method":          "worksheet.records.fetch",
        "worksheet_name":  worksheet_name,
        "start_row_index": 0,
        "row_count":       5000,
        "column_count":    20,
    }, timeout=TIMEOUT)
    data = resp.json()
    if "error_code" in data:
        print(f"  [WARN] API error for sheet '{worksheet_name}': {data}")
        return []
    return data.get("records", [])


# ── Link checker ──────────────────────────────────────────────────────────────

def _classify_link(link: str) -> str:
    if "workdrive.zoho" in link:
        return "workdrive"
    if "sheet.zoho" in link:
        return "sheet"
    return "other"


def check_link(session: requests.Session, link: str) -> tuple[str, str]:
    """Return (link, status) where status is 'ok', 'broken', or an error tag."""
    kind = _classify_link(link)

    if kind == "workdrive":
        m = _FILE_ID_RE.search(link)
        if not m:
            return link, "broken:no_file_id"
        file_id = m.group(1)
        for url in [f"{WD_BASE}/download/{file_id}", f"{WD_BASE}/files/{file_id}/content"]:
            try:
                resp = session.head(url, timeout=TIMEOUT, allow_redirects=True)
                if resp.status_code == 200:
                    return link, "ok"
                # HEAD may not be supported; fall through to GET probe
                resp = session.get(url, stream=True, timeout=TIMEOUT)
                if resp.status_code == 200:
                    ct = resp.headers.get("Content-Type", "")
                    # If we get back JSON/HTML it's an error page, not the file
                    if "json" not in ct and "html" not in ct:
                        return link, "ok"
                    return link, f"broken:http_{resp.status_code}_wrong_content"
                return link, f"broken:http_{resp.status_code}"
            except requests.exceptions.Timeout:
                return link, "broken:timeout"
            except requests.exceptions.ConnectionError:
                return link, "broken:connection_error"
            except Exception as e:
                return link, f"broken:exception_{type(e).__name__}"
        return link, "broken:all_urls_failed"

    elif kind == "sheet":
        # Zoho Sheet links are accessible if the session is valid (already verified above)
        return link, "ok:sheet_link"

    else:
        # Plain HTTP link — do a HEAD/GET without auth
        try:
            resp = requests.head(link, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code < 400:
                return link, "ok"
            resp = requests.get(link, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code < 400:
                return link, "ok"
            return link, f"broken:http_{resp.status_code}"
        except requests.exceptions.Timeout:
            return link, "broken:timeout"
        except requests.exceptions.ConnectionError:
            return link, "broken:connection_error"
        except Exception as e:
            return link, f"broken:exception_{type(e).__name__}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check accessibility of all links in the Zoho workbook.")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS,
                        help=f"Parallel workers (default: {MAX_WORKERS})")
    parser.add_argument("--timeout", type=float, default=30,
                        help="Per-request timeout in seconds (default: 30)")
    args = parser.parse_args()

    global TIMEOUT
    TIMEOUT = (10, args.timeout)

    tokens  = _load_tokens()
    session = _make_session(tokens["access_token"])

    # Gather all links
    print("Fetching worksheet list...")
    sheets = list_worksheets(session)
    state_sheets = [s for s in sheets if s["worksheet_name"] not in SKIP_SHEETS]
    print(f"Found {len(state_sheets)} state sheet(s) (skipping: {SKIP_SHEETS})\n")

    all_links: list[tuple[str, str]] = []   # (sheet_name, link)
    for sheet in state_sheets:
        name = sheet["worksheet_name"]
        rows = fetch_all_rows(session, name)
        for row in rows:
            link = row.get("Link", "")
            if isinstance(link, str) and link.strip():
                all_links.append((name, link.strip()))

    total = len(all_links)
    print(f"Total links found across all sheets: {total}\n")

    if total == 0:
        print("No links to check.")
        return

    # Check accessibility in parallel
    print(f"Checking links with {args.workers} workers...\n")
    results: list[tuple[str, str, str]] = []   # (sheet, link, status)
    link_items = all_links

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(check_link, session, link): (sheet, link)
            for sheet, link in link_items
        }
        for future in tqdm(as_completed(futures), total=total, unit="link"):
            sheet, link = futures[future]
            try:
                _, status = future.result()
            except Exception as e:
                status = f"broken:exception_{type(e).__name__}"
            results.append((sheet, link, status))

    # Tally results
    accessible = [r for r in results if r[2].startswith("ok")]
    broken     = [r for r in results if r[2].startswith("broken")]

    broken_by_reason: dict[str, int] = defaultdict(int)
    for _, _, status in broken:
        broken_by_reason[status] += 1

    broken_by_sheet: dict[str, int] = defaultdict(int)
    for sheet, _, status in broken:
        broken_by_sheet[sheet] += 1

    # Report
    w = 60
    print(f"\n{'='*w}")
    print(f"  LINK ACCESSIBILITY REPORT")
    print(f"{'='*w}")
    print(f"  Total links checked           : {total}")
    print(f"  Accessible (ok)               : {len(accessible):>6}  ({100*len(accessible)/total:.1f}%)")
    print(f"  Broken                        : {len(broken):>6}  ({100*len(broken)/total:.1f}%)")
    print(f"{'─'*w}")
    print(f"  Broken links by reason:")
    for reason, count in sorted(broken_by_reason.items(), key=lambda x: -x[1]):
        print(f"    {reason:<40} : {count}")
    print(f"{'─'*w}")
    print(f"  Broken links by sheet:")
    for sheet, count in sorted(broken_by_sheet.items(), key=lambda x: -x[1]):
        print(f"    {sheet:<40} : {count}")
    print(f"{'='*w}\n")

    # Dump broken links to file for follow-up
    broken_csv = Path(__file__).resolve().parent / "broken_links.csv"
    with open(broken_csv, "w") as f:
        f.write("sheet,link,reason\n")
        for sheet, link, status in sorted(broken, key=lambda x: x[0]):
            f.write(f"{sheet},{link},{status}\n")
    print(f"Broken links written to: {broken_csv}")


if __name__ == "__main__":
    main()
