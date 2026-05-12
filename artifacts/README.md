# Artifacts Directory

Processing artifacts organized by phase.

## Structure

- `phase1_english/raw/` - Phase 1 extracted English PDFs (152 docs)
  - Each folder: {doc_id} (12-char hash)
  - Contains: doc.md, doc.json

- `phase2_indic/raw/` - Phase 2 extracted Indic PDFs (63 docs)
  - Each folder: {doc_name} (full document name)
  - Contains: doc.md, doc.json, doc_translated.md, doc_translated.json

- `phase2_indic/organized/` - Phase 2 organized by state
  - Grouped by metadata.State
  - Files: {Name}.json (translated), {Name}_original.json (Marathi/Tamil)
