# Setup Guide

## 1. Place Project Files

Create a project folder:

```bash
mkdir process_english_files
cd process_english_files
```

Copy the provided files into this folder:

```bash
1_create_documents.py
2_create_chunks.py
data/
```

Final structure should look like:

```bash
process_english_files/
├── 1_create_documents.py
├── 2_create_chunks.py
└── data/
```

---

# 2. Create Python Virtual Environment

Create environment:

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

# 3. Upgrade pip

```bash
pip install --upgrade pip
```

---

# 4. Install PyTorch (GPU-enabled)

Example for CUDA 12.1:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

---

# 5. Install Project Dependencies

Create `requirements.txt`

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

# 6. Verify GPU Setup

Check GPU visibility:

```bash
nvidia-smi
```

Verify in Python:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

Expected:

```bash
True
```

Check GPU device:

```bash
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

Example:

```bash
NVIDIA H200 NVL
```

---

# 7. Verify Embedding Model Loads

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-en')"
```

Model downloads on first run.

---

# Data Folder Setup

Expected structure:

```bash
data/
├── unique_urls.xlsx
├── MetadataMaster.xlsx
├── metadata.xlsx
├── structure.json
│
├── karnataka/
│   └── <document-folder>/
│       ├── <folder_name>_output.json
│       └── <folder_name>_document.md
│
├── punjab/
│   └── <document-folder>/
│       ├── <folder_name>_output.json
│       └── <folder_name>_document.md
```

---

# Required Excel Setup

## unique_urls.xlsx

Required columns:

```text
primary_link
duplicates
doc_id
```

Used for:

- document identity
- duplicate link mapping
- deduplication

---

## MetadataMaster.xlsx

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

Used for:

- metadata population
- crop/state mapping
- verification metadata

---

# MongoDB Setup

Update in both scripts:

```python
MONGO_URI="your_connection_string"
DB_NAME="new_pdf_chunks_and_metadata"
COLLECTION="new_test"
```

Ensure:

- credentials are valid
- IP is whitelisted
- cluster reachable

---

# Run Order

## Step 1 — Create document records

```bash
python 1_create_documents.py
```

Creates:

- document metadata
- link mappings
- doc usage records

---

## Step 2 — Generate chunks + embeddings

```bash
python 2_create_chunks.py
```

Creates:

- extracted chunks
- embeddings
- stores chunks in MongoDB

---

# Full Run Commands

```bash
source env/bin/activate

python 1_create_documents.py

python 2_create_chunks.py
```

---

# Re-running

Safe to rerun both.

## Documents script

Will:

- insert new documents
- update changed metadata
- skip unchanged records

---

## Chunk script

Will skip:

```bash
chunks already exist
```

No duplicate embeddings created.

---

# Deactivate Environment

When done:

```bash
deactivate
```

---

# Re-enter Later

```bash
cd process_english_files
source env/bin/activate
```

---

# Troubleshooting

## Wrong Python being used

Check:

```bash
which python
```

Should point to:

```bash
env/bin/python
```

---

## Package import errors

Reinstall dependencies:

```bash
pip install -r requirements.txt
```

---

## GPU not detected

Check:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

If False:

- verify drivers
- reinstall CUDA torch build

---

## Missing JSON errors

Ensure naming follows:

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