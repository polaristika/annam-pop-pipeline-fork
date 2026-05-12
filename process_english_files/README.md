# process_english_files

This folder contains a two-step pipeline that ingests processed English PDF documents into MongoDB — first creating document metadata records, then embedding and storing text chunks.

---

## Folder Contents

| File | Purpose |
|---|---|
| `create_documents.py` | Step 1 — reads Excel metadata and inserts/updates document records in MongoDB |
| `create_chunks.py` | Step 2 — extracts text from JSON outputs, chunks, embeds, and writes chunks to MongoDB |
| `riya_req.txt` | Python dependencies (pip install -r) |
| `riya_setup.md` | Original setup guide |
| `venv/` | Python virtual environment (not tracked in git) |

---

## Data Dependencies (not included, place under `./data/`)

```
data/
├── unique_urls.xlsx        # primary_link, duplicates, doc_id columns
├── MetadataMaster.xlsx     # multi-sheet: Link, Name of POPs, Organization, Crop, Season, …
│
├── <state>/                # e.g. karnataka/, punjab/
│   └── <document-folder>-<pdf_id>/
│       ├── <folder>_output.json    # preferred naming
│       └── <folder>_document.md   # optional
```

The `pdf_id` is the last segment of each Zoho WorkDrive URL (`https://workdrive.zoho.in/file/<pdf_id>`).

---

## MongoDB Schema

Database: `new_pdf_chunks_and_metadata`

### Collection: `metadata_document` (written by `create_documents.py`)

```json
{
  "document": {
    "doc_id": "<pdf_id>",
    "doc_name": "Name of POPs from metadata",
    "app_name": "Show Name from metadata",
    "unique_links": "<primary WorkDrive URL>",
    "doc_links": ["<primary>", "<duplicate1>", ...],
    "doc_origin": "Org Name, Location",
    "meta_data": {
      "language": "...",
      "organization_name": "...",
      "organization_location": "...",
      "season": "..."
    },
    "doc_usage": [
      { "doc_link": "...", "state": "...", "crop": "...", "verified_by": "..." }
    ]
  },
  "chunks": []   // populated later by create_chunks.py
}
```

### Chunks (added by `create_chunks.py`)

Each document's `chunks` array is updated in-place:

```json
{
  "chunk": {
    "chunk_id": "<doc_id>_<index>",
    "associated_doc_id": "<doc_id>",
    "embedding_vector": [1024-dim float array],
    "chunk_content": "...",
    "page_no": 3,
    "_content_hash": "<sha256>"
  }
}
```

---

## How the Scripts Work

### `create_documents.py`

1. Reads `data/unique_urls.xlsx` — each row is one logical document with a primary link and optional comma-separated duplicates.
2. Reads `data/MetadataMaster.xlsx` (all sheets concatenated) — keyed on the `Link` column.
3. For each primary link:
   - If document already exists in MongoDB → adds any new links or usage records (`$addToSet`).
   - If new → inserts a full document record with metadata and an empty `chunks` array.

Re-running is safe: unchanged records are skipped.

### `create_chunks.py`

1. Iterates subdirectories of `data/` (each is one document folder).
2. Derives the `pdf_id` from the folder name suffix (last `-`-delimited segment).
3. Skips folders not present in `unique_urls.xlsx` or whose document has chunks already.
4. Resolves the JSON file using this priority:
   - `<folder>_output.json` (preferred)
   - `<folder>.json` (fallback)
5. Extracts text segments from the JSON, supporting two formats:
   - **Flat content-array** (NHB/newsletter style with `type: text|heading|image`)
   - **Docling tree format** (recursive `body → children → $ref` nodes)
6. Sliding-window chunks: 500 words, 100-word overlap.
7. Embeds all chunks with `BAAI/bge-large-en` (via `sentence-transformers`, GPU if available).
8. Updates the existing MongoDB document with the `chunks` array.

Re-running is safe: documents with existing chunks are skipped.

---

## Setup & Run

```bash
# 1. Create and activate virtualenv
python3 -m venv venv
source venv/bin/activate

# 2. Install PyTorch (GPU example for CUDA 12.1)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Install other dependencies
pip install -r riya_req.txt

# 4. Update MongoDB URI in both scripts
#    MONGO_URI = "mongodb+srv://..."

# 5. Place data files under ./data/ (see structure above)

# 6. Run in order
python create_documents.py
python create_chunks.py
```

---

## Configuration Constants

Both scripts share these top-of-file constants — edit before running:

| Constant | File | Default | Description |
|---|---|---|---|
| `MONGO_URI` | both | `"mongodb+srv://..."` | Atlas connection string |
| `DB_NAME` | both | `new_pdf_chunks_and_metadata` | Database name |
| `COLLECTION` | `create_documents.py` | `metadata_document` | Document collection |
| `COLLECTION` | `create_chunks.py` | `new` | Same collection for chunk writes |
| `DATA_DIR` | both | `./data` | Root data directory |
| `CHUNK_SIZE` | `create_chunks.py` | `500` | Words per chunk |
| `OVERLAP` | `create_chunks.py` | `100` | Overlap between consecutive chunks |
| `EMBED_DEVICE` | `create_chunks.py` | auto (`cuda`/`cpu`) | Embedding device |

> **Note:** `COLLECTION` differs between the two scripts (`metadata_document` vs `new`). Ensure both point to the same collection for chunks to be written back correctly.

---

## Relationship to the Main Pipeline

These scripts are a downstream consumer of the main `pop_cli.py` pipeline. The expected flow is:

```
pop_cli.py process (Phase 1)
        │
        └─► artifacts/phase1_english/<hash>/
                ├── doc.json        ← renamed/copied into data/<folder>_output.json
                └── doc.md
                        │
                        ▼
        create_documents.py  →  MongoDB document record
        create_chunks.py     →  MongoDB chunks + embeddings
```
