"""dedup: Scan Zoho sheets and deduplicate PDFs by perceptual hash."""

import subprocess
import sys
from pathlib import Path

POP2_DIR     = Path(__file__).resolve().parents[2] / "pop_2"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers):
    parser = subparsers.add_parser(
        'dedup',
        help='Extract unique PDF links from Zoho via perceptual hash deduplication',
        description=(
            'Scans every row in the Zoho workbook, downloads each file, and deduplicates '
            'by perceptual hash (pHash). Resumable — re-run after interruption to continue '
            'from the last checkpoint in output.csv. '
            'Writes output.csv (checkpoint) and unique_urls.xlsx (clean export). '
            'Paths configurable via .pop_2_env (DEDUP_OUTPUT_CSV, DEDUP_OUTPUT_XLSX).'
        )
    )
    parser.add_argument(
        '--test', action='store_true',
        help='Test mode: stop at 2 primary links with max 2 duplicates each'
    )
    parser.add_argument(
        '--workers', type=int, default=6, metavar='N',
        help='Parallel download workers (default: 6)'
    )
    parser.set_defaults(func=execute)


def execute(args):
    cmd = [sys.executable, str(POP2_DIR / "extract_unique_link.py")]
    if args.test:
        cmd.append("--test")
    cmd += ["--workers", str(args.workers)]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    sys.exit(result.returncode)
