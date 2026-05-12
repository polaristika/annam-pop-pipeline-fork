#!/usr/bin/env python3
# create_documents.py
# Iterates unique_urls.xlsx (primary_link column) — NOT the data/ folder.
# Creates one document per primary_link with all URLs and metadata.
# Chunks are added later by create_chunks.py once .json files are ready.

import os
import hashlib

import pandas as pd
from pymongo import MongoClient, ASCENDING

# ── Config ─────────────────────────────────────────────────────────────────────
MONGO_URI      = "mongodb+srv://riyamehtaatwork_db_user:riyamehtaatwork_db_user@ajrasakha.1af8ryy.mongodb.net/?appName=ajrasakha" #test in this db, change for prod
DB_NAME        = "new_pdf_chunks_and_metadata"
COLLECTION     = "new_paulose_1"
DATA_DIR       = "../artifacts/phase1_english"
WORKDRIVE_BASE = "https://workdrive.zoho.in/file/"

# ── Helpers ────────────────────────────────────────────────────────────────────
def extract_pdf_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]

def parse_org(org_with_location: str):
    if "," in org_with_location:
        name, loc = org_with_location.rsplit(",", 1)
        return name.strip(), loc.strip()
    return org_with_location.strip(), ""

# ── Loaders ────────────────────────────────────────────────────────────────────
def load_unique_urls():
    path = os.path.join(DATA_DIR, "unique_urls.xlsx")
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
    path = os.path.join(DATA_DIR, "MetadataMaster.xlsx")
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

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    col = MongoClient(MONGO_URI)[DB_NAME][COLLECTION]
    col.create_index([("document.doc_id", ASCENDING)])

    unique_urls = load_unique_urls()
    metadata    = load_metadata()

    debug_cross_match(unique_urls, metadata)

    inserted = 0
    updated  = 0
    skipped  = 0

    # ── Iterate unique_urls.xlsx rows, not data/ folders ───────────────────
    for primary_link, url_data in unique_urls.items():
        all_links = url_data["all_links"]
        doc_id    = extract_pdf_id_from_url(primary_link)

        primary_meta = metadata.get(primary_link, {})
        if not primary_meta:
            print(f"  [META LOOKUP] ⚠️  No metadata for primary_link: {primary_link}")

        # ── BUILD DOC_USAGE from all links ──────────────────────────────────
        # new_doc_usage = []
        # new_links     = set(all_links)

        # for link in all_links:
        #     meta = metadata.get(link)
        #     if not meta:
        #         continue
        #     new_doc_usage.append({
        #         "doc_link":    link,
        #         "state":       meta.get("In which States it's Used for", "").strip(),
        #         "crop":        meta.get("Crop", "").strip(),
        #         "verified_by": meta.get("Agri Expert name", "").strip(),
        #     })
        new_doc_usage = []
        new_links = set(all_links)

        seen_state_crop = set()

        for link in all_links:
            meta = metadata.get(link)
            if not meta:
                continue

            state = meta.get(
                "In which States it's Used for",
                ""
            ).strip()

            crop = meta.get(
                "Crop",
                ""
            ).strip()

            usage_key = (state, crop)

            # skip duplicate state+crop combos
            if usage_key in seen_state_crop:
                continue

            seen_state_crop.add(usage_key)

            new_doc_usage.append({
                "doc_link": link,          # first link representing this combo
                "state": state,
                "crop": crop,
                "verified_by": meta.get(
                    "Agri Expert name",
                    ""
                ).strip(),
            })

        # ── CHECK IF DOC EXISTS ─────────────────────────────────────────────
        existing = col.find_one({"document.doc_id": doc_id})

        # ── CASE 1: EXISTS → UPDATE links + usage only ──────────────────────
        if existing:
            existing_links = set(existing["document"]["doc_links"])
            existing_usage = existing["document"]["doc_usage"]

            links_to_add = list(new_links - existing_links)
            # usage_to_add = [u for u in new_doc_usage if u not in existing_usage]
            # dedupe only on (state, crop)
            existing_state_crop = {
                (
                    u.get("state","").strip(),
                    u.get("crop","").strip()
                )
                for u in existing_usage
            }

            usage_to_add = [
                u for u in new_doc_usage
                if (
                    u.get("state","").strip(),
                    u.get("crop","").strip()
                ) not in existing_state_crop
            ]

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

        # ── CASE 2: NEW → INSERT document (no chunks yet) ───────────────────
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
            "chunks": []  # populated later by create_chunks.py
        }

        col.insert_one(document_payload)
        print(f"  ✓ Inserted {doc_id}")
        inserted += 1

    print(f"\n✓ Done — inserted: {inserted}, updated: {updated}, skipped: {skipped}")
    print("Run create_chunks.py once .md/.json files are ready.")

if __name__ == "__main__":
    main()