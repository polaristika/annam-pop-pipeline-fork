"""
embeddings/generate.py  –  Step 4: Generate BAAI/bge-large-en embeddings

Finds chunks with empty / null / missing embedding_vector and fills them
using GPU batch inference. GPU 1 is used by default (GPU 0 reserved for VLLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config.settings import (
    MONGO_URI_STAGING,
    DB_NAME,
    EMBED_MODEL,
    EMBED_DIM,
    EMBED_BATCH_SIZE,
    EMBED_DEVICE,
    EMBED_COLLECTIONS,
)

# MongoDB filter – catches ALL missing-embedding cases
NEEDS_EMBEDDING_FILTER = {
    "chunks": {
        "$elemMatch": {
            "$or": [
                {"embedding_vector": {"$size": 0}},
                {"embedding_vector": {"$type": 10}},
                {"embedding_vector": {"$exists": False}},
            ]
        }
    }
}


def _chunk_needs_embedding(chunk: dict) -> bool:
    ev = chunk.get("embedding_vector")
    if ev is None:
        return True
    if isinstance(ev, list) and len(ev) == 0:
        return True
    if isinstance(ev, list) and len(ev) == EMBED_DIM:
        return False
    return True   # unexpected – re-embed


def run(args) -> int:
    import torch
    from pymongo import MongoClient, UpdateOne
    from tqdm import tqdm

    device      = args.device or EMBED_DEVICE
    batch_size  = args.batch_size or EMBED_BATCH_SIZE
    collections = args.collections or EMBED_COLLECTIONS
    mongo_uri   = args.mongo_uri or MONGO_URI_STAGING

    # ── GPU check ──────────────────────────────────────────────────────────────
    if not torch.cuda.is_available():
        print("❌ CUDA not available. Embeddings require a GPU.")
        return 1
    gpu_idx  = int(device.split(":")[-1]) if ":" in device else 0
    gpu_name = torch.cuda.get_device_name(gpu_idx)
    vram_gb  = torch.cuda.get_device_properties(gpu_idx).total_memory / 1e9
    print(f"GPU: {gpu_name}  ({vram_gb:.1f} GB VRAM)  →  {device}")

    # ── Load model ─────────────────────────────────────────────────────────────
    from sentence_transformers import SentenceTransformer
    print(f"\nLoading {EMBED_MODEL} ...")
    model = SentenceTransformer(EMBED_MODEL, device=device)
    model.half()
    emb_dim = model.get_sentence_embedding_dimension()
    print(f"  dim={emb_dim}  dtype=fp16")
    assert emb_dim == EMBED_DIM, f"Expected {EMBED_DIM}-dim, got {emb_dim}"

    # ── Connect ────────────────────────────────────────────────────────────────
    print(f"\nConnecting to MongoDB...")
    client = MongoClient(mongo_uri)
    db     = client[DB_NAME]

    if not collections:
        collections = db.list_collection_names()
    print(f"Collections: {collections}\n")

    total_updated = total_skipped = 0

    for col_name in collections:
        col        = db[col_name]
        total_docs = col.count_documents({})
        needs_docs = col.count_documents(NEEDS_EMBEDDING_FILTER)
        print(f"{'─'*60}")
        print(f"Collection: {col_name}  |  total={total_docs}  |  need={needs_docs}")

        if needs_docs == 0:
            print("  All chunks already embedded.")
            continue

        docs = list(tqdm(col.find(NEEDS_EMBEDDING_FILTER), total=needs_docs,
                         desc="  Fetching", unit="doc"))

        work_items = []
        for doc in docs:
            for i, chunk in enumerate(doc.get("chunks", [])):
                if not _chunk_needs_embedding(chunk):
                    total_skipped += 1
                    continue
                content = (chunk.get("chunk_content") or "").strip()
                if content:
                    work_items.append((doc["_id"], i, content))

        if not work_items:
            print("  No embeddable text found.")
            continue

        print(f"  Chunks to embed: {len(work_items)}")
        texts      = [item[2] for item in work_items]
        embeddings = []

        for start in tqdm(range(0, len(texts), batch_size),
                          desc=f"  Embedding [{col_name}]", unit="batch"):
            batch = texts[start: start + batch_size]
            with torch.no_grad():
                vecs = model.encode(batch, normalize_embeddings=True,
                                    convert_to_tensor=True, show_progress_bar=False)
            embeddings.extend(vecs.cpu().float().tolist())

        bulk_ops = [
            UpdateOne({"_id": doc_id},
                      {"$set": {f"chunks.{chunk_idx}.embedding_vector": emb}})
            for (doc_id, chunk_idx, _), emb in zip(work_items, embeddings)
        ]
        result         = col.bulk_write(bulk_ops, ordered=False)
        updated        = result.modified_count
        total_updated += updated
        print(f"  ✓ Updated {updated} chunk embeddings in '{col_name}'")
        torch.cuda.empty_cache()

    print(f"\n{'='*60}")
    print(f"Done! Updated={total_updated}  |  Skipped={total_skipped}")
    client.close()
    return 0


def add_args(sub):
    sub.add_argument("--collections", nargs="+", default=None,
                     help="Collections to process (default from settings)")
    sub.add_argument("--device",      default=None,
                     help=f"Torch device (default: {EMBED_DEVICE})")
    sub.add_argument("--batch-size",  type=int, default=None,
                     help=f"Embedding batch size (default: {EMBED_BATCH_SIZE})")
    sub.add_argument("--mongo-uri",   default=None,
                     help="Override MongoDB URI (default: staging)")
