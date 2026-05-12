#!/usr/bin/env python3
# create_chunks.py
# Step 5: Embed and chunk Phase 1 extraction outputs, write to MongoDB.
# Run after create_documents.py once .json files are available.
# Credentials and paths are read from .pop_2_env at project root.

import os
import json
import hashlib
from collections import Counter
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, ASCENDING
from sentence_transformers import SentenceTransformer
import torch


# ── Config defaults (overridden at runtime via .pop_2_env) ────────────────────
MONGO_URI      = ""
DB_NAME        = "new_pdf_chunks_and_metadata"
COLLECTION     = "new_paulose"
DATA_DIR       = "artifacts/phase1_english"
CHUNK_SIZE     = 500
OVERLAP        = 100
EMBED_DEVICE   = "cuda" if torch.cuda.is_available() else "cpu"
WORKDRIVE_BASE = "https://workdrive.zoho.in/file/"


# ── Env loader ────────────────────────────────────────────────────────────────

def _load_pop2_env():
    candidates = [
        Path(__file__).resolve().parent.parent / ".pop_2_env",
        Path(".pop_2_env"),
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break


def _setup():
    global MONGO_URI, DB_NAME, COLLECTION, DATA_DIR
    _load_pop2_env()
    MONGO_URI  = os.environ.get("MONGO_URI",       MONGO_URI)
    DB_NAME    = os.environ.get("MONGO_DB",         DB_NAME)
    COLLECTION = os.environ.get("MONGO_COLLECTION", COLLECTION)
    DATA_DIR   = os.environ.get("DATA_DIR",         DATA_DIR)
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI not set — add it to .pop_2_env")


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_pdf_id(folder_name: str) -> str:
    return folder_name.rsplit("-", 1)[-1]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Loader ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_unique_urls():
    path = str(PROJECT_ROOT / "unique_urls.xlsx")
    df = pd.read_excel(path, dtype=str).fillna("")

    result = {}
    for _, row in df.iterrows():
        primary = row["primary_link"].strip()
        doc_id  = row.get("doc_id", "").strip()
        result[primary] = {"doc_id": doc_id}

    return result


# ── JSON → segments ───────────────────────────────────────────────────────────

def extract_segments(json_path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # Flat content-array format (NHB/newsletter JSONs)
    if "content" in data and isinstance(data["content"], list):
        segments = []
        for item in data["content"]:
            item_type = item.get("type", "")
            if item_type in ("text", "heading"):
                text = item.get("content", "").strip()
                if text:
                    segments.append((text, 1))
            elif item_type == "image":
                desc = item.get("description", "").strip()
                if desc:
                    segments.append((desc, 1))
        return segments

    # Docling tree format (body / children / $ref)
    def resolve(ref):
        parts = ref.lstrip("#/").split("/")
        node = data
        for p in parts:
            node = node[int(p)] if isinstance(node, list) else node[p]
        return node

    segments = []

    def visit(node):
        node = resolve(node["$ref"]) if "$ref" in node else node
        if node.get("content_layer") == "furniture":
            return
        if node.get("children"):
            for child in node["children"]:
                visit(child)
        else:
            text = node.get("text", "").strip()
            prov = node.get("prov", [])
            page = prov[0]["page_no"] if prov else 1
            if text:
                segments.append((text, page))

    for child in data.get("body", {}).get("children", []):
        visit(child)

    return segments


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_with_pages(segments):
    word_pages = [(w, p) for text, p in segments for w in text.split()]
    step = CHUNK_SIZE - OVERLAP

    chunks = []
    for i in range(0, len(word_pages), step):
        batch = word_pages[i:i + CHUNK_SIZE]
        if not batch:
            break
        text = " ".join(w for w, _ in batch)
        page = Counter(p for _, p in batch).most_common(1)[0][0]
        chunks.append((text, page))

    return chunks


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    _setup()

    col   = MongoClient(MONGO_URI)[DB_NAME][COLLECTION]
    model = SentenceTransformer("BAAI/bge-large-en", device=EMBED_DEVICE)

    col.create_index([("document.doc_id", ASCENDING)])

    unique_urls = load_unique_urls()

    folders = sorted(os.listdir(DATA_DIR))
    if args.limit:
        folders = folders[:args.limit]
        print(f"[TEST MODE] Limited to {args.limit} folders\n")

    for folder in folders:
        folder_path = os.path.join(DATA_DIR, folder)

        if not os.path.isdir(folder_path):
            continue

        pdf_id       = extract_pdf_id(folder)
        primary_link = f"{WORKDRIVE_BASE}{pdf_id}"

        print("\n==============================")
        print(f"[DEBUG] PDF ID: {pdf_id}")
        print(f"[DEBUG] Primary Link: {primary_link}")
        print(f"[DEBUG] Folder Path: {folder_path}")
        print("==============================\n")

        if primary_link not in unique_urls:
            print(f"  ❌ NOT FOUND IN unique_urls.xlsx → {primary_link}")
            continue

        doc_id   = pdf_id
        existing = col.find_one({"document.doc_id": doc_id})
        if not existing:
            print(f"  ⚠️  Document {doc_id} not found in DB — run ingest-docs first")
            continue

        if existing.get("chunks"):
            print(f"  → Skipped {doc_id} (chunks already exist)")
            continue

        json_candidates = [f"{folder}_output.json", f"{folder}.json"]
        json_path = None
        for filename in json_candidates:
            candidate = os.path.join(folder_path, filename)
            if os.path.exists(candidate):
                json_path = candidate
                break

        md_candidates = [f"{folder}_document.md", f"{folder}.md"]
        md_path = None
        for filename in md_candidates:
            candidate = os.path.join(folder_path, filename)
            if os.path.exists(candidate):
                md_path = candidate
                break

        if not json_path:
            print(f"  ⚠️ No matching JSON found for {doc_id}")
            print(f"     Tried: {json_candidates}")
            continue

        print(f"  ✓ Using JSON: {os.path.basename(json_path)}")
        if md_path:
            print(f"  ✓ Using MD:   {os.path.basename(md_path)}")
        else:
            print(f"  ⚠️ No matching MD found (optional)")

        segments = extract_segments(json_path)
        chunks   = chunk_with_pages(segments)

        if not chunks:
            print(f"  ⚠️  No chunks produced for {doc_id}")
            continue

        texts      = [c[0] for c in chunks]
        embeddings = model.encode(texts, batch_size=64, normalize_embeddings=True)

        chunk_docs = []
        for i, ((text, page), emb) in enumerate(zip(chunks, embeddings)):
            chunk_docs.append({
                "chunk": {
                    "chunk_id":          f"{doc_id}_{i}",
                    "associated_doc_id": doc_id,
                    "embedding_vector":  emb.tolist(),
                    "chunk_content":     text,
                    "page_no":           page,
                    "_content_hash":     sha256(text),
                }
            })

        col.update_one(
            {"document.doc_id": doc_id},
            {"$set": {"chunks": chunk_docs}}
        )
        print(f"  ✓ Added {len(chunk_docs)} chunks to doc {doc_id}")

    print("\n✓ Done")


if __name__ == "__main__":
    main()
