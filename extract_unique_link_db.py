import argparse
import hashlib
import json
import os
import re
import time
from io import BytesIO

import imagehash
import fitz
import pandas as pd
import requests
from PIL import Image
from pymongo import MongoClient
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

# ---------------- CONFIG ----------------
TOKENS_FILE      = "zoho_tokens.json"
WD_BASE          = "https://workdrive.zoho.in/api/v1"
OUTPUT_CSV       = "output.csv"
TIMEOUT          = (10, 60)
HASH_THRESHOLD   = 10
CHECKPOINT_EVERY = 100   # checkpoint output.csv every N sources processed

with open(TOKENS_FILE) as f:
    tokens = json.load(f)

_CLIENT_ID          = tokens.get("client_id", "")
_CLIENT_SECRET      = tokens.get("client_secret", "")
_REFRESH_TOKEN      = tokens.get("refresh_token", "")
_ACCESS_TOKEN       = tokens["access_token"]
_token_refreshed_at = 0.0   # epoch seconds of last successful refresh

HEADERS = {"Authorization": f"Zoho-oauthtoken {_ACCESS_TOKEN}"}

session = requests.Session()
session.headers.update(HEADERS)
retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
session.mount("https://", HTTPAdapter(max_retries=retry))

_dl_session = requests.Session()
_dl_session.headers.update(HEADERS)
_dl_retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 502, 503])
_dl_session.mount("https://", HTTPAdapter(max_retries=_dl_retry))


def _refresh_access_token() -> bool:
    global _ACCESS_TOKEN, _token_refreshed_at
    # Zoho tokens last 3600 s. If we refreshed recently, a 401 is a permissions
    # issue on that specific file — not an expired token. Skip to avoid rate limits.
    if time.time() - _token_refreshed_at < 3500:
        return False
    if not _REFRESH_TOKEN or not _CLIENT_ID or not _CLIENT_SECRET:
        print("[AUTH] Missing refresh_token/client_id/client_secret in zoho_tokens.json — cannot auto-refresh.")
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
        print(f"[AUTH] Token refresh request failed: {e}")
        return False

    new_token = data.get("access_token")
    if not new_token:
        print(f"[AUTH] Token refresh failed: {data}")
        return False

    _ACCESS_TOKEN = new_token
    auth_header = f"Zoho-oauthtoken {new_token}"
    session.headers.update({"Authorization": auth_header})
    _dl_session.headers.update({"Authorization": auth_header})

    try:
        tokens["access_token"] = new_token
        tmp = TOKENS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(tokens, f, indent=2)
        os.replace(tmp, TOKENS_FILE)
    except Exception as e:
        print(f"[WARN] Could not persist refreshed token: {e}")

    _token_refreshed_at = time.time()
    print("[AUTH] Access token refreshed successfully.")
    return True


_FILE_ID_RE = re.compile(r'/file/([a-zA-Z0-9]+)')


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


def fetch_file_bytes(file_id: str, wd_base: str = WD_BASE) -> tuple[BytesIO, str] | tuple[None, None]:
    urls = [f"{wd_base}/download/{file_id}", f"{wd_base}/files/{file_id}/content"]
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


def compute_hashes(images: list):
    try:
        return [imagehash.phash(img) for img in images]
    except Exception:
        return None


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


# ---------------- CSV HELPERS ----------------

def load_output_csv() -> tuple[dict, list, list]:
    """Load output.csv into url_lookup, hash_db, and rows_out."""
    if not os.path.exists(OUTPUT_CSV):
        return {}, [], []

    df = pd.read_csv(OUTPUT_CSV)
    url_lookup: dict[str, dict] = {}
    hash_db: list[tuple] = []
    rows_out: list[dict] = []

    for _, row in df.iterrows():
        ftype   = str(row["ftype"])
        hstr    = str(row["hash_value"])
        primary = str(row["primary_link"])
        raw_dups = str(row.get("duplicates", ""))
        dups = [d for d in raw_dups.split(",") if d and d != "nan"]
        hashes = _str_to_hashes(hstr, ftype)
        if hashes is None:
            print(f"[WARN] Skipping corrupt CSV row: {primary}")
            continue
        entry = {"primary_link": primary, "hash_value": hstr, "ftype": ftype}
        url_lookup[primary] = entry
        for d in dups:
            url_lookup[d] = entry
        hash_db.append((hashes, primary, hstr, ftype))
        rows_out.append({
            "doc_id":       int(row["doc_id"]),
            "primary_link": primary,
            "duplicates":   dups,
            "hash_value":   hstr,
            "ftype":        ftype,
        })

    return url_lookup, hash_db, rows_out


def save_output_csv(rows_out: list):
    rows = [
        {
            "doc_id":       r["doc_id"],
            "primary_link": r["primary_link"],
            "duplicates":   ",".join(r["duplicates"]),
            "hash_value":   r["hash_value"],
            "ftype":        r["ftype"],
        }
        for r in rows_out
    ]
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)


def append_to_output_csv(rows_out: list, hash_db: list, url_lookup: dict,
                          url: str, hashes, ftype: str):
    """Register a genuinely new unique document in all three in-memory structures."""
    hash_str = _hashes_to_str(hashes)
    doc_id   = len(rows_out) + 1
    entry    = {"primary_link": url, "hash_value": hash_str, "ftype": ftype}
    rows_out.append({
        "doc_id":       doc_id,
        "primary_link": url,
        "duplicates":   [],
        "hash_value":   hash_str,
        "ftype":        ftype,
    })
    hash_db.append((hashes, url, hash_str, ftype))
    url_lookup[url] = entry


# ---------------- MONGO HELPERS ----------------

def is_zoho_workdrive(url: str) -> bool:
    return ("workdrive.zoho.in" in url or "workdrive.zohoexternal.in" in url) and "/file/" in url


def upsert_unique_link(col, source: str, hash_str: str = None, flag: bool = False):
    doc = {"source": source}
    if hash_str is not None:
        doc["hash"] = hash_str
    if flag:
        doc["flag"] = True
    col.update_one({"source": source}, {"$set": doc}, upsert=True)


# ---------------- REFLAG PASS ----------------

def reprocess_flagged_links(unique_link_col, url_lookup: dict, hash_db: list, rows_out: list) -> bool:
    """Re-process every flag:true entry in unique_link.

    Resolution rules:
      - URL is primary in url_lookup      → remove flag, add hash in-place
      - URL is duplicate in url_lookup    → delete entry, upsert primary (add if missing)
      - Zoho link, hash match found       → delete entry, upsert matched primary
      - Zoho link, no hash match          → remove flag, add hash in-place (becomes new primary)
      - Malformed / not downloadable / unhashable / non-Zoho → leave as-is (skip)
    Returns True if output.csv was modified.
    """
    flagged = list(unique_link_col.find({"flag": True}))
    if not flagged:
        print("[REFLAG] No flagged entries found.")
        return False

    print(f"[REFLAG] Reprocessing {len(flagged)} flagged entries...")
    csv_dirty = False
    resolved  = 0
    removed   = 0

    for doc in tqdm(flagged, desc="Reprocessing flagged"):
        url = doc.get("source", "")
        if not url:
            unique_link_col.delete_one({"_id": doc["_id"]})
            removed += 1
            continue

        if url in url_lookup:
            entry   = url_lookup[url]
            primary = entry["primary_link"]
            if url == primary:
                # ── URL is the primary — remove flag, add hash ───────────────
                print(f"[REFLAG FOUND ] {url}\n               → is primary, removing flag")
                unique_link_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"hash": entry["hash_value"]}, "$unset": {"flag": ""}},
                )
                resolved += 1
            else:
                # ── URL is a duplicate — delete this, ensure primary is present
                print(f"[REFLAG FOUND ] {url}\n               → duplicate of {primary}, deleting from unique_link")
                unique_link_col.delete_one({"_id": doc["_id"]})
                upsert_unique_link(unique_link_col, primary, entry["hash_value"])
                resolved += 1

        elif is_zoho_workdrive(url):
            # ── Try downloading and hashing ──────────────────────────────────
            file_id = extract_file_id(url)
            if not file_id:
                print(f"[REFLAG SKIP  ] Malformed Zoho URL, leaving as-is: {url}")
                continue

            wd_base = (
                "https://workdrive.zohoexternal.in/api/v1"
                if "zohoexternal" in url else WD_BASE
            )
            file_bytes, ftype = fetch_file_bytes(file_id, wd_base)

            if file_bytes is None:
                print(f"[REFLAG SKIP  ] Still not downloadable, leaving as-is: {url}")
                continue

            hashes = None
            if ftype == "pdf":
                images = pdf_to_images(file_bytes)
                if images:
                    hashes = compute_hashes(images)
            elif ftype == "image":
                images = image_to_images(file_bytes)
                if images:
                    hashes = compute_hashes(images)
            elif ftype == "document":
                hashes = hashlib.md5(file_bytes.read()).hexdigest()

            if hashes is None:
                print(f"[REFLAG SKIP  ] Could not hash ({ftype}), leaving as-is: {url}")
                continue

            matched_idx = None
            for i, (existing_hashes, *_) in enumerate(hash_db):
                if is_match(hashes, existing_hashes):
                    matched_idx = i
                    break

            if matched_idx is not None:
                # Hash matched an existing primary — delete this entry, upsert primary
                _, matched_primary, matched_hash_str, matched_ftype = hash_db[matched_idx]
                print(f"[REFLAG HIT   ] {url}\n               → matches primary: {matched_primary}")
                unique_link_col.delete_one({"_id": doc["_id"]})
                upsert_unique_link(unique_link_col, matched_primary, matched_hash_str)
                rows_out[matched_idx]["duplicates"].append(url)
                url_lookup[url] = {
                    "primary_link": matched_primary,
                    "hash_value":   matched_hash_str,
                    "ftype":        matched_ftype,
                }
                csv_dirty = True
                resolved += 1
            else:
                # No match — this URL becomes a new primary
                hash_str = _hashes_to_str(hashes)
                print(f"[REFLAG NEW   ] {url}\n               → new unique, adding to output.csv")
                unique_link_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"hash": hash_str}, "$unset": {"flag": ""}},
                )
                append_to_output_csv(rows_out, hash_db, url_lookup, url, hashes, ftype)
                csv_dirty = True
                resolved += 1

        else:
            # ── Still non-Zoho — leave as-is ────────────────────────────────
            print(f"[REFLAG SKIP  ] Still non-Zoho, leaving as-is: {url}")

    print(f"[REFLAG] Done — {resolved} resolved, {removed} removed.")
    return csv_dirty


# ---------------- MAIN ----------------

def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate MongoDB document sources against output.csv and populate unique_link collection."
    )
    parser.add_argument("--mongo-uri",         required=True,  help="MongoDB connection URI")
    parser.add_argument("--db",                required=True,  help="Database name")
    parser.add_argument("--collection",        required=True,  help="Input collection name")
    parser.add_argument("--unique-collection", required=True,  help="Output collection name for unique links")
    parser.add_argument(
        "--mode",
        choices=["reflag", "process", "all"],
        default="all",
        help="reflag: re-process flagged unique_link entries only | "
             "process: run main MongoDB loop only | "
             "all: run reflag pass then main loop (default)",
    )
    args = parser.parse_args()

    client          = MongoClient(args.mongo_uri)
    db              = client[args.db]
    input_col       = db[args.collection]
    unique_link_col = db[args.unique_collection]

    print(f"Connected to MongoDB: db={args.db}, collection={args.collection}, mode={args.mode}")

    url_lookup, hash_db, rows_out = load_output_csv()
    print(f"Loaded output.csv: {len(rows_out)} unique docs, {len(url_lookup)} URL entries")

    # ── REFLAG PASS ──────────────────────────────────────────────────────────
    if args.mode in ("reflag", "all"):
        if reprocess_flagged_links(unique_link_col, url_lookup, hash_db, rows_out):
            save_output_csv(rows_out)
            print(f"[REFLAG] output.csv updated — now {len(rows_out)} unique docs")
        if args.mode == "reflag":
            print("Reflag pass complete.")
            return

    # ── MAIN PROCESSING LOOP ─────────────────────────────────────────────────
    total_docs        = input_col.count_documents({})
    csv_dirty         = False
    sources_processed = 0

    counts = {
        "found_primary":    0,   # Case A — URL is the primary itself
        "found_duplicate":  0,   # Case A — URL is a known duplicate
        "hash_hit":         0,   # Case B1 — hash matched existing entry
        "new_unique":       0,   # Case B2 — new unique, added to output.csv
        "non_zoho":         0,   # Case C — non-Zoho link, flagged
        "malformed_zoho":   0,   # Zoho URL but no file ID parseable
        "skip_download":    0,   # not downloadable
        "skip_no_pages":    0,   # PDF yielded no pages
        "skip_hash_fail":   0,   # hash computation returned None
        "skip_unknown_type":0,   # unrecognised magic bytes
    }

    for mongo_doc in tqdm(input_col.find({}), total=total_docs, desc="Processing docs"):
        doc_modified = False
        sources      = mongo_doc.get("sources", [])

        for source_obj in sources:
            url = source_obj.get("source", "")
            if not isinstance(url, str) or not url.strip():
                continue
            url = url.strip()

            # Count every non-empty source so the checkpoint fires reliably
            sources_processed += 1

            if url in url_lookup:
                # ── CASE A: URL already known in output.csv ───────────────────
                entry   = url_lookup[url]
                primary = entry["primary_link"]
                if url == primary:
                    print(f"[FOUND    ] {url}\n             → is primary link")
                    counts["found_primary"] += 1
                else:
                    print(f"[FOUND    ] {url}\n             → duplicate of: {primary}")
                    counts["found_duplicate"] += 1
                upsert_unique_link(unique_link_col, primary, entry["hash_value"])
                if source_obj["source"] != primary:
                    source_obj["source"] = primary
                    doc_modified = True

            elif is_zoho_workdrive(url):
                # ── CASE B: Zoho WorkDrive link, not in output.csv ───────────
                file_id = extract_file_id(url)
                if not file_id:
                    print(f"[NON-ZOHO ] Malformed Zoho URL, flagging: {url}")
                    upsert_unique_link(unique_link_col, url, flag=True)
                    counts["malformed_zoho"] += 1
                else:
                    print(f"[HASH     ] Downloading and hashing: {url}")
                    wd_base = (
                        "https://workdrive.zohoexternal.in/api/v1"
                        if "zohoexternal" in url
                        else WD_BASE
                    )
                    file_bytes, ftype = fetch_file_bytes(file_id, wd_base)

                    if file_bytes is None:
                        print(f"[SKIP     ] Not downloadable, flagging: {url}")
                        upsert_unique_link(unique_link_col, url, flag=True)
                        counts["skip_download"] += 1
                    else:
                        hashes = None
                        if ftype == "pdf":
                            images = pdf_to_images(file_bytes)
                            if not images:
                                print(f"[SKIP     ] PDF yielded no pages, flagging: {url}")
                                upsert_unique_link(unique_link_col, url, flag=True)
                                counts["skip_no_pages"] += 1
                            else:
                                hashes = compute_hashes(images)
                                if hashes is None:
                                    print(f"[SKIP     ] Hash computation failed, flagging: {url}")
                                    upsert_unique_link(unique_link_col, url, flag=True)
                                    counts["skip_hash_fail"] += 1
                                else:
                                    print(f"[HASH     ] PDF hash computed ({len(images)} page(s)): {url}")
                        elif ftype == "image":
                            images = image_to_images(file_bytes)
                            if not images:
                                print(f"[SKIP     ] Could not open image, flagging: {url}")
                                upsert_unique_link(unique_link_col, url, flag=True)
                                counts["skip_no_pages"] += 1
                            else:
                                hashes = compute_hashes(images)
                                if hashes is None:
                                    print(f"[SKIP     ] Hash computation failed, flagging: {url}")
                                    upsert_unique_link(unique_link_col, url, flag=True)
                                    counts["skip_hash_fail"] += 1
                                else:
                                    print(f"[HASH     ] Image hash computed: {url}")
                        elif ftype == "document":
                            hashes = hashlib.md5(file_bytes.read()).hexdigest()
                            print(f"[HASH     ] Document MD5 computed: {url}")
                        else:
                            print(f"[SKIP     ] Unknown file type ({ftype}), flagging: {url}")
                            upsert_unique_link(unique_link_col, url, flag=True)
                            counts["skip_unknown_type"] += 1

                        if hashes is not None:
                            matched_idx = None
                            for i, (existing_hashes, *_) in enumerate(hash_db):
                                if is_match(hashes, existing_hashes):
                                    matched_idx = i
                                    break

                            if matched_idx is not None:
                                # ── CASE B1: hash matched an existing entry ───
                                _, matched_primary, matched_hash_str, _ = hash_db[matched_idx]
                                print(f"[HASH HIT ] {url}\n             → matches primary: {matched_primary}")
                                upsert_unique_link(unique_link_col, matched_primary, matched_hash_str)
                                source_obj["source"] = matched_primary
                                doc_modified = True
                                rows_out[matched_idx]["duplicates"].append(url)
                                url_lookup[url] = {
                                    "primary_link": matched_primary,
                                    "hash_value":   matched_hash_str,
                                    "ftype":        hash_db[matched_idx][3],
                                }
                                csv_dirty = True
                                counts["hash_hit"] += 1
                            else:
                                # ── CASE B2: genuinely new unique document ────
                                hash_str = _hashes_to_str(hashes)
                                print(f"[NEW UNIQ ] {url}\n             → no match found, added as new unique (hash: {hash_str[:40]})")
                                upsert_unique_link(unique_link_col, url, hash_str)
                                append_to_output_csv(rows_out, hash_db, url_lookup, url, hashes, ftype)
                                csv_dirty = True
                                counts["new_unique"] += 1
                                # source stays as-is (it is the primary)

            else:
                # ── CASE C: non-Zoho link ────────────────────────────────────
                print(f"[NON-ZOHO ] Flagging non-Zoho link: {url}")
                upsert_unique_link(unique_link_col, url, flag=True)
                counts["non_zoho"] += 1
                # source stays as-is

            if sources_processed % CHECKPOINT_EVERY == 0 and csv_dirty:
                save_output_csv(rows_out)
                csv_dirty = False
                print(f"[CHECKPOINT] CSV saved — {len(rows_out)} rows, {sources_processed} sources processed")

        if doc_modified:
            input_col.update_one(
                {"_id": mongo_doc["_id"]},
                {"$set": {"sources": sources}},
            )

    if csv_dirty:
        save_output_csv(rows_out)

    print(f"\nDone. {len(rows_out)} unique docs in CSV, {sources_processed} sources processed.")

    # ── Write summary.md ─────────────────────────────────────────────────────
    skipped = (counts["skip_download"] + counts["skip_no_pages"]
               + counts["skip_hash_fail"] + counts["skip_unknown_type"])
    summary = f"""# Deduplication Run Summary

## Overview
| | |
|---|---|
| Total sources processed | {sources_processed} |
| MongoDB docs scanned | {total_docs} |
| Unique docs in output.csv after run | {len(rows_out)} |

## Link breakdown

| Category | Count |
|---|---|
| Found in output.csv — as primary link | {counts["found_primary"]} |
| Found in output.csv — as duplicate | {counts["found_duplicate"]} |
| Zoho link — hash matched existing entry | {counts["hash_hit"]} |
| Zoho link — new unique (added to output.csv) | {counts["new_unique"]} |
| Non-Zoho link (flagged) | {counts["non_zoho"]} |
| Malformed Zoho URL (flagged) | {counts["malformed_zoho"]} |

## Skipped links

| Reason | Count |
|---|---|
| Not downloadable | {counts["skip_download"]} |
| PDF/image yielded no pages | {counts["skip_no_pages"]} |
| Hash computation failed | {counts["skip_hash_fail"]} |
| Unknown file type | {counts["skip_unknown_type"]} |
| **Total skipped** | **{skipped}** |
"""
    with open("summary.md", "w") as f:
        f.write(summary)
    print("Summary written to summary.md")


if __name__ == "__main__":
    main()
