"""
ndb/chunk_map.py  –  Step 3: Map chunks from New_Kritika → new_paulose_1

Matches documents via document.unique_links.
  - Paulose empty  → fill from Kritika
  - Paulose partial (fewer chunks than Kritika) → overwrite
  - No Kritika match → logged to unmatched_paulose_docs.log
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config.settings import (
    MONGO_URI_PROD,
    DB_NAME,
    COLLECTION_KRITIKA,
    COLLECTION_PAULOSE,
    CHUNK_BATCH_SIZE,
    LOG_DIR,
)


def run(args) -> int:
    from pymongo import MongoClient, UpdateOne

    dry_run     = args.dry_run
    log_file    = Path(args.log_file) if args.log_file else LOG_DIR / "step3_chunk_map.log"
    batch_size  = args.batch_size or CHUNK_BATCH_SIZE
    kritika_col_name = getattr(args, "source_collection", COLLECTION_KRITIKA)
    paulose_col_name = getattr(args, "target_collection", COLLECTION_PAULOSE)
    mongo_uri   = getattr(args, "mongo_uri", MONGO_URI_PROD)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )
    log = logging.getLogger("chunk_map")
    log.info("=" * 60)
    log.info(f"Step 3 – Chunk Mapping | DRY_RUN={dry_run}")
    log.info(f"  {kritika_col_name} → {paulose_col_name}")
    log.info("=" * 60)

    client      = MongoClient(mongo_uri)
    db          = client[DB_NAME]
    kritika_col = db[kritika_col_name]
    paulose_col = db[paulose_col_name]

    # ── Build Kritika lookup {unique_links → {chunks, count}} ─────────────────
    log.info("Building Kritika lookup map...")
    kritika_map = {}
    for doc in kritika_col.find(
        {"chunks": {"$exists": True, "$not": {"$size": 0}}},
        {"document.unique_links": 1, "chunks": 1},
    ):
        link   = doc.get("document", {}).get("unique_links")
        chunks = doc.get("chunks", [])
        if not link or not chunks:
            continue
        if link not in kritika_map or len(chunks) > len(kritika_map[link]["chunks"]):
            kritika_map[link] = {"chunks": chunks, "count": len(chunks), "_id": doc["_id"]}
    log.info(f"Kritika docs with valid chunks: {len(kritika_map)}")

    # ── Iterate Paulose ───────────────────────────────────────────────────────
    log.info("Scanning Paulose collection...")
    stats = {"total": 0, "empty_filled": 0, "overwritten": 0, "skipped_ok": 0, "unmatched": 0}
    bulk_ops, unmatched = [], []

    for p_doc in paulose_col.find({}, {"document.unique_links": 1, "chunks": 1}):
        stats["total"] += 1
        p_id     = p_doc["_id"]
        p_link   = p_doc.get("document", {}).get("unique_links")
        p_chunks = p_doc.get("chunks", [])
        p_count  = len(p_chunks)

        if not p_link:
            log.warning(f"[NO LINK] _id={p_id} – skipping")
            continue

        matched = kritika_map.get(p_link)

        if matched is None:
            if p_count == 0:
                stats["unmatched"] += 1
                unmatched.append({"paulose_id": str(p_id), "unique_links": p_link})
                log.warning(f"[UNMATCHED] _id={p_id} | link={p_link}")
            else:
                stats["skipped_ok"] += 1
            continue

        k_chunks = matched["chunks"]
        k_count  = matched["count"]

        if p_count == 0:
            log.info(f"[FILL]      _id={p_id} | +{k_count} chunks | {p_link}")
            stats["empty_filled"] += 1
        elif k_count > p_count:
            log.info(f"[OVERWRITE] _id={p_id} | {p_count}→{k_count} | {p_link}")
            stats["overwritten"] += 1
        else:
            stats["skipped_ok"] += 1
            continue

        if not dry_run:
            bulk_ops.append(UpdateOne(
                {"_id": p_id},
                {"$set": {
                    "chunks":           k_chunks,
                    "chunk_count":      k_count,
                    "chunks_source":    f"mapped_from_{kritika_col_name}",
                    "chunks_mapped_at": datetime.utcnow().isoformat(),
                }},
            ))

        if len(bulk_ops) >= batch_size:
            result = paulose_col.bulk_write(bulk_ops, ordered=False)
            log.info(f"  Batch flushed | modified={result.modified_count}")
            bulk_ops = []

    if bulk_ops and not dry_run:
        result = paulose_col.bulk_write(bulk_ops, ordered=False)
        log.info(f"  Final batch | modified={result.modified_count}")

    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info(f"  Total scanned     : {stats['total']}")
    log.info(f"  Empty → filled    : {stats['empty_filled']}")
    log.info(f"  Partial → updated : {stats['overwritten']}")
    log.info(f"  Skipped (OK)      : {stats['skipped_ok']}")
    log.info(f"  Unmatched (logged): {stats['unmatched']}")
    log.info(f"  DRY_RUN           : {dry_run}")
    log.info("=" * 60)

    if unmatched:
        log.info("Unmatched doc links:")
        for u in unmatched:
            log.info(f"  {u['paulose_id']} | {u['unique_links']}")

    client.close()
    return 0


def add_args(sub):
    sub.add_argument("--dry-run",           action="store_true",
                     help="Simulate without writing")
    sub.add_argument("--source-collection", default=COLLECTION_KRITIKA)
    sub.add_argument("--target-collection", default=COLLECTION_PAULOSE)
    sub.add_argument("--batch-size",        type=int, default=CHUNK_BATCH_SIZE)
    sub.add_argument("--log-file",          default=None)
    sub.add_argument("--mongo-uri",         default=MONGO_URI_PROD)
