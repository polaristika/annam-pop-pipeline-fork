"""
Migration script: Update ALL existing documents in MongoDB collection
to strictly follow the new NDB schema.

OLD schema issues found in DB:
  ❌ unique_link (singular) → must be unique_links (plural)
  ❌ doc_usage entries missing doc_link field
  ❌ meta_data still has `format` and `agri_expert_name` (not in NDB spec)
  ❌ chunk_id uses random hash instead of doc_id_index format
  ❌ _content_hash missing from chunks

NEW schema (strictly enforced):
  ✅ unique_links (plural, string)
  ✅ doc_links (list)
  ✅ doc_origin (correctly assigned)
  ✅ meta_data: only language, organization_name, organization_location, season
  ✅ doc_usage[]: each entry has doc_link, state, crop, verified_by
  ✅ chunk_id: doc_id_index
  ✅ _content_hash: sha256 of chunk_content
"""

import hashlib
from pymongo import MongoClient

MONGO_URI = (
    "mongodb+srv://riyamehtaatwork_db_user:riyamehtaatwork_db_user"
    "@ajrasakha.1af8ryy.mongodb.net/?appName=ajrasakha"
)
DB_NAME         = "new_pdf_chunks_and_metadata"
COLLECTION_NAME = "New_Kritika"   # ← change if needed

# Central-org keywords for doc_origin assignment
CENTRAL_KEYWORDS = ["ICAR", "GOI", "CENTRAL", "NATIONAL", "IFFCO", "INDIAN FARMERS"]


def assign_doc_origin(doc: dict) -> str:
    """
    Rule:
      - State-level document → state name
      - Central institute (ICAR, IFFCO, GOI etc.) → "central"
      - University / regional org → organization_location state
    """
    org = doc.get("meta_data", {}).get("organization_name", "").upper()
    if any(kw in org for kw in CENTRAL_KEYWORDS):
        return "central"

    # If doc_origin already looks like a proper state name (not a URL or org name), keep it
    existing = doc.get("doc_origin", "")
    if existing and len(existing) < 50 and "http" not in existing and "," not in existing:
        return existing

    # Fallback: use organization_location
    loc = doc.get("meta_data", {}).get("organization_location", "")
    # Strip city prefix (e.g. "Guntur, Andhra Pradesh" → "Andhra Pradesh")
    if "," in loc:
        return loc.split(",")[-1].strip()
    return loc or "Unknown"


def clean_meta_data(meta: dict) -> dict:
    """Keep only NDB-spec fields."""
    return {
        "language":              meta.get("language", "English"),
        "organization_name":     meta.get("organization_name", ""),
        "organization_location": meta.get("organization_location", ""),
        "season":                meta.get("season", "All"),
    }


def get_primary_link(doc: dict) -> str:
    """Extract primary link regardless of old/new field name."""
    # New schema
    if doc.get("unique_links"):
        return doc["unique_links"]
    # Old schema (singular)
    if doc.get("unique_link"):
        return doc["unique_link"]
    # Fallback: first entry of doc_links
    links = doc.get("doc_links", [])
    if links:
        return links[0]
    return ""


def fix_doc_usage(doc_usage: list, primary_link: str, meta: dict) -> list:
    """
    Ensure every doc_usage entry has: doc_link, state, crop, verified_by
    """
    verified_by_fallback = meta.get("agri_expert_name", "dpt2_batch_process")
    fixed = []
    for entry in doc_usage:
        fixed.append({
            "doc_link":    entry.get("doc_link", primary_link),
            "state":       entry.get("state", ""),
            "crop":        entry.get("crop", ""),
            "verified_by": entry.get("verified_by", verified_by_fallback),
        })
    return fixed


def fix_chunks(chunks: list, doc_id: str) -> list:
    """
    Re-index chunks:
      - chunk_id = doc_id_index
      - associated_doc_id = doc_id
      - _content_hash = sha256(chunk_content)
    """
    fixed = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("chunk_content", "")
        fixed.append({
            "chunk_id":          f"{doc_id}_{i}",
            "associated_doc_id": doc_id,
            "embedding_vector":  chunk.get("embedding_vector", []),
            "chunk_content":     content,
            "page_no":           chunk.get("page_no", 1),
            "_content_hash":     hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })
    return fixed


def validate(new_doc: dict, new_chunks: list) -> list[str]:
    errors = []
    d = new_doc
    if not d.get("unique_links"):
        errors.append("unique_links missing")
    if not isinstance(d.get("doc_links"), list):
        errors.append("doc_links must be a list")
    if not d.get("doc_origin"):
        errors.append("doc_origin missing")
    for i, u in enumerate(d.get("doc_usage", [])):
        if "doc_link" not in u:
            errors.append(f"doc_usage[{i}] missing doc_link")
        if "verified_by" not in u:
            errors.append(f"doc_usage[{i}] missing verified_by")
    for i, c in enumerate(new_chunks):
        if not c.get("chunk_id", "").startswith(d["doc_id"]):
            errors.append(f"chunk[{i}] bad chunk_id format")
        if "_content_hash" not in c:
            errors.append(f"chunk[{i}] missing _content_hash")
    # meta_data must NOT have format or agri_expert_name
    meta = d.get("meta_data", {})
    if "format" in meta:
        errors.append("meta_data still has 'format'")
    if "agri_expert_name" in meta:
        errors.append("meta_data still has 'agri_expert_name'")
    return errors


def migrate():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    col = db[COLLECTION_NAME]

    total = col.count_documents({})
    print(f"Found {total} documents in '{COLLECTION_NAME}'. Starting migration...\n")

    updated = 0
    skipped = 0
    failed  = 0

    for record in col.find({}):
        mongo_id = record["_id"]
        old_doc  = record.get("document", {})
        old_chunks = record.get("chunks", [])
        doc_id   = old_doc.get("doc_id", str(mongo_id))

        try:
            primary_link = get_primary_link(old_doc)
            old_meta     = old_doc.get("meta_data", {})

            new_doc = {
                "doc_id":       doc_id,
                "doc_name":     old_doc.get("doc_name", ""),
                "app_name":     old_doc.get("app_name", ""),
                "unique_links": primary_link,
                "doc_links":    old_doc.get("doc_links", [primary_link]),
                "doc_origin":   assign_doc_origin(old_doc),
                "meta_data":    clean_meta_data(old_meta),
                "doc_usage":    fix_doc_usage(
                                    old_doc.get("doc_usage", []),
                                    primary_link,
                                    old_meta
                                ),
            }

            new_chunks = fix_chunks(old_chunks, doc_id)

            errors = validate(new_doc, new_chunks)
            if errors:
                print(f"  ❌ SKIP  {doc_id}: {errors}")
                failed += 1
                continue

            col.update_one(
                {"_id": mongo_id},
                {"$set": {
                    "document": new_doc,
                    "chunks":   new_chunks,
                }}
            )
            print(f"  ✅ OK    {doc_id} | chunks: {len(new_chunks)} | origin: {new_doc['doc_origin']}")
            updated += 1

        except Exception as e:
            print(f"  ❌ ERROR {doc_id}: {e}")
            failed += 1

    client.close()
    print(f"\n{'='*55}")
    print(f"Migration complete: {updated} updated | {skipped} skipped | {failed} failed")
    print(f"{'='*55}")


if __name__ == "__main__":
    migrate()