# DPT-2 Processing Pipeline

This directory contains scripts and utilities for processing unprocessed PDFs using Landing AI DPT-2 API. This is a temporary workflow to accelerate data extraction for all remaining files. After this, the main open-source pipeline will resume.

## Structure

- `unprocessed_pdfs.csv` — List of all 337 unprocessed PDFs (same columns as `pdf_inventory.csv`)
- `garbled_pdfs.csv` — List of 90 garbled PDFs to process first (garbled_detected == True)
- `processing_log.txt` — Log of DPT-2 processing operations
- `code/` — Scripts for DPT-2 API interaction, downloading results, and conversion to project schema
- `processed_data/` — Final outputs, organized by state and PDF name, containing Markdown and JSON in project format

## Workflow

### Phase 1: Process Garbled Files First
1. Use `garbled_pdfs.csv` as the input list for initial DPT-2 batch processing.
2. Use scripts in `code/` to:
   - Submit PDFs to DPT-2
   - Download Markdown and JSON results
   - Convert results to project schema
   - Store in `processed_data/{STATE}/{PDF_NAME}/`

### Scripts

**`code/extract_garbled_pdfs.py`** - Filter garbled files from unprocessed_pdfs.csv

**`code/dpt2_batch_process.py`** - Main batch processing script
- Reads `garbled_pdfs.csv` (or `unprocessed_pdfs.csv` for all files)
- Calls Landing AI DPT-2 API for each PDF
- Saves results to `processed_data/{state}/{pdf_name}/dpt2_result.{md,json}`
- Logs all operations to `processing_log.txt`

**Setup:**
```bash
export DPT2_API_KEY="your-api-key-here"
```

**Usage:**
```bash
# Process garbled files first
python3 dpt2_processing/code/dpt2_batch_process.py
```

**Note:** This workflow is not part of the main open-source project and is for temporary use only.
