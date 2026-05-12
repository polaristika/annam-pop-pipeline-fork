#!/usr/bin/env python3
# create_chunks.py
# Run this once .md/.json files are available in the folder structure.
# Finds each document already inserted by create_documents.py and adds chunks.

import os
import json
import hashlib
from collections import Counter

import pandas as pd
from pymongo import MongoClient, ASCENDING
from sentence_transformers import SentenceTransformer
import torch

# ── Config ─────────────────────────────────────────────────────────────────────
MONGO_URI      = "mongodb+srv://riyamehtaatwork_db_user:riyamehtaatwork_db_user@ajrasakha.1af8ryy.mongodb.net/?appName=ajrasakha" #test in this db, change for prod
DB_NAME        = "new_pdf_chunks_and_metadata"
COLLECTION     = "new_paulose_1"
DATA_DIR       = "../artifacts/phase1_english"
CHUNK_SIZE     = 500
OVERLAP        = 100
EMBED_DEVICE   = "cuda" if torch.cuda.is_available() else "cpu"
WORKDRIVE_BASE = "https://workdrive.zoho.in/file/"

# ── Helpers ────────────────────────────────────────────────────────────────────
def extract_pdf_id(folder_name: str) -> str:
    return folder_name.rsplit("-", 1)[-1]

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ── Loader (only unique_urls needed — for all_links on each chunk) ─────────────
def load_unique_urls():
    path = os.path.join(DATA_DIR, "unique_urls.xlsx")
    df = pd.read_excel(path, dtype=str).fillna("")

    result = {}
    for _, row in df.iterrows():
        primary  = row["primary_link"].strip()
        doc_id   = row.get("doc_id", "").strip()
        raw_dups = row.get("duplicates", "")
        dups     = [u.strip() for u in raw_dups.split(",") if u.strip()]
        # all_links = list(dict.fromkeys([primary] + dups))
        result[primary] = {"doc_id": doc_id}

    return result

# ── JSON → segments ────────────────────────────────────────────────────────────
def extract_segments(json_path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # ── Flat content-array format (e.g. NHB/newsletter JSONs with base64 images)
    if "content" in data and isinstance(data["content"], list):
        segments = []
        for item in data["content"]:
            item_type = item.get("type", "")
            if item_type in ("text", "heading"):
                text = item.get("content", "").strip()
                if text:
                    segments.append((text, 1))
            elif item_type == "image":
                # skip base64 blob; keep description only if present
                desc = item.get("description", "").strip()
                if desc:
                    segments.append((desc, 1))
        return segments

    # ── Docling format (body / children / $ref)
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

# ── Chunking ───────────────────────────────────────────────────────────────────
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

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    col   = MongoClient(MONGO_URI)[DB_NAME][COLLECTION]
    model = SentenceTransformer("BAAI/bge-large-en", device=EMBED_DEVICE)

    col.create_index([("document.doc_id", ASCENDING)])

    unique_urls = load_unique_urls()


    for folder in os.listdir(DATA_DIR):

        folder_path = os.path.join(DATA_DIR, folder)

        # skip files like xlsx/json
        if not os.path.isdir(folder_path):
            continue

        pdf_id = extract_pdf_id(folder)
        primary_link = f"{WORKDRIVE_BASE}{pdf_id}"

        print("\n==============================")
        print(f"[DEBUG] PDF ID: {pdf_id}")
        print(f"[DEBUG] Primary Link: {primary_link}")
        print(f"[DEBUG] Folder Path: {folder_path}")
        print("==============================\n")

        if primary_link not in unique_urls:
            print(f"  ❌ NOT FOUND IN unique_url.xlsx → {primary_link}")
            continue

        url_data  = unique_urls[primary_link]
        doc_id    = pdf_id
        # all_links = url_data["all_links"]

        # ── CHECK: document must exist (created by create_documents.py) ─
        existing = col.find_one({"document.doc_id": doc_id})
        if not existing:
            print(f"  ⚠️  Document {doc_id} not found in DB — run create_documents.py first")
            continue

        # ── SKIP: chunks already present ───────────────────────────────────
        if existing.get("chunks"):
            print(f"  → Skipped {doc_id} (chunks already exist)")
            continue
        # ── Resolve canonical document files (new naming first, old naming fallback) ──


        
        # ── Resolve canonical document files (new naming first, old naming fallback) ──

        json_candidates = [
            f"{folder}_output.json",   # preferred
            f"{folder}.json"           # fallback
        ]

        md_candidates = [
            f"{folder}_document.md",   # preferred
            f"{folder}.md"             # fallback
        ]

        json_path = None
        md_path = None


        # Resolve JSON
        for filename in json_candidates:
            candidate = os.path.join(folder_path, filename)
            if os.path.exists(candidate):
                json_path = candidate
                break


        # Resolve MD (optional, informational only)
        for filename in md_candidates:
            candidate = os.path.join(folder_path, filename)
            if os.path.exists(candidate):
                md_path = candidate
                break


        # Hard fail if no valid JSON found
        if not json_path:
            print(f"  ⚠️ No matching JSON found for {doc_id}")
            print(f"     Tried: {json_candidates}")
            continue


        print(f"  ✓ Using JSON: {os.path.basename(json_path)}")

        if md_path:
            print(f"  ✓ Using MD:   {os.path.basename(md_path)}")
        else:
            print(f"  ⚠️ No matching MD found (optional)")

        # ── EXTRACT + CHUNK ────────────────────────────────────────────────
        segments = extract_segments(json_path)
        chunks   = chunk_with_pages(segments)

        if not chunks:
            print(f"  ⚠️  No chunks produced for {doc_id}")
            continue

        # ── EMBED ──────────────────────────────────────────────────────────
        texts      = [c[0] for c in chunks]
        embeddings = model.encode(texts, batch_size=64, normalize_embeddings=True)

        chunk_docs = []
        for i, ((text, page), emb) in enumerate(zip(chunks, embeddings)):
            chunk_docs.append({
                    # "doc_links":         all_links,   # all URLs, primary + duplicates
                    "chunk_id":          f"{doc_id}_{i}",
                    "associated_doc_id": doc_id,
                    "embedding_vector":  emb.tolist(),
                    "chunk_content":     text,
                    "page_no":           page,
                    "_content_hash":     sha256(text),
            })

        # ── WRITE CHUNKS TO EXISTING DOCUMENT ─────────────────────────────
        col.update_one(
            {"document.doc_id": doc_id},
            {"$set": {"chunks": chunk_docs}}
        )
        print(f"  ✓ Added {len(chunk_docs)} chunks to doc {doc_id}")

    print("\n✓ Done")

if __name__ == "__main__":
    main()