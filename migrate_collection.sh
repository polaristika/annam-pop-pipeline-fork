#!/bin/bash

# ===== CONFIG =====
PROD_URI="mongodb+srv://agriuser:agri_user_0991@staging.1fo96dy.mongodb.net/?retryWrites=true&w=majority&appName=staging"
TARGET_URI="mongodb+srv://riyamehtaatwork_db_user:riyamehtaatwork_db_user@ajrasakha.1af8ryy.mongodb.net/?appName=ajrasakha"

SOURCE_DB="agri_ai"
TARGET_DB="ans_source_audit_db"

COLLECTION="answers"

# Optional rename (set same as COLLECTION if no rename needed)
TARGET_COLLECTION="answers"

DUMP_DIR="./dump"

# ===== DUMP =====
echo "Starting dump from production..."

mongodump \
  --uri="$PROD_URI" \
  --db="$SOURCE_DB" \
  --collection="$COLLECTION" \
  --out="$DUMP_DIR"

if [ $? -ne 0 ]; then
  echo "❌ Dump failed"
  exit 1
fi

echo "✅ Dump completed"

# ===== RESTORE =====
echo "Starting restore to target cluster..."

mongorestore \
  --uri="$TARGET_URI" \
  --nsFrom="$SOURCE_DB.$COLLECTION" \
  --nsTo="$TARGET_DB.$TARGET_COLLECTION" \
  "$DUMP_DIR"

if [ $? -ne 0 ]; then
  echo "❌ Restore failed"
  exit 1
fi

echo "✅ Restore completed successfully"