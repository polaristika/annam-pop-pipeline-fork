#!/usr/bin/env python3
"""
pop_pipeline.py  –  Unified CLI for the POP (Package of Practices) Pipeline
=============================================================================

PIPELINE STEPS
──────────────
  step1          DPT-2 PDF → JSON/Markdown  (Landing AI API)
  step2          JSON → MongoDB NDB schema  (batch upload)
  step3          Chunk mapping: New_Kritika → new_paulose_1
  step4          Generate BAAI/bge-large-en embeddings (GPU)
  migrate        Migrate existing DB docs to latest NDB schema
  upload-single  Normalize + upload one dpt2_result.json file
  cleanup        Strip chunk-mapping audit fields from new_paulose_1
  verify         Check a doc_id exists in MongoDB
  query          Full-text search across processed DPT-2 outputs

QUICK EXAMPLES
──────────────
  # Run the full pipeline end-to-end (dry-run upload & chunk-map)
  python pop_pipeline.py run-all --dry-run

  # Process garbled PDFs only
  python pop_pipeline.py step1 --limit 10 --verbose

  # Upload to MongoDB (dry-run first)
  python pop_pipeline.py step2 --dry-run
  python pop_pipeline.py step2

  # Copy chunks from Kritika → Paulose
  python pop_pipeline.py step3 --dry-run
  python pop_pipeline.py step3

  # Generate embeddings (needs GPU + sentence-transformers)
  python pop_pipeline.py step4

  # Migrate existing DB to new NDB schema
  python pop_pipeline.py migrate --collection New_Kritika

  # Upload / test a single JSON file
  python pop_pipeline.py upload-single path/to/dpt2_result.json --dry-run
  python pop_pipeline.py upload-single path/to/dpt2_result.json --save-normalized

  # Verify a doc was uploaded
  python pop_pipeline.py verify <doc_id>

  # Clean chunk-mapping audit fields so step3 can re-run clean
  python pop_pipeline.py cleanup --dry-run
  python pop_pipeline.py cleanup

  # Query mode (find top matches for a crop/state)
  python pop_pipeline.py query --state Haryana --crop wheat
"""

import argparse
import sys
from pathlib import Path

# Make sure sub-packages are importable from the project root
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pop_pipeline",
        description="POP Pipeline – DPT-2 → MongoDB → Embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    # ── step1: DPT-2 batch process ─────────────────────────────────────────────
    s1 = subs.add_parser("step1", help="DPT-2: PDF → JSON/MD via Landing AI API")
    from dpt2_processing.batch_process import add_args as s1_args
    s1_args(s1)

    # ── step2: NDB upload ──────────────────────────────────────────────────────
    s2 = subs.add_parser("step2", help="NDB: Upload processed JSON → MongoDB")
    from ndb.upload import add_args as s2_args
    s2_args(s2)

    # ── step3: chunk mapping ───────────────────────────────────────────────────
    s3 = subs.add_parser("step3", help="Chunk map: Kritika → Paulose")
    from ndb.chunk_map import add_args as s3_args
    s3_args(s3)

    # ── step4: embeddings ──────────────────────────────────────────────────────
    s4 = subs.add_parser("step4", help="Generate BAAI/bge-large-en embeddings (GPU)")
    from embeddings.generate import add_args as s4_args
    s4_args(s4)

    # ── migrate: schema migration ──────────────────────────────────────────────
    sm = subs.add_parser("migrate", help="Migrate existing DB docs to new NDB schema")
    sm.add_argument("--collection", default="New_Kritika")
    sm.add_argument("--mongo-uri",  default=None)
    sm.add_argument("--dry-run",    action="store_true")

    # ── upload-single: normalize + upload one JSON ─────────────────────────────
    from ndb.utils import add_args_upload_single, add_args_cleanup_paulose, add_args_verify
    su = subs.add_parser("upload-single",
                         help="Normalize and upload a single dpt2_result.json")
    add_args_upload_single(su)

    # ── cleanup: strip audit fields from Paulose ───────────────────────────────
    sc = subs.add_parser("cleanup",
                         help="Remove chunk-mapping audit fields from new_paulose_1")
    add_args_cleanup_paulose(sc)

    # ── verify: check a doc_id in DB ──────────────────────────────────────────
    sv = subs.add_parser("verify", help="Check a doc_id exists in MongoDB")
    add_args_verify(sv)

    # ── query: search existing outputs ────────────────────────────────────────
    sq = subs.add_parser("query", help="Search processed DPT-2 outputs")
    sq.add_argument("--query",  default="", help="Free-form query text")
    sq.add_argument("--state",  default="")
    sq.add_argument("--crop",   default="")
    sq.add_argument("--top-k",  type=int, default=5)

    # ── run-all: end-to-end ────────────────────────────────────────────────────
    ra = subs.add_parser("run-all", help="Run steps 1 → 2 → 3 → 4 sequentially")
    ra.add_argument("--dry-run",    action="store_true",
                    help="Dry-run for steps 2 and 3 (step1 still runs; step4 skipped)")
    ra.add_argument("--skip-step1", action="store_true", help="Skip PDF processing")
    ra.add_argument("--skip-step4", action="store_true", help="Skip embedding generation")
    ra.add_argument("--state",      default=None, help="Limit upload to one state")

    return parser


# ── Dispatch helpers ───────────────────────────────────────────────────────────

def cmd_migrate(args) -> int:
    from config.settings import MONGO_URI_PROD, DB_NAME, CENTRAL_KEYWORDS
    import hashlib
    from pymongo import MongoClient

    mongo_uri   = args.mongo_uri or MONGO_URI_PROD
    col_name    = args.collection
    dry_run     = args.dry_run

    def _assign_origin(doc):
        org = doc.get("meta_data", {}).get("organization_name", "").upper()
        if any(kw in org for kw in CENTRAL_KEYWORDS):
            return "central"
        existing = doc.get("doc_origin", "")
        if existing and len(existing) < 50 and "http" not in existing and "," not in existing:
            return existing
        loc = doc.get("meta_data", {}).get("organization_location", "")
        return loc.split(",")[-1].strip() if "," in loc else loc or "Unknown"

    def _clean_meta(meta):
        return {k: meta.get(k, d) for k, d in [
            ("language", "English"), ("organization_name", ""),
            ("organization_location", ""), ("season", "All"),
        ]}

    def _primary_link(doc):
        return (doc.get("unique_links") or doc.get("unique_link") or
                (doc.get("doc_links") or [""])[0] or "")

    def _fix_usage(usage, link, meta):
        fallback = meta.get("agri_expert_name", "dpt2_batch_process")
        return [{"doc_link":    e.get("doc_link", link), "state": e.get("state", ""),
                 "crop":        e.get("crop",  ""),
                 "verified_by": e.get("verified_by", fallback)} for e in usage]

    def _fix_chunks(chunks, doc_id):
        out = []
        for i, c in enumerate(chunks):
            content = c.get("chunk_content", "")
            out.append({"chunk_id": f"{doc_id}_{i}", "associated_doc_id": doc_id,
                        "embedding_vector": c.get("embedding_vector", []),
                        "chunk_content": content, "page_no": c.get("page_no", 1),
                        "_content_hash": hashlib.sha256(content.encode()).hexdigest()})
        return out

    client = MongoClient(mongo_uri)
    col    = client[DB_NAME][col_name]
    total  = col.count_documents({})
    print(f"Migrating {total} docs in '{col_name}'  (dry_run={dry_run})")

    updated = failed = 0
    for record in col.find({}):
        old_doc    = record.get("document", {})
        old_chunks = record.get("chunks", [])
        doc_id     = old_doc.get("doc_id", str(record["_id"]))
        try:
            link     = _primary_link(old_doc)
            old_meta = old_doc.get("meta_data", {})
            new_doc  = {
                "doc_id":       doc_id,
                "doc_name":     old_doc.get("doc_name", ""),
                "app_name":     old_doc.get("app_name", ""),
                "unique_links": link,
                "doc_links":    old_doc.get("doc_links", [link]),
                "doc_origin":   _assign_origin(old_doc),
                "meta_data":    _clean_meta(old_meta),
                "doc_usage":    _fix_usage(old_doc.get("doc_usage", []), link, old_meta),
            }
            new_chunks = _fix_chunks(old_chunks, doc_id)
            if not dry_run:
                col.update_one({"_id": record["_id"]},
                               {"$set": {"document": new_doc, "chunks": new_chunks}})
            print(f"  ✅ {doc_id} | chunks={len(new_chunks)} | origin={new_doc['doc_origin']}")
            updated += 1
        except Exception as e:
            print(f"  ❌ {doc_id}: {e}")
            failed += 1

    print(f"\nDone: {updated} updated | {failed} failed")
    client.close()
    return 0 if failed == 0 else 1


def cmd_query(args) -> int:
    query = args.query
    if not query and not args.state and not args.crop:
        print("Provide --query or --state/--crop")
        return 1
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "dpt2_orig",
            REPO_ROOT / "dpt2_processing" / "dpt2_batch_process.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        results = mod.query_documents(query, args.state, args.crop, top_k=args.top_k)
        state_v, crop_v = mod.infer_query_filters(query, args.state, args.crop)
        mod.print_query_results(results[:5], state_v, crop_v, query)
    except Exception as e:
        print(f"Query failed: {e}")
        return 1
    return 0


def cmd_run_all(args) -> int:
    """Sequential pipeline: step1 → step2 → step3 → step4"""
    import types

    print("\n" + "=" * 65)
    print("POP PIPELINE  –  Full Run")
    print("=" * 65 + "\n")

    results = {}

    # ── Step 1 ─────────────────────────────────────────────────────────────────
    if not args.skip_step1:
        print("\n▶ STEP 1: DPT-2 Batch Process")
        from dpt2_processing.batch_process import run as run1
        s1_args = types.SimpleNamespace(
            all=False, input_csv=None, limit=None, force=False, timeout=300,
            verbose=False, pdf_root=None, output_root=None, log_path=None,
            overwrite_log=False, strict_paths=False, missing_as_failure=False,
            lang_filter="", lang_priority="unsure,indic", skip=0,
            master_xlsx=None, link_map_xlsx=None,
        )
        results["step1"] = run1(s1_args)
    else:
        print("\n⏭  Skipping Step 1")

    # ── Step 2 ─────────────────────────────────────────────────────────────────
    print("\n▶ STEP 2: NDB Upload")
    from ndb.upload import run as run2
    s2_args = types.SimpleNamespace(
        base_path=None, output_xlsx=None, master_xlsx=None,
        dry_run=args.dry_run, state=args.state,
        collection=None, mongo_uri=None,
    )
    results["step2"] = run2(s2_args)

    # ── Step 3 ─────────────────────────────────────────────────────────────────
    print("\n▶ STEP 3: Chunk Mapping")
    from ndb.chunk_map import run as run3
    s3_args = types.SimpleNamespace(
        dry_run=args.dry_run, source_collection=None,
        target_collection=None, batch_size=None, log_file=None, mongo_uri=None,
    )
    results["step3"] = run3(s3_args)

    # ── Step 4 ─────────────────────────────────────────────────────────────────
    if not args.skip_step4 and not args.dry_run:
        print("\n▶ STEP 4: Generate Embeddings")
        from embeddings.generate import run as run4
        s4_args = types.SimpleNamespace(
            collections=None, device=None, batch_size=None, mongo_uri=None,
        )
        results["step4"] = run4(s4_args)
    else:
        print("\n⏭  Skipping Step 4 (dry-run or --skip-step4)")

    print("\n" + "=" * 65)
    print("PIPELINE COMPLETE")
    for step, code in results.items():
        status = "✅" if code == 0 else "❌"
        print(f"  {status}  {step}  (exit={code})")
    print("=" * 65)

    return max(results.values()) if results else 0


def main(argv=None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    from ndb.utils import run_upload_single, run_cleanup_paulose, run_verify
    dispatch = {
        "step1":         lambda: __import__("dpt2_processing.batch_process", fromlist=["run"]).run(args),
        "step2":         lambda: __import__("ndb.upload",     fromlist=["run"]).run(args),
        "step3":         lambda: __import__("ndb.chunk_map",  fromlist=["run"]).run(args),
        "step4":         lambda: __import__("embeddings.generate", fromlist=["run"]).run(args),
        "migrate":       lambda: cmd_migrate(args),
        "upload-single": lambda: run_upload_single(args),
        "cleanup":       lambda: run_cleanup_paulose(args),
        "verify":        lambda: run_verify(args),
        "query":         lambda: cmd_query(args),
        "run-all":       lambda: cmd_run_all(args),
    }
    return dispatch[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
