"""ingest-chunks: Embed Phase 1 outputs and write chunks to MongoDB."""

import subprocess
import sys
from pathlib import Path

POP2_DIR     = Path(__file__).resolve().parents[2] / "pop_2"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers):
    parser = subparsers.add_parser(
        'ingest-chunks',
        help='Embed Phase 1 extraction outputs and write chunks to MongoDB',
        description=(
            'Iterates every folder under DATA_DIR (default: artifacts/phase1_english/), '
            'parses JSON outputs (Docling tree or flat content format), '
            'splits into 500-word sliding-window chunks, embeds with BAAI/bge-large-en '
            '(GPU if available), and writes chunks to the matching MongoDB document. '
            'Skips documents that already have chunks. '
            'Run after: pop-cli ingest-docs. '
            'Configure MONGO_URI, MONGO_DB, MONGO_COLLECTION, DATA_DIR in .pop_2_env.'
        )
    )
    parser.add_argument("--test", action="store_true", help="Process only 5 folders (for testing)")
    parser.set_defaults(func=execute)


def execute(args):
    cmd = [sys.executable, str(POP2_DIR / "create_chunks.py")]
    if args.test:
        cmd += ["--limit", "5"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    sys.exit(result.returncode)
