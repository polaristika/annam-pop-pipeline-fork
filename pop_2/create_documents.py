#!/usr/bin/env python3
# create_documents.py
# Step 4: Create one MongoDB document per unique PDF (no chunks yet).
# Reads unique_urls.xlsx + MetadataMaster.xlsx from DATA_DIR.
# Run after the dedup step. Chunks are added later by create_chunks.py.
# Credentials and paths are read from .pop_2_env at project root.

import os
import hashlib
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, ASCENDING


# ── Config defaults (overridden at runtime via .pop_2_env) ────────────────────
MONGO_URI      = ""
DB_NAME        = "new_pdf_chunks_and_metadata"
COLLECTION     = "new_paulose"
DATA_DIR       = "artifacts/phase1_english"
WORKDRIVE_BASE = "https://workdrive.zoho.in/file/"


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
    global MONGO_URI, DB_NAME, COLLECTION, DATA_DIR
    _load_pop2_env()
    MONGO_URI  = os.environ.get("MONGO_URI",       MONGO_URI)
    DB_NAME    = os.environ.get("MONGO_DB",         DB_NAME)
    COLLECTION = os.environ.get("MONGO_COLLECTION", COLLECTION)
    DATA_DIR   = os.environ.get("DATA_DIR",         DATA_DIR)
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI not set — add it to .pop_2_env")


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_pdf_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def parse_org(org_with_location: str):
    if "," in org_with_location:
        name, loc = org_with_location.rsplit(",", 1)
        return name.strip(), loc.strip()
    return org_with_location.strip(), ""


# ── Loaders ───────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_unique_urls():
    path = str(PROJECT_ROOT / "unique_urls.xlsx")
    df = pd.read_excel(path, dtype=str).fillna("")

    print("\n══════════════════════════════════════════")
    print(f"[URL DEBUG] File: {path}")
    print(f"[URL DEBUG] Columns found: {list(df.columns)}")
    print(f"[URL DEBUG] Total rows: {len(df)}")

    for col in ["primary_link", "duplicates"]:
        if col not in df.columns:
            print(f"[URL DEBUG] ⚠️  Column '{col}' NOT FOUND — check exact column name above")

    print(f"\n[URL DEBUG] First 5 rows (raw):")
    print(df[["primary_link", "duplicates"]].head(5).to_string(index=False))
    print("══════════════════════════════════════════\n")

    result = {}
    rows_with_dups = 0

    for _, row in df.iterrows():
        primary  = row["primary_link"].strip()
        doc_id   = row.get("doc_id", "").strip()
        raw_dups = row.get("duplicates", "")
        dups     = [u.strip() for u in raw_dups.split(",") if u.strip()]
        if dups:
            rows_with_dups += 1
        all_links = list(dict.fromkeys([primary] + dups))
        result[primary] = {"doc_id": doc_id, "all_links": all_links}

    print(f"[URL DEBUG] Rows with at least one duplicate: {rows_with_dups} / {len(df)}")
    sample = next(((k, v) for k, v in result.items() if len(v["all_links"]) > 1), None)
    if sample:
        print(f"[URL DEBUG] Sample entry WITH duplicates:")
        print(f"  primary  : {sample[0]}")
        print(f"  all_links: {sample[1]['all_links']}")
    else:
        print("[URL DEBUG] ⚠️  No entry found with more than 1 link")
    print()

    return result


def load_metadata():
    path = str(PROJECT_ROOT / "MetadataMaster.xlsx")
    xl = pd.ExcelFile(path)

    print("\n══════════════════════════════════════════")
    print(f"[META DEBUG] Workbook: {path}")
    print(f"[META DEBUG] All sheets found: {xl.sheet_names}")

    all_rows = []
    for sheet in xl.sheet_names:
        df_sheet = pd.read_excel(xl, sheet_name=sheet, dtype=str).fillna("")
        print(f"\n  Sheet '{sheet}':")
        print(f"    rows      : {len(df_sheet)}")
        print(f"    columns   : {list(df_sheet.columns)}")
        has_link = "Link" in df_sheet.columns
        print(f"    has 'Link': {has_link}")
        if has_link:
            non_empty = df_sheet["Link"].str.strip().ne("").sum()
            print(f"    non-empty Link rows: {non_empty}")
            if non_empty:
                print(f"    sample Link values : {df_sheet['Link'].str.strip().dropna().head(3).tolist()}")
        all_rows.append(df_sheet)

    df = pd.concat(all_rows, ignore_index=True).fillna("")

    if "Link" not in df.columns:
        print("\n  ❌ 'Link' column not found in any sheet!")
        print("══════════════════════════════════════════\n")
        return {}

    result = {
        row["Link"].strip(): row.to_dict()
        for _, row in df.iterrows()
        if row["Link"].strip()
    }

    print(f"\n[META DEBUG] Total metadata rows loaded (all sheets): {len(result)}")
    if result:
        sample_link = next(iter(result))
        sample_meta = result[sample_link]
        print(f"[META DEBUG] Sample link   : {sample_link}")
        print(f"[META DEBUG] Sample fields : {list(sample_meta.keys())}")
        print(f"[META DEBUG] Name of POPs  : {sample_meta.get('Name of POPs', '⚠️  KEY MISSING')}")
        print(f"[META DEBUG] Show Name     : {sample_meta.get('Show Name', '⚠️  KEY MISSING')}")
        print(f"[META DEBUG] Org Name      : {sample_meta.get('Organization Name, with Location', '⚠️  KEY MISSING')}")
        print(f"[META DEBUG] Season        : {sample_meta.get('Season', '⚠️  KEY MISSING')}")
    print("══════════════════════════════════════════\n")

    return result


def debug_cross_match(unique_urls: dict, metadata: dict):
    print("\n══════════════════════════════════════════")
    print("[CROSS-MATCH DEBUG] Checking duplicate links against MetadataMaster keys")
    print(f"  Total metadata keys : {len(metadata)}")

    checked = 0
    for primary, data in unique_urls.items():
        all_links = data["all_links"]
        if len(all_links) <= 1:
            continue
        print(f"\n  Primary: {primary}")
        for link in all_links:
            label = "✓ FOUND" if link in metadata else "❌ MISSING"
            print(f"    {label} → {link}")
        checked += 1
        if checked >= 5:
            break

    all_dup_links   = {l for d in unique_urls.values() for l in d["all_links"][1:]}
    found_in_meta   = sum(1 for l in all_dup_links if l in metadata)
    missing_in_meta = len(all_dup_links) - found_in_meta

    print(f"\n  Total unique duplicate links : {len(all_dup_links)}")
    print(f"  Found in MetadataMaster      : {found_in_meta}")
    print(f"  ❌ MISSING from MetadataMaster: {missing_in_meta}")

    if missing_in_meta:
        print("\n  First 5 missing duplicate links:")
        count = 0
        for l in all_dup_links:
            if l not in metadata:
                print(f"    {l}")
                count += 1
                if count >= 5:
                    break
    print("══════════════════════════════════════════\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    _setup()

    col = MongoClient(MONGO_URI)[DB_NAME][COLLECTION]
    col.create_index([("document.doc_id", ASCENDING)])

    unique_urls = load_unique_urls()
    metadata    = load_metadata()

    debug_cross_match(unique_urls, metadata)

    if args.limit:
        unique_urls = dict(list(unique_urls.items())[:args.limit])
        print(f"[TEST MODE] Limited to {args.limit} documents\n")

    inserted = 0
    updated  = 0
    skipped  = 0

    for primary_link, url_data in unique_urls.items():
        all_links = url_data["all_links"]
        doc_id    = extract_pdf_id_from_url(primary_link)

        primary_meta = metadata.get(primary_link, {})
        if not primary_meta:
            print(f"  [META LOOKUP] ⚠️  No metadata for primary_link: {primary_link}")

        new_doc_usage = []
        new_links = set(all_links)
        seen_usage = set()

        for link in all_links:
            meta = metadata.get(link)
            if not meta:
                continue

            state = meta.get("In which States it's Used for", "").strip()
            crop  = meta.get("Crop", "").strip()
            usage_key = (state.lower(), crop.lower())

            if usage_key in seen_usage:
                continue
            seen_usage.add(usage_key)

            new_doc_usage.append({
                "doc_link":    link,
                "state":       state,
                "crop":        crop,
                "verified_by": meta.get("Agri Expert name", "").strip(),
            })

        existing = col.find_one({"document.doc_id": doc_id})

        if existing:
            existing_links = set(existing["document"]["doc_links"])
            existing_usage = existing["document"]["doc_usage"]

            links_to_add = list(new_links - existing_links)
            usage_to_add = [u for u in new_doc_usage if u not in existing_usage]

            if links_to_add or usage_to_add:
                col.update_one(
                    {"document.doc_id": doc_id},
                    {
                        "$addToSet": {
                            "document.doc_links": {"$each": links_to_add},
                            "document.doc_usage": {"$each": usage_to_add},
                        }
                    },
                )
                print(f"  → Updated  {doc_id}")
                updated += 1
            else:
                print(f"  → Skipped  {doc_id} (no changes)")
                skipped += 1

            continue

        org_raw           = primary_meta.get("Organization Name, with Location", "")
        org_name, org_loc = parse_org(org_raw)

        document_payload = {
            "document": {
                "doc_id":       doc_id,
                "doc_name":     primary_meta.get("Name of POPs", ""),
                "app_name":     primary_meta.get("Show Name", ""),
                "unique_links": primary_link,
                "doc_links":    all_links,
                "doc_origin":   org_raw,
                "meta_data": {
                    "language":              primary_meta.get("Language", ""),
                    "organization_name":     org_name,
                    "organization_location": org_loc,
                    "season":                primary_meta.get("Season", ""),
                },
                "doc_usage": new_doc_usage,
            },
            "chunks": []
        }

        col.insert_one(document_payload)
        print(f"  ✓ Inserted {doc_id}")
        inserted += 1

    print(f"\n✓ Done — inserted: {inserted}, updated: {updated}, skipped: {skipped}")
    print("Run create_chunks.py (or pop-cli ingest-chunks) once .json files are ready.")


if __name__ == "__main__":
    main()
