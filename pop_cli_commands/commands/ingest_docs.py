"""ingest-docs: Create MongoDB document records from Zoho metadata."""

import subprocess
import sys
from pathlib import Path

POP2_DIR     = Path(__file__).resolve().parents[2] / "pop_2"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers):
    parser = subparsers.add_parser(
        'ingest-docs',
        help='Create MongoDB document records from Zoho metadata',
        description=(
            'Reads unique_urls.xlsx and MetadataMaster.xlsx from DATA_DIR '
            '(default: artifacts/phase1_english/) and inserts or updates one MongoDB document '
            'per unique PDF. doc_usage entries are deduplicated on (state, crop). '
            'Run after: pop-cli zoho-download and Phase 1 extraction. '
            'Configure MONGO_URI, MONGO_DB, MONGO_COLLECTION, DATA_DIR in .pop_2_env.'
        )
    )
    parser.add_argument("--test", action="store_true", help="Process only 5 documents (for testing)")
    parser.set_defaults(func=execute)


def execute(args):
    cmd = [sys.executable, str(POP2_DIR / "create_documents.py")]
    if args.test:
        cmd += ["--limit", "5"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    sys.exit(result.returncode)
