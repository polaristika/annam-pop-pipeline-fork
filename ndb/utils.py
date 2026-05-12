"""
ndb/utils.py  –  Utility operations for MongoDB collections

Utilities:
  cleanup-paulose   Remove chunk-mapping audit fields from new_paulose_1
                    (chunks_mapped_at, chunks_source, chunk_count)
  upload-single     Normalize and upload a single dpt2_result.json to MongoDB
  verify            Check one document in DB by doc_id
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config.settings import (
    MONGO_URI_PROD,
    DB_NAME,
    COLLECTION_PAULOSE,
    COLLECTION_KRITIKA,
    OUTPUT_XLSX,
    MASTER_XLSX,
    CENTRAL_KEYWORDS,
)


# ── cleanup-paulose ───────────────────────────────────────────────────────────

def run_cleanup_paulose(args) -> int:
    """
    Strip the three chunk-mapping audit fields added by step3 from new_paulose_1.
    Useful when you want to re-run step3 cleanly from scratch.

    Originally: rem.py
    """
    from pymongo import MongoClient

    mongo_uri  = getattr(args, "mongo_uri", MONGO_URI_PROD)
    collection = getattr(args, "collection", COLLECTION_PAULOSE)
    dry_run    = getattr(args, "dry_run", False)

    client = MongoClient(mongo_uri)
    col    = client[DB_NAME][collection]

    filter_q = {"$or": [
        {"chunks_mapped_at": {"$exists": True}},
        {"chunks_source":    {"$exists": True}},
        {"chunk_count":      {"$exists": True}},
    ]}

    matched = col.count_documents(filter_q)
    print(f"Documents with audit fields: {matched}")

    if dry_run:
        print(f"[DRY RUN] Would remove audit fields from {matched} docs.")
        client.close()
        return 0

    result = col.update_many(
        filter_q,
        {"$unset": {
            "chunks_mapped_at": "",
            "chunks_source":    "",
            "chunk_count":      "",
        }},
    )
    print(f"✅ Matched: {result.matched_count}  |  Modified: {result.modified_count}")
    client.close()
    return 0


def add_args_cleanup_paulose(sub):
    sub.add_argument("--collection", default=COLLECTION_PAULOSE,
                     help="Collection to clean (default: new_paulose_1)")
    sub.add_argument("--mongo-uri",  default=MONGO_URI_PROD)
    sub.add_argument("--dry-run",    action="store_true",
                     help="Show count without modifying")


# ── upload-single ─────────────────────────────────────────────────────────────

def run_upload_single(args) -> int:
    """
    Normalize and upload a single dpt2_result.json to MongoDB.

    Resolves links from output.xlsx, pulls metadata from Master Sheet,
    then upserts into the target collection.

    Originally: upload_normalized_json.py  +  test.py
    """
    import hashlib
    import pandas as pd
    from pymongo import MongoClient

    json_path    = Path(args.json_path)
    output_xlsx  = args.output_xlsx or str(OUTPUT_XLSX)
    master_xlsx  = args.master_xlsx or str(MASTER_XLSX)
    mongo_uri    = getattr(args, "mongo_uri", MONGO_URI_PROD)
    collection   = getattr(args, "collection", COLLECTION_KRITIKA)
    dry_run      = getattr(args, "dry_run", False)
    save_norm    = getattr(args, "save_normalized", False)

    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        return 1

    print(f"Loading: {json_path}")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    doc    = data.get("document", {})
    chunks = data.get("chunks", [])
    doc_id = doc.get("doc_id", "")

    if not doc_id:
        print("❌ doc_id missing from document – cannot proceed.")
        return 1

    # ── Resolve links from output.xlsx ────────────────────────────────────────
    print("Loading output.xlsx...")
    out_df = pd.read_excel(output_xlsx, sheet_name="Sheet1", dtype=str)
    out_df.columns = [c.strip() for c in out_df.columns]

    # Match by primary_link or by the existing link field in the JSON
    raw_link = (doc.get("doc_link") or doc.get("unique_links") or
                doc.get("unique_link") or (doc.get("doc_links") or [""])[0] or "").strip()

    match = out_df[out_df["primary_link"].str.strip() == raw_link]
    if match.empty:
        # Try looking in duplicates column
        match = out_df[out_df["duplicates"].str.contains(raw_link, na=False, regex=False)]

    if not match.empty:
        row          = match.iloc[0]
        primary_link = str(row["primary_link"]).strip()
        raw_dups     = str(row.get("duplicates", "")).strip()
        dup_links    = [l.strip() for l in raw_dups.split(",") if l.strip()] if raw_dups and raw_dups != "nan" else []
        doc_links    = list(dict.fromkeys([primary_link] + dup_links))
        print(f"  Link resolved via output.xlsx ✓  ({len(doc_links)} doc_links)")
    else:
        primary_link = raw_link
        doc_links    = [raw_link] if raw_link else []
        print(f"  Link not in output.xlsx – using as-is")

    # ── Pull metadata from Master Sheet ───────────────────────────────────────
    print("Loading Master Sheet...")
    xl     = pd.ExcelFile(master_xlsx)
    sheets = [s for s in xl.sheet_names if s != "Matrix"]
    meta_data  = {"language": "English", "organization_name": "", "organization_location": "", "season": "All"}
    doc_usage  = []
    seen_pairs = set()

    for sheet in sheets:
        df = pd.read_excel(master_xlsx, sheet_name=sheet, dtype=str).fillna("")
        df.columns = [c.strip() for c in df.columns]
        for _, r in df.iterrows():
            link = str(r.get("Link", "")).strip()
            if link not in doc_links:
                continue
            # Populate meta_data from the first matching row
            if not meta_data["organization_name"]:
                org_full = str(r.get("Organization Name, with Location", "")).strip()
                if "," in org_full:
                    parts = org_full.rsplit(",", 1)
                    org_name, org_loc = parts[0].strip(), parts[1].strip()
                else:
                    org_name = org_full
                    org_loc  = "New Delhi" if sheet == "Central" else sheet
                meta_data = {
                    "language":              str(r.get("Language", "English")).strip() or "English",
                    "organization_name":     org_name,
                    "organization_location": org_loc,
                    "season":                str(r.get("Season", "All")).strip() or "All",
                }
            state    = next((str(r.get(c, "")).strip() for c in
                             ["In which States it's Used for", "State", "Headquater"]
                             if str(r.get(c, "")).strip()), "")
            crop     = next((str(r.get(c, "")).strip() for c in
                             ["In which Crops it's Used for", "Crop"]
                             if str(r.get(c, "")).strip()), "")
            verified = str(r.get("Agri Expert name", "")).strip() or "dpt2_batch_process"
            key = (state, crop)
            if key not in seen_pairs:
                seen_pairs.add(key)
                doc_usage.append({"doc_link": link, "state": state,
                                  "crop": crop, "verified_by": verified})

    if not doc_usage:
        doc_usage = [{"doc_link": primary_link, "state": "", "crop": "", "verified_by": "dpt2_batch_process"}]

    # ── Assign doc_origin ─────────────────────────────────────────────────────
    org_upper  = meta_data["organization_name"].upper()
    state_folder = json_path.parts[-3] if len(json_path.parts) >= 3 else ""
    doc_origin = "central" if any(kw in org_upper for kw in CENTRAL_KEYWORDS) else (state_folder or "Unknown")

    # ── Build clean document ──────────────────────────────────────────────────
    new_doc = {
        "doc_id":       doc_id,
        "doc_name":     doc.get("doc_name", ""),
        "app_name":     doc.get("app_name", ""),
        "unique_links": primary_link,
        "doc_links":    doc_links,
        "doc_origin":   doc_origin,
        "meta_data":    meta_data,
        "doc_usage":    doc_usage,
    }

    # ── Fix chunks ────────────────────────────────────────────────────────────
    new_chunks = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("chunk_content", "")
        new_chunks.append({
            "chunk_id":          f"{doc_id}_{i}",
            "associated_doc_id": doc_id,
            "embedding_vector":  chunk.get("embedding_vector", []),
            "chunk_content":     content,
            "page_no":           chunk.get("page_no", 1),
            "_content_hash":     hashlib.sha256(content.encode()).hexdigest(),
        })

    ndb_doc = {"document": new_doc, "chunks": new_chunks}

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  doc_id        : {doc_id}")
    print(f"  unique_links  : {primary_link}")
    print(f"  doc_links     : {len(doc_links)} links")
    print(f"  doc_origin    : {doc_origin}")
    print(f"  doc_usage     : {len(doc_usage)} entries")
    print(f"  chunks        : {len(new_chunks)}")

    # ── Optionally save normalized JSON next to original ──────────────────────
    if save_norm:
        norm_path = json_path.parent / "dpt2_result.normalized.json"
        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(ndb_doc, f, ensure_ascii=False, indent=2)
        print(f"\n  Normalized JSON saved → {norm_path}")

    if dry_run:
        print("\n[DRY RUN] No changes written to MongoDB.")
        return 0

    # ── Upsert ────────────────────────────────────────────────────────────────
    print(f"\nUploading to {DB_NAME}.{collection} ...")
    client = MongoClient(mongo_uri)
    col    = client[DB_NAME][collection]
    result = col.update_one(
        {"document.doc_id": doc_id},
        {"$set": ndb_doc},
        upsert=True,
    )
    if result.upserted_id:
        print(f"✅ Inserted – MongoDB _id: {result.upserted_id}")
    elif result.modified_count:
        print(f"✅ Updated existing document (doc_id: {doc_id})")
    else:
        print("⚠️  No changes made (document already up to date).")

    # ── Verify ────────────────────────────────────────────────────────────────
    found = col.find_one({"document.doc_id": doc_id}, {"document.doc_id": 1})
    print(f"   Verified in DB: {found is not None}")

    client.close()
    return 0


def add_args_upload_single(sub):
    sub.add_argument("json_path",
                     help="Path to a single dpt2_result.json file")
    sub.add_argument("--output-xlsx",     default=None)
    sub.add_argument("--master-xlsx",     default=None)
    sub.add_argument("--collection",      default=COLLECTION_KRITIKA)
    sub.add_argument("--mongo-uri",       default=MONGO_URI_PROD)
    sub.add_argument("--dry-run",         action="store_true",
                     help="Validate and print without writing to MongoDB")
    sub.add_argument("--save-normalized", action="store_true",
                     help="Save dpt2_result.normalized.json alongside the source")


# ── verify ────────────────────────────────────────────────────────────────────

def run_verify(args) -> int:
    """Quick DB lookup by doc_id to confirm a document was uploaded."""
    from pymongo import MongoClient

    mongo_uri  = getattr(args, "mongo_uri", MONGO_URI_PROD)
    collection = getattr(args, "collection", COLLECTION_KRITIKA)
    doc_id     = args.doc_id

    client = MongoClient(mongo_uri)
    col    = client[DB_NAME][collection]
    found  = col.find_one({"document.doc_id": doc_id})
    client.close()

    if found:
        d = found.get("document", {})
        print(f"✅ Found in {collection}")
        print(f"   doc_id       : {d.get('doc_id')}")
        print(f"   doc_name     : {d.get('doc_name')}")
        print(f"   unique_links : {d.get('unique_links')}")
        print(f"   doc_origin   : {d.get('doc_origin')}")
        print(f"   chunks       : {len(found.get('chunks', []))}")
        return 0
    else:
        print(f"❌ doc_id '{doc_id}' not found in {collection}")
        return 1


def add_args_verify(sub):
    sub.add_argument("doc_id",
                     help="doc_id to look up in MongoDB")
    sub.add_argument("--collection", default=COLLECTION_KRITIKA)
    sub.add_argument("--mongo-uri",  default=MONGO_URI_PROD)
