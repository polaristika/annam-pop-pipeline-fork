"""
ndb/upload.py  –  Step 2: Upload processed JSON → MongoDB (NDB schema)

For every dpt2_result.json under processed_data_new/:
  1. Resolve link via output.xlsx  → unique_links + doc_links
  2. Pull metadata + doc_usage from Master Sheet
  3. Validate against NDB schema
  4. Upsert into MongoDB
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config.settings import (
    MONGO_URI_PROD,
    DB_NAME,
    COLLECTION_KRITIKA,
    CENTRAL_KEYWORDS,
    PROCESSED_NEW,
    OUTPUT_XLSX,
    MASTER_XLSX,
)


# ── Lookup builders ───────────────────────────────────────────────────────────

def build_link_map(output_xlsx: str) -> dict:
    import pandas as pd
    df = pd.read_excel(output_xlsx, sheet_name="Sheet1", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    link_map = {}
    for _, row in df.iterrows():
        primary = str(row.get("primary_link", "")).strip()
        if not primary or primary == "nan":
            continue
        raw_dups = str(row.get("duplicates", "")).strip()
        dup_links = [l.strip() for l in raw_dups.split(",") if l.strip()] if raw_dups and raw_dups != "nan" else []
        doc_links = list(dict.fromkeys([primary] + dup_links))
        entry = {"unique_links": primary, "doc_links": doc_links}
        for link in doc_links:
            link_map[link] = entry
        link_map[primary] = entry
    print(f"  [output.xlsx] {len(link_map)} link mappings loaded")
    return link_map


def build_master_index(master_xlsx: str) -> dict:
    import pandas as pd
    xl     = pd.ExcelFile(master_xlsx)
    sheets = [s for s in xl.sheet_names if s != "Matrix"]
    index  = {}
    for sheet in sheets:
        df = pd.read_excel(master_xlsx, sheet_name=sheet, dtype=str).fillna("")
        df.columns = [c.strip() for c in df.columns]
        for _, row in df.iterrows():
            link = str(row.get("Link", "")).strip()
            if not link or link == "nan":
                continue
            state = next((str(row.get(c, "")).strip() for c in
                          ["In which States it's Used for", "State", "Headquater"]
                          if str(row.get(c, "")).strip() and str(row.get(c, "")).strip() != "nan"), "")
            crop  = next((str(row.get(c, "")).strip() for c in
                          ["In which Crops it's Used for", "Crop"]
                          if str(row.get(c, "")).strip() and str(row.get(c, "")).strip() != "nan"), "")
            org_full = str(row.get("Organization Name, with Location", "")).strip()
            if "," in org_full:
                parts = org_full.rsplit(",", 1)
                org_name, org_loc = parts[0].strip(), parts[1].strip()
            else:
                org_name = org_full
                org_loc  = "New Delhi" if sheet == "Central" else sheet
            verified = str(row.get("Agri Expert name", "")).strip()
            if not verified or verified == "nan":
                verified = "dpt2_batch_process"
            language = str(row.get("Language", "English")).strip() or "English"
            season   = str(row.get("Season",   "All")).strip()     or "All"
            index.setdefault(link, []).append({
                "state": state, "crop": crop, "verified_by": verified,
                "org_name": org_name, "org_location": org_loc,
                "language": language, "season": season, "sheet": sheet,
            })
    total_rows = sum(len(v) for v in index.values())
    print(f"  [master sheet] {total_rows} rows across {len(sheets)} sheets → {len(index)} unique links")
    return index


# ── Schema helpers ────────────────────────────────────────────────────────────

def assign_doc_origin(org_name: str, state_folder: str) -> str:
    if any(kw in org_name.upper() for kw in CENTRAL_KEYWORDS):
        return "central"
    return state_folder or "Unknown"


def build_meta_data(primary_link: str, master_index: dict) -> dict:
    rows = master_index.get(primary_link, [])
    if rows:
        r = rows[0]
        return {"language": r["language"], "organization_name": r["org_name"],
                "organization_location": r["org_location"], "season": r["season"]}
    return {"language": "English", "organization_name": "", "organization_location": "", "season": "All"}


def build_doc_usage(doc_links: list, master_index: dict) -> list:
    seen, result = set(), []
    for link in doc_links:
        rows = master_index.get(link, [])
        if not rows:
            key = ("", "")
            if key not in seen:
                seen.add(key)
                result.append({"doc_link": link, "state": "", "crop": "", "verified_by": "dpt2_batch_process"})
        for r in rows:
            key = (r["state"], r["crop"])
            if key not in seen:
                seen.add(key)
                result.append({"doc_link": link, "state": r["state"],
                               "crop": r["crop"], "verified_by": r["verified_by"]})
    return result


def fix_chunks(chunks: list, doc_id: str) -> list:
    result = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("chunk_content", "")
        result.append({
            "chunk_id":          f"{doc_id}_{i}",
            "associated_doc_id": doc_id,
            "embedding_vector":  chunk.get("embedding_vector", []),
            "chunk_content":     content,
            "page_no":           chunk.get("page_no", 1),
            "_content_hash":     hashlib.sha256(content.encode()).hexdigest(),
        })
    return result


def validate(doc: dict, chunks: list) -> list:
    errors = []
    if not doc.get("unique_links"):            errors.append("unique_links missing")
    if not isinstance(doc.get("doc_links"), list) or not doc["doc_links"]:
                                               errors.append("doc_links empty")
    if not doc.get("doc_origin"):              errors.append("doc_origin missing")
    for i, u in enumerate(doc.get("doc_usage", [])):
        if "doc_link" not in u:                errors.append(f"doc_usage[{i}] missing doc_link")
    for bad in ["format", "agri_expert_name"]:
        if bad in doc.get("meta_data", {}):    errors.append(f"meta_data has forbidden key '{bad}'")
    return errors


def transform(raw: dict, state_folder: str, link_map: dict, master_index: dict):
    doc    = raw.get("document", {})
    chunks = raw.get("chunks", [])
    doc_id = doc.get("doc_id", "")
    raw_link = (doc.get("doc_link") or doc.get("unique_links") or
                doc.get("unique_link") or (doc.get("doc_links") or [""])[0])
    raw_link = str(raw_link).strip()
    if raw_link in link_map:
        resolved     = link_map[raw_link]
        unique_links = resolved["unique_links"]
        doc_links    = resolved["doc_links"]
        link_source  = "output.xlsx ✓"
    else:
        unique_links = raw_link
        doc_links    = [raw_link] if raw_link else []
        link_source  = "fallback (not in output.xlsx)"
    meta_data  = build_meta_data(unique_links, master_index)
    doc_origin = assign_doc_origin(meta_data["organization_name"], state_folder)
    doc_usage  = build_doc_usage(doc_links, master_index)
    new_doc = {
        "doc_id":       doc_id,
        "doc_name":     doc.get("doc_name", ""),
        "app_name":     doc.get("app_name", ""),
        "unique_links": unique_links,
        "doc_links":    doc_links,
        "doc_origin":   doc_origin,
        "meta_data":    meta_data,
        "doc_usage":    doc_usage,
    }
    return {"document": new_doc, "chunks": fix_chunks(chunks, doc_id)}, link_source


# ── Main run ──────────────────────────────────────────────────────────────────

def run(args) -> int:
    base         = Path(args.base_path) if args.base_path else PROCESSED_NEW
    output_xlsx  = args.output_xlsx or str(OUTPUT_XLSX)
    master_xlsx  = args.master_xlsx or str(MASTER_XLSX)
    dry_run      = args.dry_run
    state_filter = getattr(args, "state", None)
    collection   = getattr(args, "collection", COLLECTION_KRITIKA)
    mongo_uri    = getattr(args, "mongo_uri", MONGO_URI_PROD)

    if not base.exists():
        print(f"❌ Base path not found: {base.resolve()}")
        return 1

    print("=" * 65)
    print("Step 2 – NDB Upload")
    print("Loading lookup tables...")
    link_map     = build_link_map(output_xlsx)
    master_index = build_master_index(master_xlsx)
    print()

    all_jsons = sorted(base.rglob("dpt2_result.json"))
    if state_filter:
        all_jsons = [p for p in all_jsons if p.parts[len(base.parts)] == state_filter]

    total = len(all_jsons)
    if total == 0:
        print("No dpt2_result.json files found.")
        return 0

    print(f"{'[DRY RUN] ' if dry_run else ''}Found {total} JSON files\n")

    col = None
    if not dry_run:
        from pymongo import MongoClient
        client = MongoClient(mongo_uri)
        col    = client[DB_NAME][collection]

    ok = inserted = updated = failed = 0
    fail_log, log_lines = [], []

    for idx, json_path in enumerate(all_jsons, 1):
        rel_parts    = json_path.relative_to(base).parts
        state_folder = rel_parts[0] if len(rel_parts) > 1 else "Unknown"
        short_path   = str(json_path.relative_to(base))
        try:
            with open(json_path, encoding="utf-8") as f:
                raw = json.load(f)
            ndb, link_source = transform(raw, state_folder, link_map, master_index)
            doc_id = ndb["document"]["doc_id"]
            errors = validate(ndb["document"], ndb["chunks"])
            if errors:
                raise ValueError(f"Validation failed: {errors}")
            d = ndb["document"]
            detail = (f"[{idx}/{total}] {short_path}\n"
                      f"         doc_id={doc_id} | chunks={len(ndb['chunks'])} | "
                      f"origin={d['doc_origin']} | links={len(d['doc_links'])} | "
                      f"usage_entries={len(d['doc_usage'])} | {link_source}")
            if dry_run:
                print(f"  🔍 DRY  {detail}")
                log_lines.append(f"DRY | {short_path} | {doc_id} | {link_source}")
            else:
                result = col.update_one(
                    {"document.doc_id": doc_id}, {"$set": ndb}, upsert=True)
                action = "INSERT" if result.upserted_id else "UPDATE"
                inserted += bool(result.upserted_id)
                updated  += not bool(result.upserted_id)
                print(f"  ✅ {action}  {detail}")
                log_lines.append(f"{action} | {short_path} | {doc_id} | {link_source}")
            ok += 1
        except Exception as e:
            failed += 1
            err_msg = f"{type(e).__name__}: {e}"
            print(f"  ❌ FAIL  [{idx}/{total}] {short_path}\n           {err_msg}")
            fail_log.append((short_path, err_msg))
            log_lines.append(f"FAIL | {short_path} | {err_msg}")

    print(f"\n{'='*65}")
    if dry_run:
        print(f"DRY RUN: {ok} valid | {failed} would fail | total {total}")
    else:
        print(f"Upload → {DB_NAME}.{collection}")
        print(f"  Inserted: {inserted}  Updated: {updated}  Failed: {failed}  Total: {total}")
        client.close()

    if fail_log:
        print("\nFailed:")
        for path, err in fail_log:
            print(f"  • {path}\n    {err}")

    log_path = base / f"upload_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\nLog → {log_path}")
    return 0 if failed == 0 else 1


def add_args(sub):
    sub.add_argument("--base-path",   default=None,
                     help=f"Root of processed JSON files (default: {PROCESSED_NEW})")
    sub.add_argument("--output-xlsx", default=None)
    sub.add_argument("--master-xlsx", default=None)
    sub.add_argument("--dry-run",     action="store_true",
                     help="Validate and log without writing to MongoDB")
    sub.add_argument("--state",       default=None,
                     help="Only upload one state folder, e.g. Haryana")
    sub.add_argument("--collection",  default=COLLECTION_KRITIKA,
                     help="Target MongoDB collection")
    sub.add_argument("--mongo-uri",   default=MONGO_URI_PROD,
                     help="Override MongoDB connection URI")
