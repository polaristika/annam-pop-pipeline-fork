# pop_2 — Zoho Download & MongoDB Ingest

The `pop_2/` folder contains scripts for two things:
1. Pulling unique PDFs from Zoho WorkDrive into the pipeline
2. Ingesting processed PDF outputs into MongoDB as searchable chunks

---

## Overall Flow

```
Zoho WorkDrive / Sheet
        │
        ▼
[1] Authenticate with Zoho        zoho_token_exchange.py
        │
        ▼
[2] Deduplicate links              extract_unique_link.py
        │  (scans Zoho sheet, hashes each PDF, outputs unique_urls.xlsx)
        ▼
[3] Download unique PDFs           zoho_pdf_download_v2.py
        │  (downloads only the deduplicated primary links)
        ▼
[4] Run main pipeline              pop_cli.py  (see root README)
        │
        ▼
[5] Create MongoDB documents       create_documents.py
        │
        ▼
[6] Create chunks + embeddings     create_chunks.py
        │
        ▼
MongoDB: new_pdf_chunks_and_metadata.new_paulose_1
```

---

## Files

| File | What it does |
|------|--------------|
| `zoho_token_exchange.py` | One-time: exchanges a Zoho auth code for tokens, saves to `zoho_tokens.json` |
| `extract_unique_link.py` | Scans Zoho sheet, detects duplicate PDFs via perceptual hashing, outputs `output.csv` and `unique_urls.xlsx` |
| `zoho_pdf_download_v2.py` | Downloads only the PDFs listed in `unique_urls.xlsx` (skip-existing, 8 parallel threads) |
| `create_documents.py` | Reads `unique_urls.xlsx` + `MetadataMaster.xlsx`, inserts metadata docs into MongoDB |
| `create_chunks.py` | Reads Phase 1 JSON outputs, creates sliding-window chunks, embeds with `BAAI/bge-large-en`, writes to MongoDB |
| `zoho_sheet_explorer.py` | Utility: checks how many Zoho links in the workbook are accessible vs broken |
| `ZOHO_SETUP.md` | Step-by-step guide to get Zoho API credentials |
| `WORK_DONE.md` | Detailed documentation of the full pipeline and all scripts |
| `creating_doc_and_chunks.md` | Docs for the MongoDB document/chunk pipeline |

---

## Setup

Create a `.pop_2_env` file in the **project root** (not inside `pop_2/`):

```
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_AUTH_CODE=your_auth_code
MONGO_URI=mongodb+srv://...
```

All scripts load this file automatically at startup.

---

## Step-by-Step

### 1. Get Zoho credentials

Follow `pop_2/ZOHO_SETUP.md` to get a Client ID, Client Secret, and a 10-minute auth code from the Zoho API console.

### 2. Authenticate

```bash
python pop_2/zoho_token_exchange.py
```

Saves `zoho_tokens.json`. Tokens expire in ~1 hour — re-run with a fresh auth code to refresh.

### 3. Deduplicate links

```bash
python pop_2/extract_unique_link.py
```

Scans all Zoho sheet links, downloads each file temporarily to compute a perceptual hash (first 3 PDF pages), and groups duplicates. Outputs:
- `output.csv` — resumable checkpoint with hash values and duplicate lists
- `unique_urls.xlsx` — clean list of unique primary links

### 4. Download unique PDFs

```bash
python pop_2/zoho_pdf_download_v2.py --link unique_urls.xlsx
```

Downloads only the deduplicated primary links to `data/raw/POP Bank/{State}/`. Already-downloaded files are skipped.

### 5. Run the main pipeline

Process PDFs through Phases 1–2 using `pop_cli.py` (see root README). Outputs land in `artifacts/phase1_english/`.

> **numpy version switch:** `pop_cli.py` (Phase 1) requires `numpy==2.2.6`. Before running the ingest steps below, downgrade numpy:
> ```bash
> pip install numpy==1.26.4
> ```

### 6. Create MongoDB documents

```bash
python pop_2/create_documents.py
```

Reads `unique_urls.xlsx` and `MetadataMaster.xlsx`, inserts one document per unique PDF into MongoDB. Safe to rerun — skips unchanged records.

### 7. Create chunks and embeddings

```bash
python pop_2/create_chunks.py
```

Reads JSON outputs from `artifacts/phase1_english/`, splits text into 500-word sliding-window chunks (100-word overlap), embeds with `BAAI/bge-large-en` (GPU recommended), writes to MongoDB. Safe to rerun — skips docs that already have chunks.

---

## MongoDB Collections

| Database | Collection | Written by |
|----------|------------|------------|
| `new_pdf_chunks_and_metadata` | `new_paulose` | v1 scripts (legacy) |
| `new_pdf_chunks_and_metadata` | `new_paulose_1` | v2 scripts (current) |

---

## Key Data Files (not in git)

| File | Description |
|------|-------------|
| `zoho_tokens.json` | Live Zoho OAuth tokens — gitignored |
| `output.csv` | Deduplication checkpoint (4136 unique docs) |
| `unique_urls.xlsx` | Clean deduplicated link list |
| `MetadataMaster.xlsx` | POP metadata workbook (multi-sheet, keyed on `Link`) |

---

## Dependencies

```bash
pip install pymongo pandas openpyxl sentence-transformers torch pymupdf imagehash Pillow requests tqdm
```

GPU (CUDA) is strongly recommended for embedding generation.
