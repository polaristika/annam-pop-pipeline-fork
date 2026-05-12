# Work Done — POP Pipeline

> **Scope:** All scripts and files in the project root and `process_english_files/`.  
> **Date documented:** 2026-04-28

---

## High-Level Overview

```
Zoho WorkDrive / Sheet
        │
        ▼
[1] Download & Deduplicate PDFs
        │
        ▼
[2] PDF Inventory + Classification  (pop_cli.py)
        │
        ▼
[3] Phase 1 Extraction  →  artifacts/phase1_english/<hash>/
        │
        ▼
[4] Ingest to MongoDB  (process_english_files/)
        │
        ├── create_documents → metadata records
        └── create_chunks   → embeddings
```

---

## 1. Zoho Authentication

| File | What it does |
|---|---|
| `zoho_token_exchange.py` | One-time script: exchanges an OAuth auth code for `access_token` + `refresh_token`, saves to `zoho_tokens.json` |
| `zoho_tokens.json` | Stores live Zoho credentials (gitignored) |
| `ZOHO_SETUP.md` | Step-by-step guide to obtain Zoho API credentials and run the token exchange |

**Flow:**

```
Zoho API Console
  → generate auth code (10-min TTL)
  → run zoho_token_exchange.py
  → zoho_tokens.json written
```

All downstream scripts load `zoho_tokens.json` at startup and auto-refresh the token on 401 responses.

---

## 2. PDF Download from Zoho

### `zoho_pdf_downloader.py`
- Reads all state sheets from the Zoho workbook (skips `Matrix` sheet)
- Downloads every PDF link found to `data/raw/POP Bank/{State}/`
- 8 parallel download threads, retries on 429/500/502/503
- Skips files that already exist locally

### `zoho_pdf_download_v2.py`
- Targeted download: only fetches PDFs whose `primary_link` appears in a given `output.xlsx`
- Same 8-thread, retry, skip-existing behaviour
- Used after deduplication to avoid re-downloading known duplicates

---

## 3. Deduplication — Finding Unique Links

### `extract_unique_link.py`
Purpose: scan all Zoho sheet rows, download each file, detect duplicates by perceptual hash, and produce a deduplicated link list.

**Steps:**

```
Zoho Sheet API → all links
        │
        ▼ per link:
    Download file (PDF / image / document)
        │
        ├── PDF   → render first 3 pages → pHash
        ├── image → pHash
        └── doc   → MD5
        │
        ▼ compare hash against hash_db
        │
        ├── match found → add link to existing entry's duplicates
        └── no match    → new primary entry
        │
        ▼ every 100 links
    Save checkpoint to output.csv
        │
        ▼ final
    output.csv + unique_urls.xlsx (no hash columns)
```

- Resumable: re-loads `output.csv` on restart and skips already-seen links
- Stops if 50 consecutive downloads fail (token expiry guard)
- Hash threshold = 10 perceptual-hash distance units

**Outputs:**
- `output.csv` — checkpoint with `doc_id, primary_link, duplicates, hash_value, ftype`
- `unique_urls.xlsx` — clean export with `doc_id, primary_link, duplicates`

---

### `extract_unique_link_db.py` + `extract_unique_link_db.sh`
Purpose: MongoDB-backed version that reconciles links found in the live `answers` collection against `output.csv`.

**Modes (`--mode`):**

| Mode | Action |
|---|---|
| `process` | Iterates all docs in `answers`, checks each source URL |
| `reflag` | Re-processes all `flag:true` entries in `unique_links` |
| `all` | Runs reflag pass first, then main loop |

**Per-URL resolution logic (process mode):**

```
Source URL
    │
    ├── Found in output.csv as primary   → upsert to unique_links (no flag)
    ├── Found in output.csv as duplicate → upsert primary to unique_links
    ├── Zoho URL, not in output.csv      → download + hash
    │       ├── hash matches existing    → upsert matched primary
    │       ├── hash is new              → add to output.csv + unique_links
    │       └── not downloadable         → write with flag=true
    └── Non-Zoho URL                     → write with flag=true
```

**Reflag pass:** re-processes all `flag:true` entries in `unique_links` using the same resolution logic; updates `output.csv` if any new uniques are found.

**Run via:**
```bash
bash extract_unique_link_db.sh
# (MODE=process by default in the shell script)
```

**Results (from `summary.md`):**

| Metric | Count |
|---|---|
| Total sources processed | 24,100 |
| MongoDB docs scanned | 12,653 |
| Unique docs in output.csv | 4,136 |
| Found as primary | 19,291 |
| Found as duplicate | 3,846 |
| Non-Zoho (flagged) | 369 |
| Not downloadable (skipped) | 594 |

---

### `migrate_collection.sh`
- `mongodump` from production cluster (`agri_ai.answers`)
- `mongorestore` to target cluster (`ans_source_audit_db.answers`)
- Used to bring production data into the audit/dev environment

---

## 4. Audit / Investigation Scripts (temp files)

These were written to investigate which flagged links were actually being used in live answers.

### `temp.py`
- Loads all `flag:true` entries from `unique_links` collection
- Scans every doc in `answers`, extracts source URLs
- Writes distinct flagged links that appear in answers → `temp.csv`

### `temp2.py`
- Input: `temp3(1).csv` (flagged links list)
- Checks `output.csv` to see if each link is already a known primary
- Tests actual accessibility of each Zoho URL via HEAD-style download
- Outputs `temp2.csv` with columns: `source_name, link, in_output, accessible`

### `temp3.py`
- Input: `temp_deduped(1).csv`
- For each flagged link, finds the `answers` document that references it
- Fetches the corresponding `questions` document (cached per question ID)
- Outputs `temp3.csv` with: `source_name, link, answer_id, question_id, question, answer`

**Intermediate CSVs** (`temp.csv`, `temp_deduped.csv`, `temp3.csv`, `temp3(1).csv`, `temp2.csv`, etc.) are working files from this audit chain and are not tracked in git.

---

## 5. Main PDF Processing Pipeline (`pop_cli.py`)

Entry point for all PDF classification and extraction work. See `CLAUDE.md` for full detail.

```
pop_cli.py inventory --scan
    → scans data/raw/POP Bank/, classifies each PDF
    → writes pdf_inventory.csv (15 columns)

pop_cli.py process --phase 1 --count N
    → processes English PDFs via Docling
    → outputs artifacts/phase1_english/<md5_hash>/

pop_cli.py batch --phase 2 --all
    → processes Indic PDFs via EasyOCR + VLM + IndicTrans
```

`pdf_inventory.csv` is the master index with fields including `lang_guess`, `lang_conf`, `garbled_detected`, `phase`, and `status`.

---

## 6. Ingest to MongoDB — `process_english_files/`

Two-step pipeline to take Phase 1 extraction outputs and load them into MongoDB as searchable vector chunks.

### Overall Flow

```
artifacts/phase1_english/
  └── <state>/<folder>-<pdf_id>/
        ├── <folder>_output.json   ← preferred
        └── <folder>_document.md

unique_urls.xlsx   ←─ deduplication output (primary_link, duplicates, doc_id)
MetadataMaster.xlsx ←─ POP metadata (multi-sheet, keyed on Link column)

        │
        ▼ Step 1
new_create_document.py
        │  reads unique_urls.xlsx + MetadataMaster.xlsx
        │  for each primary_link → inserts/updates doc in MongoDB
        │
        ▼ Step 2
new_create_chunks.py
        │  iterates artifact folders
        │  parses JSON (flat or Docling tree format)
        │  sliding-window chunks (500 words, 100 overlap)
        │  embeds with BAAI/bge-large-en (1024-dim)
        │  writes chunks array to existing MongoDB doc
        ▼
MongoDB: new_pdf_chunks_and_metadata.new_paulose_1
```

---

### Script Versions

There are two generations of scripts:

| Script | Collection | Key difference |
|---|---|---|
| `create_documents.py` (v1) | `new_paulose` | Original; adds all usage entries without dedup |
| `create_chunks.py` (v1) | `new_paulose` | Chunks nested under `{"chunk": {...}}` |
| `new_create_document.py` (v2) | `new_paulose_1` | Deduplicates `doc_usage` entries on `(state, crop)` |
| `new_create_chunks.py` (v2) | `new_paulose_1` | Chunks stored flat (no `"chunk"` wrapper key) |

v2 scripts are what `scheduler.py` runs.

---

### `new_create_document.py` (v2)

1. Reads `unique_urls.xlsx` → `{primary_link: {doc_id, all_links}}`
2. Reads all sheets of `MetadataMaster.xlsx`, concatenates, keys on `Link` column
3. Runs a cross-match debug report
4. For each primary link:
   - Builds `doc_usage` entries from all duplicate links, **deduplicating on `(state, crop)` pairs**
   - If doc exists in MongoDB → `$addToSet` new links and usage entries
   - If new → inserts full document record with empty `chunks: []`

**MongoDB document structure:**
```json
{
  "document": {
    "doc_id": "<pdf_id from Zoho URL>",
    "doc_name": "Name of POPs",
    "app_name": "Show Name",
    "unique_links": "<primary URL>",
    "doc_links": ["<primary>", "<dup1>", ...],
    "doc_origin": "Org Name, Location",
    "meta_data": { "language", "organization_name", "organization_location", "season" },
    "doc_usage": [{ "doc_link", "state", "crop", "verified_by" }]
  },
  "chunks": []
}
```

---

### `new_create_chunks.py` (v2)

1. Loads `unique_urls.xlsx` (for primary_link → doc_id mapping)
2. Iterates every subdirectory under `DATA_DIR`
3. Derives `pdf_id` from the last `-`-delimited folder segment
4. Constructs `primary_link = WORKDRIVE_BASE + pdf_id` and checks it's in `unique_urls.xlsx`
5. Checks the MongoDB doc exists; skips if chunks already present
6. Resolves JSON file (`<folder>_output.json` preferred, `<folder>.json` fallback)
7. Parses JSON — supports two formats:

```
Flat format (NHB/newsletter):
  data.content[].type  in (text, heading, image)

Docling tree format:
  data.body.children[] → recursive $ref resolution
  skips nodes with content_layer == "furniture"
```

8. Sliding-window chunking: 500 words, 100-word overlap, page number = most common page in window
9. Embeds all chunks with `BAAI/bge-large-en` (GPU if available), batch size 64, L2-normalized
10. Writes chunks to MongoDB with `$set`

**Chunk structure (v2 — flat, no wrapper):**
```json
{
  "chunk_id": "<doc_id>_<index>",
  "associated_doc_id": "<doc_id>",
  "embedding_vector": [1024 floats],
  "chunk_content": "...",
  "page_no": 3,
  "_content_hash": "<sha256>"
}
```

---

### `scheduler.py`

Runs `new_create_document.py` → `new_create_chunks.py` every 10 minutes.

- Runs immediately on start
- Aborts the run if either script exits non-zero
- Logs to both `pipeline.log` and stdout
- Uses the local `venv/bin/python`

**Pipeline ran continuously on 2026-04-24** (visible in `pipeline.log`): first with v1 scripts, then switched to v2 after a naming correction (`new_create_documents.py` → `new_create_document.py`).

---

## 7. Urgent — Golden Dataset Extraction (`urgent/`)

Three scripts for extracting sample data from production MongoDB for evaluation/testing. All read `MONGO_URI` from `urgent/.envurgent`.

| Script | Source collection | Output | What it extracts |
|---|---|---|---|
| `extract_agri_pairs.py` | `agriai.answers` + `agriai.questions` | `agri_qa_pairs.csv` | 200 random answers joined with their question docs |
| `extract_golden_agri_qa.py` | `golden_db.agri_qa` | `golden_agri_qa.csv` | 200 random docs from the golden agri Q&A collection |
| `extract_golden_pop.py` | `golden_db.pop` | `golden_pop.csv` | 200 random docs from the golden POP collection |

All three use `$sample` aggregation (random), exclude `embedding` fields, flatten `metadata` sub-objects, and write to CSV.

---

## 8. Testing — Question Extraction (`testing/`)

| File | Purpose |
|---|---|
| `Ajrasakha Testing - GDB (reviewer).csv` | Full reviewer test dataset (~2.7 MB) |
| `extract_paulose_questions.py` | Filters first 50 rows for `Tester == "Paulose"`, formats as `"<question> for <State>, <District>"` → `output.csv` |
| `output.csv` | Output of above (Paulose's questions with location context) |

---

## Key Data Files (not in git)

| File | Description |
|---|---|
| `data/raw/POP Bank/` | Source PDFs (~565, organized by state) |
| `artifacts/phase1_english/` | Phase 1 extraction outputs (JSON + Markdown per doc) |
| `pdf_inventory.csv` | Master PDF index (generated by `pop_cli.py inventory --scan`) |
| `output.csv` | Deduplicated link list (4136 unique docs) |
| `unique_urls.xlsx` | Clean export of deduplication output |
| `MetadataMaster.xlsx` | POP metadata workbook (multi-sheet) |
| `zoho_tokens.json` | Zoho OAuth tokens (gitignored) |

---

## MongoDB Collections Referenced

| Cluster | DB | Collection | Written by |
|---|---|---|---|
| `cluster-rkp` | `ans_source_audit_db` | `answers` | Migrated from prod via `migrate_collection.sh` |
| `cluster-rkp` | `ans_source_audit_db` | `unique_links` | `extract_unique_link_db.py` |
| `ajrasakha` | `new_pdf_chunks_and_metadata` | `new_paulose` | v1 ingest scripts |
| `ajrasakha` | `new_pdf_chunks_and_metadata` | `new_paulose_1` | v2 ingest scripts (current) |
| `staging` | `agri_ai` | `answers` | Production (read-only source for migration) |
| `staging` | `golden_db` | `agri_qa`, `pop` | Golden datasets (read by urgent/ scripts) |

---

## Dependencies Summary

| Package | Used by |
|---|---|
| `pymongo` | All MongoDB scripts |
| `pandas`, `openpyxl` | Excel read/write throughout |
| `sentence-transformers` | `create_chunks.py`, `new_create_chunks.py` |
| `torch` | Embedding model device detection |
| `pymupdf (fitz)` | PDF → images for hashing |
| `imagehash`, `Pillow` | Perceptual hashing for dedup |
| `requests`, `urllib3` | Zoho API calls |
| `tqdm` | Progress bars |
| `schedule` | `scheduler.py` |
| `python-dotenv` | `urgent/` scripts env loading |
