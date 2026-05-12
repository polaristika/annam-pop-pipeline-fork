"""
config/settings.py  –  Central configuration for the POP Pipeline.

Edit values here; everything else reads from this file.
"""

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Repository layout  (all paths are relative to REPO_ROOT)
# ─────────────────────────────────────────────────────────────────────────────
REPO_ROOT       = Path(__file__).resolve().parents[1]   # pop_pipeline/
DPT2_ROOT       = REPO_ROOT / "dpt2_processing"
PROCESSED_ROOT  = DPT2_ROOT / "processed_data"          # output of step 1
PROCESSED_NEW   = DPT2_ROOT / "processed_data_new"      # curated for upload
LOG_DIR         = REPO_ROOT / "logs"

# ─────────────────────────────────────────────────────────────────────────────
# Input CSVs
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_GARBLED_CSV     = DPT2_ROOT / "garbled_pdfs.csv"
DEFAULT_UNPROCESSED_CSV = DPT2_ROOT / "unprocessed_pdfs.csv"

# ─────────────────────────────────────────────────────────────────────────────
# Reference Excel files  (place them in repo root or override via CLI)
# ─────────────────────────────────────────────────────────────────────────────
OUTPUT_XLSX  = REPO_ROOT / "output.xlsx"
MASTER_XLSX  = REPO_ROOT / "Master Sheet - Repository of Govt. Adv and POPs 17 (1).xlsx"

# ─────────────────────────────────────────────────────────────────────────────
# MongoDB – Step 2 (upload) and Step 3 (chunk mapping)
# ─────────────────────────────────────────────────────────────────────────────
MONGO_URI_PROD = (
    "mongodb+srv://riyamehtaatwork_db_user:riyamehtaatwork_db_user"
    "@ajrasakha.1af8ryy.mongodb.net/?appName=ajrasakha"
)
MONGO_URI_STAGING = (
    "mongodb+srv://agriuser:agri_user_0991"
    "@staging.1fo96dy.mongodb.net/?retryWrites=true&w=majority&appName=staging"
)

DB_NAME          = "new_pdf_chunks_and_metadata"
COLLECTION_KRITIKA = "New_Kritika"
COLLECTION_PAULOSE = "new_paulose_1"

# ─────────────────────────────────────────────────────────────────────────────
# Embedding model  (Step 4)
# ─────────────────────────────────────────────────────────────────────────────
EMBED_MODEL      = "BAAI/bge-large-en"
EMBED_DIM        = 1024
EMBED_BATCH_SIZE = 2048
EMBED_DEVICE     = "cuda:1"          # GPU 1 — GPU 0 reserved for VLLM
EMBED_COLLECTIONS = ["merged_chunks_metadata"]

# ─────────────────────────────────────────────────────────────────────────────
# Business logic
# ─────────────────────────────────────────────────────────────────────────────
CENTRAL_KEYWORDS = ["ICAR", "GOI", "CENTRAL", "NATIONAL", "IFFCO", "INDIAN FARMERS"]
CHUNK_BATCH_SIZE = 100    # bulk_write batch for chunk mapping
