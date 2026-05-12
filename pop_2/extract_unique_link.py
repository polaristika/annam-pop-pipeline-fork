import os
import re
import json
import hashlib
import threading
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm
import fitz
from PIL import Image
import imagehash
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ── Config defaults (overridden at runtime via .pop_2_env) ────────────────────
TOKENS_FILE            = "zoho_tokens.json"
WORKBOOK_ID            = "egcqk17ec3dd273a64674b4622eae0def0bdd"
SHEET_BASE             = "https://sheet.zoho.in/api/v2"
WD_BASE                = "https://workdrive.zoho.in/api/v1"
OUTPUT_EXCEL           = "unique_urls.xlsx"
OUTPUT_CSV             = "output.csv"
TIMEOUT                = (10, 60)
HASH_THRESHOLD         = 10
SKIP_SHEETS            = {"Matrix"}
CHECKPOINT_EVERY       = 100
CONSECUTIVE_FAIL_LIMIT = 50
MAX_WORKERS            = 6

# ── Runtime state (populated by _setup) ──────────────────────────────────────
_tokens        = {}
_CLIENT_ID     = ""
_CLIENT_SECRET = ""
_REFRESH_TOKEN = ""
_ACCESS_TOKEN  = ""
session        = None
_dl_session    = None
_token_lock    = threading.Lock()  # prevents concurrent token refreshes


# ── Env loader ────────────────────────────────────────────────────────────────

def _load_pop2_env():
    """Load .pop_2_env from project root into os.environ (existing vars take priority)."""
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
    """Load env config, read tokens file, and initialise session objects."""
    global _tokens, _CLIENT_ID, _CLIENT_SECRET, _REFRESH_TOKEN, _ACCESS_TOKEN
    global session, _dl_session
    global TOKENS_FILE, WORKBOOK_ID, OUTPUT_EXCEL, OUTPUT_CSV

    _load_pop2_env()

    TOKENS_FILE  = os.environ.get("ZOHO_TOKENS_FILE",  TOKENS_FILE)
    WORKBOOK_ID  = os.environ.get("ZOHO_WORKBOOK_ID",  WORKBOOK_ID)
    OUTPUT_CSV   = os.environ.get("DEDUP_OUTPUT_CSV",   OUTPUT_CSV)
    OUTPUT_EXCEL = os.environ.get("DEDUP_OUTPUT_XLSX",  OUTPUT_EXCEL)

    with open(TOKENS_FILE) as f:
        _tokens = json.load(f)

    _CLIENT_ID     = _tokens.get("client_id", "")
    _CLIENT_SECRET = _tokens.get("client_secret", "")
    _REFRESH_TOKEN = _tokens.get("refresh_token", "")
    _ACCESS_TOKEN  = _tokens["access_token"]

    headers = {"Authorization": f"Zoho-oauthtoken {_ACCESS_TOKEN}"}

    session = requests.Session()
    session.headers.update(headers)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
    session.mount("https://", HTTPAdapter(max_retries=retry))

    _dl_session = requests.Session()
    _dl_session.headers.update(headers)
    dl_retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 502, 503])
    _dl_session.mount("https://", HTTPAdapter(max_retries=dl_retry))


# ── Auth ──────────────────────────────────────────────────────────────────────

def _refresh_access_token() -> bool:
    """Exchange refresh token for a new access token; update sessions + tokens file.

    Thread-safe: acquires _token_lock so only one thread refreshes at a time.
    If another thread already refreshed while we were waiting, we return True
    immediately (the updated token is already on the shared sessions).
    """
    global _ACCESS_TOKEN
    with _token_lock:
        if not _REFRESH_TOKEN or not _CLIENT_ID or not _CLIENT_SECRET:
            print("[AUTH] Missing refresh_token/client_id/client_secret in tokens file — cannot auto-refresh.")
            return False
        token_before = _ACCESS_TOKEN
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
            print(f"[AUTH] Token refresh request failed: {e}")
            return False

        new_token = data.get("access_token")
        if not new_token:
            print(f"[AUTH] Token refresh failed: {data}")
            return False

        if new_token == token_before:
            return True  # another thread already refreshed; sessions are current

        _ACCESS_TOKEN = new_token
        auth_header = f"Zoho-oauthtoken {new_token}"
        session.headers.update({"Authorization": auth_header})
        _dl_session.headers.update({"Authorization": auth_header})

        try:
            _tokens["access_token"] = new_token
            tmp = TOKENS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(_tokens, f, indent=2)
            os.replace(tmp, TOKENS_FILE)
        except Exception as e:
            print(f"[WARN] Could not persist refreshed token: {e}")

        print("[AUTH] Access token refreshed successfully.")
        return True


_FILE_ID_RE = re.compile(r'/file/([a-zA-Z0-9]+)')


# ── Zoho Sheet API ────────────────────────────────────────────────────────────

def list_worksheets() -> list[dict]:
    resp = session.get(f"{SHEET_BASE}/{WORKBOOK_ID}",
                       params={"method": "worksheet.list"}, timeout=TIMEOUT)
    data = resp.json()
    if resp.status_code == 401 or "error_code" in data:
        raise SystemExit(
            f"[AUTH] Zoho token invalid or expired: {data.get('message', data)}\n"
            "Run: python pop_cli.py zoho-auth"
        )
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


# ── WorkDrive fetch ───────────────────────────────────────────────────────────

def extract_file_id(link: str) -> str | None:
    m = _FILE_ID_RE.search(link)
    return m.group(1) if m else None


_MAGIC = {
    b"%PDF":              "pdf",
    b"\xff\xd8\xff":      "image",
    b"\x89PNG":           "image",
    b"GIF8":              "image",
    b"BM":                "image",
    b"RIFF":              "image",
    b"PK\x03\x04":        "document",
    b"\xd0\xcf\x11\xe0":  "document",
    b"{\rtf":             "document",
    b"\x09\x08\x10\x00":  "document",
}


def _detect_type(data: bytes) -> str:
    for magic, ftype in _MAGIC.items():
        if data.startswith(magic):
            return ftype
    return ""


def fetch_file_bytes(file_id: str) -> tuple[BytesIO, str] | tuple[None, None]:
    urls = [f"{WD_BASE}/download/{file_id}", f"{WD_BASE}/files/{file_id}/content"]
    _refreshed = False
    for url in urls:
        try:
            resp = _dl_session.get(url, stream=True, timeout=TIMEOUT)
        except requests.exceptions.RequestException:
            continue
        if resp.status_code == 401:
            if not _refreshed and _refresh_access_token():
                _refreshed = True
                try:
                    resp = _dl_session.get(url, stream=True, timeout=TIMEOUT)
                except requests.exceptions.RequestException:
                    continue
                if resp.status_code == 401:
                    print("[AUTH] Still 401 after refresh — stopping.")
                    return None, None
            else:
                return None, None
        if resp.status_code != 200:
            continue
        ct = resp.headers.get("Content-Type", "")
        if "json" in ct or "html" in ct:
            continue
        try:
            data = b"".join(resp.iter_content(chunk_size=1 << 20))
        except requests.exceptions.RequestException:
            continue
        ftype = _detect_type(data)
        if ftype:
            return BytesIO(data), ftype

    return None, None


# ── File → images ─────────────────────────────────────────────────────────────

def image_to_images(img_bytes: BytesIO) -> list:
    try:
        return [Image.open(img_bytes).convert("RGB")]
    except Exception:
        return []


def pdf_to_images(pdf_bytes: BytesIO) -> list:
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes.read(), filetype="pdf")
    except Exception:
        return []
    for i in range(min(3, len(doc))):
        pix = doc[i].get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images


# ── Hash ──────────────────────────────────────────────────────────────────────

def compute_hashes(images: list):
    try:
        return [imagehash.phash(img) for img in images]
    except Exception:
        return None


def _classify_link(link: str) -> str:
    """Return link type: 'workdrive', 'sheet', or 'other'."""
    if "workdrive.zoho" in link:
        return "workdrive"
    if "sheet.zoho" in link:
        return "sheet"
    return "other"


def _fetch_and_hash(link: str) -> tuple[str, object, str, str]:
    """Download a file and compute its hash. Runs in a worker thread.

    Returns (link, hashes, ftype, skip_reason). hashes is None on any failure.
    skip_reason is '' on success, otherwise one of:
      sheet_link | other_link | no_file_id | download_failed |
      few_pages | image_failed | hash_failed | unknown_type
    """
    link_type = _classify_link(link)

    if link_type == "sheet":
        tqdm.write(f"[SHEET LINK ] {link}")
        return link, None, "", "sheet_link"

    if link_type == "other":
        tqdm.write(f"[OTHER LINK ] {link}")
        return link, None, "", "other_link"

    # WorkDrive link — try to download and hash
    file_id = extract_file_id(link)
    if not file_id:
        tqdm.write(f"[NO FILE ID ] {link}")
        return link, None, "", "no_file_id"

    tqdm.write(f"[DOWNLOADING] {link}")
    file_bytes, ftype = fetch_file_bytes(file_id)
    if file_bytes is None:
        tqdm.write(f"[DL FAILED  ] {link}")
        return link, None, "", "download_failed"

    if ftype == "pdf":
        images = pdf_to_images(file_bytes)
        if not images:
            tqdm.write(f"[NO PAGES   ] {link}")
            return link, None, ftype, "few_pages"
        hashes = compute_hashes(images)
        if hashes is None:
            tqdm.write(f"[HASH FAIL  ] {link}")
            return link, None, ftype, "hash_failed"
        tqdm.write(f"[HASHED     ] {link}  ({len(images)} pages)")
    elif ftype == "image":
        images = image_to_images(file_bytes)
        if not images:
            tqdm.write(f"[IMG FAIL   ] {link}")
            return link, None, ftype, "image_failed"
        hashes = compute_hashes(images)
        if hashes is None:
            tqdm.write(f"[HASH FAIL  ] {link}")
            return link, None, ftype, "hash_failed"
        tqdm.write(f"[HASHED     ] {link}  (image)")
    elif ftype == "document":
        hashes = hashlib.md5(file_bytes.read()).hexdigest()
        tqdm.write(f"[HASHED     ] {link}  (document MD5)")
    else:
        tqdm.write(f"[UNKNOWN TYP] {link}  (type={ftype!r})")
        return link, None, ftype, "unknown_type"

    return link, hashes, ftype, ""


def is_match(h1, h2) -> bool:
    if isinstance(h1, str) and isinstance(h2, str):
        return h1 == h2
    if isinstance(h1, list) and isinstance(h2, list):
        return sum(abs(a - b) for a, b in zip(h1, h2)) < HASH_THRESHOLD
    return False


def _hashes_to_str(hashes) -> str:
    if isinstance(hashes, str):
        return hashes
    return "|".join(str(h) for h in hashes)


def _str_to_hashes(val: str, ftype: str):
    if ftype == "document":
        return val
    try:
        parts = [p for p in val.split("|") if p and p != "nan"]
        if not parts:
            return None
        return [imagehash.hex_to_hash(p) for p in parts]
    except Exception:
        return None


# ── Checkpoint ────────────────────────────────────────────────────────────────

def save_checkpoint(rows_out: list):
    try:
        rows = [
            {
                "doc_id":       r["doc_id"],
                "primary_link": r["primary_link"],
                "duplicates":   ",".join(r["duplicates"]),
                "hash_value":   _hashes_to_str(r["hash"]),
                "ftype":        r["ftype"],
            }
            for r in rows_out
        ]
        pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    except Exception as e:
        print(f"[WARN] Checkpoint save failed: {e}")


def load_checkpoint() -> tuple[list, list, set]:
    if not os.path.exists(OUTPUT_CSV):
        return [], [], set()

    df = pd.read_csv(OUTPUT_CSV)
    rows_out = []
    hash_db  = []
    seen_links: set[str] = set()

    for _, row in df.iterrows():
        raw_dups = str(row.get("duplicates", ""))
        dups = [d for d in raw_dups.split(",") if d and d != "nan"]
        hashes = _str_to_hashes(str(row["hash_value"]), str(row["ftype"]))
        if hashes is None:
            print(f"[WARN] Skipping corrupt checkpoint row: {row.get('primary_link')}")
            continue
        rows_out.append({
            "doc_id":       int(row["doc_id"]),
            "primary_link": row["primary_link"],
            "duplicates":   dups,
            "hash":         hashes,
            "ftype":        str(row["ftype"]),
        })
        hash_db.append(hashes)
        seen_links.add(str(row["primary_link"]))
        seen_links.update(dups)

    return rows_out, hash_db, seen_links


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="Extract unique PDF links from Zoho via pHash dedup.")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: stop at 2 primary links with max 2 duplicates each")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS,
                        help=f"Parallel download workers (default: {MAX_WORKERS})")
    cli_args = parser.parse_args()
    TEST_MODE = cli_args.test
    workers   = cli_args.workers

    if TEST_MODE:
        print("[TEST MODE] Processing 50 links then stopping.")

    _setup()

    sheets = list_worksheets()
    state_sheets = [s for s in sheets if s["worksheet_name"] not in SKIP_SHEETS]
    print(f"Found {len(state_sheets)} sheet(s)")

    all_links = []
    for sheet in state_sheets:
        rows = fetch_all_rows(sheet["worksheet_name"])
        for row in rows:
            link = row.get("Link", "")
            if isinstance(link, str) and link.strip():
                all_links.append(link.strip())

    print(f"Total links from sheets: {len(all_links)}")

    rows_out, hash_db, seen_links = load_checkpoint()
    if seen_links:
        print(f"Resuming: {len(rows_out)} unique docs already found, "
              f"{len(seen_links)} links already processed")
        all_links = [l for l in all_links if l not in seen_links]
        print(f"Remaining: {len(all_links)} links to process")

    processed_count = 0  # successful hashes
    total_count     = 0  # all futures seen (success + failure)
    fail_count      = 0
    stop            = False

    counts = {
        "primary":       0,   # new unique doc added
        "duplicate":     0,   # hash matched existing primary
        "sheet_link":    0,   # Zoho Sheet link (not downloadable as file)
        "other_link":    0,   # non-Zoho / unrecognised link
        "no_file_id":    0,   # WorkDrive URL but no /file/ id parseable
        "download_failed": 0, # download returned nothing
        "few_pages":     0,   # PDF yielded no pages
        "image_failed":  0,   # image could not be opened
        "hash_failed":   0,   # hash computation returned None
        "unknown_type":  0,   # unrecognised magic bytes
    }

    print(f"Starting parallel download with {workers} workers.")

    pool = ThreadPoolExecutor(max_workers=workers)
    pbar = tqdm(total=len(all_links))
    try:
        futures = {pool.submit(_fetch_and_hash, link): link for link in all_links}

        for future in as_completed(futures):
            pbar.update(1)

            link, hashes, ftype, skip_reason = future.result()
            total_count += 1

            if hashes is None:
                if skip_reason in counts:
                    counts[skip_reason] += 1
                # Only count network failures toward the consecutive-fail circuit breaker
                if skip_reason in ("download_failed", ""):
                    fail_count += 1
                    if fail_count >= CONSECUTIVE_FAIL_LIMIT:
                        tqdm.write(f"\n[STOP] {fail_count} consecutive download failures — "
                                   f"check connectivity or token. Saving checkpoint.")
                        stop = True
                else:
                    fail_count = 0
            else:
                fail_count = 0  # reset on any success

                # ── dedup (main thread only — intentionally single-threaded) ──
                matched = False
                for i, existing in enumerate(hash_db):
                    if is_match(hashes, existing):
                        matched_primary = rows_out[i]["primary_link"]
                        if not TEST_MODE or len(rows_out[i]["duplicates"]) < 2:
                            rows_out[i]["duplicates"].append(link)
                        tqdm.write(f"[DUPLICATE  ] {link}\n               → matches primary: {matched_primary}")
                        counts["duplicate"] += 1
                        matched = True
                        break

                if not matched:
                    tqdm.write(f"[PRIMARY    ] {link}")
                    counts["primary"] += 1
                    rows_out.append({
                        "doc_id":       len(rows_out) + 1,
                        "primary_link": link,
                        "duplicates":   [],
                        "hash":         hashes,
                        "ftype":        ftype,
                    })
                    hash_db.append(hashes)

                processed_count += 1

                if not TEST_MODE and processed_count % CHECKPOINT_EVERY == 0:
                    save_checkpoint(rows_out)
                    tqdm.write(f"[CHECKPOINT] {len(rows_out)} unique docs, "
                               f"{processed_count} processed this session")

            # Test mode: stop after 50 links
            if TEST_MODE and total_count >= 50:
                tqdm.write(f"[TEST] Processed {total_count} items — stopping.")
                stop = True

            if stop:
                break  # exit as_completed immediately

    finally:
        pbar.close()
        pool.shutdown(wait=False, cancel_futures=True)  # cancel queued futures, don't block
        save_checkpoint(rows_out)
        print(f"\n[SAVED] Checkpoint written — {len(rows_out)} unique docs, {processed_count} processed this session.")

    skipped = (counts["download_failed"] + counts["few_pages"] + counts["image_failed"]
               + counts["hash_failed"] + counts["unknown_type"])
    non_workdrive = counts["sheet_link"] + counts["other_link"] + counts["no_file_id"]

    print(f"\n{'='*60}")
    print(f"  DEDUPLICATION RUN SUMMARY")
    print(f"{'='*60}")
    print(f"  Total links processed        : {total_count}")
    print(f"{'─'*60}")
    print(f"  [PRIMARY    ] New unique docs : {counts['primary']}")
    print(f"  [DUPLICATE  ] Hash matched    : {counts['duplicate']}")
    print(f"{'─'*60}")
    print(f"  [SHEET LINK ] Zoho Sheet URLs : {counts['sheet_link']}")
    print(f"  [OTHER LINK ] Non-Zoho URLs   : {counts['other_link']}")
    print(f"  [NO FILE ID ] Malformed WD URL: {counts['no_file_id']}")
    print(f"{'─'*60}")
    print(f"  [DL FAILED  ] Download failed : {counts['download_failed']}")
    print(f"  [NO PAGES   ] PDF yielded no pages: {counts['few_pages']}")
    print(f"  [IMG FAIL   ] Image open fail : {counts['image_failed']}")
    print(f"  [HASH FAIL  ] Hash failed      : {counts['hash_failed']}")
    print(f"  [UNKNOWN TYP] Unknown type    : {counts['unknown_type']}")
    print(f"{'─'*60}")
    print(f"  Non-WorkDrive (skipped)       : {non_workdrive}")
    print(f"  WorkDrive skipped (errors)    : {skipped}")
    print(f"  Unique docs in output.csv     : {len(rows_out)}")
    print(f"{'='*60}\n")

    final = [
        {
            "doc_id":       r["doc_id"],
            "primary_link": r["primary_link"],
            "duplicates":   ",".join(r["duplicates"]),
        }
        for r in rows_out
    ]
    df_out = pd.DataFrame(final)
    for _ in range(3):
        try:
            df_out.to_excel(OUTPUT_EXCEL, index=False)
            break
        except PermissionError:
            print("Close output.xlsx and retrying...")
            import time; time.sleep(3)

    print(f"Output saved to: {OUTPUT_EXCEL} and {OUTPUT_CSV}")
    # Force-exit to bypass concurrent.futures' atexit join on in-flight worker threads.
    # All file I/O is complete above; skipping cleanup is safe here.
    os._exit(0)


if __name__ == "__main__":
    main()
