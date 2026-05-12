"""zoho-download: Download deduplicated PDFs from Zoho WorkDrive."""

import subprocess
import sys
from pathlib import Path

POP2_DIR     = Path(__file__).resolve().parents[2] / "pop_2"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers):
    parser = subparsers.add_parser(
        'zoho-download',
        help='Download deduplicated PDFs from Zoho WorkDrive',
        description=(
            'Downloads only the PDFs whose primary_link appears in the dedup output XLSX. '
            'Uses 8 parallel download threads with automatic token refresh. '
            'Skips files already downloaded. '
            'Run after: pop-cli dedup'
        )
    )
    parser.add_argument(
        '--links', metavar='XLSX',
        default='unique_urls.xlsx',
        help='XLSX with primary_link column (output of dedup step, default: unique_urls.xlsx)'
    )
    parser.add_argument(
        '--test', action='store_true',
        help='Test mode: download max 5 files'
    )
    parser.set_defaults(func=execute)


def execute(args):
    cmd = [sys.executable, str(POP2_DIR / "zoho_pdf_download_v2.py"), "--link", args.links]
    if args.test:
        cmd.append("--test")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    sys.exit(result.returncode)
