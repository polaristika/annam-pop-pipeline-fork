#!/bin/bash

MONGO_URI="mongodb+srv://paulose610_db_user:6kjuVpxUEoU2LhYj@cluster-rkp.vghajqu.mongodb.net/?appName=Cluster-rkp"
DB_NAME="ans_source_audit_db"
COLLECTION="answers"
UNIQUE_COLLECTION="unique_links"

# MODE options:
#   all     — run reflag pass then main processing loop (default)
#   reflag  — re-process flagged unique_link entries only
#   process — run main MongoDB loop only (skips reflag pass)
MODE="process"

python extract_unique_link_db.py \
  --mongo-uri "$MONGO_URI" \
  --db "$DB_NAME" \
  --collection "$COLLECTION" \
  --unique-collection "$UNIQUE_COLLECTION" \
  --mode "$MODE"
