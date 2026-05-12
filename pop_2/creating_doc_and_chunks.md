# PDF Processing and Chunking Pipeline

## Overview

This project ingests structured PDF content, stores document-level metadata in MongoDB, then generates semantic chunks and embeddings for retrieval.

The pipeline runs in two phases:

1. `create_documents.py`
2. `create_chunks.py`

Keeping these separate allows:

- metadata to be loaded independently
- chunking to be rerun without touching documents
- embeddings to be regenerated without rebuilding metadata

---

# Repository Structure

```bash
process_english_files/
├── README.md
├── requirements.txt
├── create_documents.py
├── create_chunks.py
│
└── data/
    ├── unique_urls.xlsx
    ├── MetadataMaster.xlsx
    │
    ├── Guava Intercultural Operations-qpkuu9...
    │   ├── ..._output.json
    │   └── ..._document.md
    │
    ├── NHB-Mango Propagation Method-2ta2...
    │   ├── ....json
    │   └── ....md
    │
    └── Newsletter Final-Water logged rice...
        ├── ....json
        └── ....md
```

---

# Environment Setup

## Create Virtual Environment

```bash
python3 -m venv env
```

Activate:

```bash
source env/bin/activate
```

Verify:

```bash
which python
```

Expected:

```bash
.../process_english_files/env/bin/python
```

---

## Upgrade pip

```bash
pip install --upgrade pip
```

---

# Install Dependencies

Create:

## requirements.txt

```txt
pandas
openpyxl
pymongo
sentence-transformers
transformers
torch
numpy
tqdm
```

Install:

```bash
pip install -r requirements.txt
```

---

# GPU Setup in VM

Embedding generation uses:

```bash
BAAI/bge-large-en
```

GPU is strongly recommended.

---

## Verify GPU

```bash
nvidia-smi
```

Should show:

- GPU model
- Driver version
- CUDA version

---

## Verify CUDA in Python

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

Expected:

```bash
True
```

Check GPU:

```bash
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

Example:

```bash
NVIDIA H200 NVL
```

---

## Install CUDA-enabled PyTorch

Example CUDA 12.1:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

---

## Verify model loads

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-en')"
```

---

# Input Files

---

# unique_urls.xlsx

Required columns:

```text
primary_link
duplicates
doc_id
```

Purpose:

- canonical document identity
- duplicate URL mapping
- deduplication

Example:

```text
primary_link                 duplicates
link1                        link2,link3
```

Produces:

```text
doc_links:
[
 primary,
 duplicate1,
 duplicate2
]
```

---

# MetadataMaster.xlsx

Required columns:

```text
Link
Name of POPs
Show Name
Language
Organization Name, with Location
Season
Crop
In which States it's Used for
Agri Expert name
```

Used to populate:

- metadata
- crop mapping
- state usage
- expert verification

---

# Document Folder Naming

Folder:

```bash
<document-name>-<pdf_id>
```

Examples:

```bash
Guava Intercultural Operations-qpkuu...
```

---

## Supported file naming

Preferred:

```bash
<folder>_output.json
<folder>_document.md
```

Fallback:

```bash
<folder>.json
<folder>.md
```

Both are supported.

---

# MongoDB Schema

Collection:

```bash
new
```

Database:

```bash
new_pdf_chunks_and_metadata
```

---

## Document Record

Created by:

```bash
create_documents.py
```

Structure:

```json
document:
  doc_id
  doc_name
  app_name
  unique_links
  doc_links
  doc_origin

  meta_data:
      language
      organization_name
      organization_location
      season

  doc_usage:
      state
      crop
      verified_by

chunks: []
```

---

## Chunk Structure

Created by:

```bash
create_chunks.py
```

```json
chunk:
   chunk_id
   associated_doc_id
   chunk_content
   page_no
   embedding_vector
   _content_hash
```

Note:

Document links are intentionally NOT stored in chunks.

Chunks reference parent document using:

```text
associated_doc_id
```

---

# Hashing

Each chunk stores:

```python
sha256(text)
```

Using:

```python
hashlib.sha256(text.encode("utf-8")).hexdigest()
```

Stored as:

```text
_content_hash
```

Purpose:

- content fingerprinting
- chunk comparison
- future duplicate detection
- change detection

Example:

```text
5c57b592f6421079706484abebcab81b...
```

---

# Chunking Strategy

Configuration:

```python
CHUNK_SIZE = 500
OVERLAP = 100
```

Sliding window:

```text
1-500
401-900
801-1300
```

Each chunk stores dominant source page.

---

# Supported JSON Structures

---

## 1. Flat content-array format

```json
content[]
type:
  text
  heading
  image
```

Used for newsletter/NHB-style JSONs.

Images skipped except description text.

---

## 2. Docling hierarchical format

Uses:

```text
body.children
$ref resolution
text nodes
prov.page_no
```

Furniture layer ignored:

```text
content_layer = furniture
```

---

# Pipeline Flow

## Phase 1

Run:

```bash
python create_documents.py
```

Flow:

```bash
Start
 |
 v
Load unique_urls.xlsx
 |
Load MetadataMaster.xlsx
 |
Build doc_usage
 |
Check MongoDB
 |-------------------+
 |                   |
New Document       Existing
 |                   |
Insert            Compare links/usage
 |                   |
Done           Update or Skip
```

---

## Phase 2

Run:

```bash
python create_chunks.py
```

Flow:

```bash
Start
 |
Scan document folders
 |
Resolve JSON / MD
 |
Check Mongo document exists
 |
Skip if chunks already exist
 |
Extract text segments
 |
Create chunks
 |
Generate embeddings
 |
SHA256 hash each chunk
 |
Update MongoDB with chunks
 |
Done
```

---

# Full End-to-End Flow Diagram

```bash
unique_urls.xlsx
MetadataMaster.xlsx
        |
        v
+----------------------+
| create_documents.py  |
+----------------------+
        |
  Insert/Update docs
        |
        v
MongoDB documents
        |
        v
+--------------------+
| create_chunks.py   |
+--------------------+
        |
 JSON parsing
 Chunking
 Embeddings
 Hashing
        |
        v
MongoDB documents + chunks
```

---

# Running the Pipeline

## Step 1

```bash
python create_documents.py
```

Expected:

```bash
✓ Inserted ...
→ Updated ...
→ Skipped ...
```

---

## Step 2

```bash
python create_chunks.py
```

Expected:

```bash
✓ Added 42 chunks to doc ...
```

---

## Full Run

```bash
source env/bin/activate

python create_documents.py

python create_chunks.py
```

---

# Re-running

Safe to rerun.

---

## create_documents.py

Will:

- insert new docs
- update changed metadata
- skip unchanged records

---

## create_chunks.py

Will skip:

```bash
chunks already exist
```

No duplicate chunk embeddings created.

---

# Troubleshooting

## GPU not detected

Check:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

---

## Missing JSON

Check naming:

```bash
<folder>_output.json
```

or

```bash
<folder>.json
```

---

## No chunks produced

Usually:

- unsupported JSON schema
- empty extracted text
- all content filtered

---

## Mongo connection failure

Check:

- MONGO_URI
- IP whitelist
- credentials
- cluster availability

---

# Design Notes

## Why two scripts?

Separates:

- metadata ingestion
- content chunking

Avoids rerunning expensive embeddings when metadata changes.

---

## Why SHA256 hash?

Allows future:

- dedup detection
- content change tracking
- chunk integrity validation

---

## Why no doc_links inside chunks?

Normalization.

Store links once at document level.

Use:

```text
associated_doc_id
```

to link chunks back to documents.

Avoids repeated link storage across hundreds of chunks.