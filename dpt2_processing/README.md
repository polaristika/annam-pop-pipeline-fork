# POP Pipeline

End-to-end pipeline: PDF advisories → DPT-2 JSON → MongoDB NDB schema → Embeddings.

---

## Project Structure

```
pop_pipeline/
├── pop_pipeline.py          ← Unified CLI entrypoint (run everything from here)
│
├── config/
│   └── settings.py          ← ALL config: paths, Mongo URIs, model names, etc.
│
├── dpt2_processing/
│   ├── batch_process.py     ← Step 1: DPT-2 PDF → JSON/MD (Landing AI API)
│   └── dpt2_batch_process.py  ← Original monolith (keep here, step1 imports it)
│
├── ndb/
│   ├── upload.py            ← Step 2: Batch upload JSON → MongoDB NDB schema
│   └── chunk_map.py         ← Step 3: Copy chunks Kritika → Paulose
│
├── embeddings/
│   └── generate.py          ← Step 4: BAAI/bge-large-en GPU embeddings
│
├── logs/                    ← Auto-created; all log files land here
└── README.md
```

**Reference files** (place in repo root, paths configurable in `config/settings.py`):
```
pop_pipeline/
├── output.xlsx              ← primary_link + duplicates map
└── Master Sheet - Repository of Govt. Adv and POPs 17 (1).xlsx
```

---

## One-time Setup

```bash
pip install pymongo pandas openpyxl sentence-transformers torch tqdm deep-translator PyPDF2 requests
```

---

## CLI Reference

All commands go through `pop_pipeline.py`:

```
python pop_pipeline.py <command> [options]
```

### `step1` – DPT-2 PDF → JSON/MD

```bash
# Process garbled PDFs (default)
python pop_pipeline.py step1

# Process all unprocessed PDFs
python pop_pipeline.py step1 --all

# Limit to 5 rows, verbose logging
python pop_pipeline.py step1 --limit 5 --verbose

# Force re-process already-done files
python pop_pipeline.py step1 --force

# Custom CSV, output dir, PDF root
python pop_pipeline.py step1 \
  --input-csv /data/my_pdfs.csv \
  --pdf-root /data/pdfs/ \
  --output-root /data/processed/

# Filter by language guess
python pop_pipeline.py step1 --lang-filter unsure,indic
```

### `step2` – Upload JSON → MongoDB

```bash
# Dry run (no writes, logs everything)
python pop_pipeline.py step2 --dry-run

# Upload all states
python pop_pipeline.py step2

# Upload one state only
python pop_pipeline.py step2 --state Haryana

# Custom paths
python pop_pipeline.py step2 \
  --base-path /data/processed_data_new \
  --output-xlsx /data/output.xlsx \
  --master-xlsx "/data/Master Sheet.xlsx"

# Upload to a different collection
python pop_pipeline.py step2 --collection New_Kritika_v2
```

### `step3` – Chunk Mapping (Kritika → Paulose)

```bash
# Dry run
python pop_pipeline.py step3 --dry-run

# Live run
python pop_pipeline.py step3

# Custom collections
python pop_pipeline.py step3 \
  --source-collection New_Kritika \
  --target-collection new_paulose_1
```

### `step4` – Generate Embeddings

```bash
# Default (staging DB, GPU 1, all target collections)
python pop_pipeline.py step4

# Specific collections / device
python pop_pipeline.py step4 \
  --collections merged_chunks_metadata \
  --device cuda:0 \
  --batch-size 512

# Override Mongo URI
python pop_pipeline.py step4 --mongo-uri "mongodb+srv://..."
```

### `migrate` – Fix Schema in Existing DB Docs

```bash
# Preview changes
python pop_pipeline.py migrate --collection New_Kritika --dry-run

# Apply fixes
python pop_pipeline.py migrate --collection New_Kritika
```

Fixes applied:
- `unique_link` → `unique_links`
- `doc_usage` entries get `doc_link` field
- `meta_data` cleaned (removes `format`, `agri_expert_name`)
- `chunk_id` reformatted to `doc_id_index`
- `_content_hash` added

### `query` – Search Processed Outputs

```bash
python pop_pipeline.py query --state Haryana --crop wheat
python pop_pipeline.py query --query "paddy cultivation Punjab" --top-k 10
```

### `run-all` – Full Pipeline End-to-End

```bash
# Dry-run (step1 runs, steps 2+3 simulated, step4 skipped)
python pop_pipeline.py run-all --dry-run

# Full run
python pop_pipeline.py run-all

# Skip PDF processing (already done), skip embeddings
python pop_pipeline.py run-all --skip-step1 --skip-step4

# Full run, only Haryana state for upload
python pop_pipeline.py run-all --state Haryana
```

---


### `upload-single` – Upload One JSON File (debug / one-off)

Replaces the old `upload_normalized_json.py` and `test.py`. Use when you want to test a single file before running the full batch.

```bash
# Dry-run — see what would be built, nothing written
python pop_pipeline.py upload-single path/to/dpt2_result.json --dry-run

# Upload and also save a .normalized.json next to the source
python pop_pipeline.py upload-single path/to/dpt2_result.json --save-normalized

# Upload to a different collection
python pop_pipeline.py upload-single path/to/dpt2_result.json --collection New_Kritika_test
```

### `cleanup` – Strip Chunk-Mapping Audit Fields

Removes `chunks_mapped_at`, `chunks_source`, and `chunk_count` from `new_paulose_1`. Run this when you want to re-run step3 from a clean state.

Originally: `rem.py`

```bash
# Preview — how many docs have audit fields
python pop_pipeline.py cleanup --dry-run

# Actually remove them
python pop_pipeline.py cleanup

# Target a different collection
python pop_pipeline.py cleanup --collection new_paulose_1
```

### `verify` – Check a Doc Exists in MongoDB

Quick sanity check after upload.

Originally: the tail of `test.py`

```bash
python pop_pipeline.py verify <doc_id>
python pop_pipeline.py verify <doc_id> --collection New_Kritika
```

## Config

Edit `config/settings.py` to change:

| Setting | What it controls |
|---|---|
| `MONGO_URI_PROD` | Production MongoDB |
| `MONGO_URI_STAGING` | Staging MongoDB (used by embeddings) |
| `DB_NAME` | Database name |
| `COLLECTION_KRITIKA` | Main upload collection |
| `COLLECTION_PAULOSE` | Chunk-mapping target |
| `PROCESSED_ROOT` | Where step1 writes output |
| `PROCESSED_NEW` | Where step2 reads input |
| `OUTPUT_XLSX` | Link dedup map |
| `MASTER_XLSX` | Metadata master sheet |
| `EMBED_MODEL` | Sentence-transformer model |
| `EMBED_DEVICE` | GPU device for embeddings |
| `CENTRAL_KEYWORDS` | Keywords that set `doc_origin = "central"` |

---

## Typical Full-Pipeline Run

```bash
# 1. Dry-run everything to catch issues
python pop_pipeline.py run-all --dry-run

# 2. Process PDFs
python pop_pipeline.py step1 --verbose

# 3. Upload to MongoDB (check a state first)
python pop_pipeline.py step2 --dry-run --state Punjab
python pop_pipeline.py step2 --state Punjab
python pop_pipeline.py step2   # all states

# 4. Map chunks
python pop_pipeline.py step3 --dry-run
python pop_pipeline.py step3

# 5. Embeddings (GPU required)
python pop_pipeline.py step4
```
