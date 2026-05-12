"""zoho-auth: Exchange a Zoho OAuth authorization code for access/refresh tokens."""

import subprocess
import sys
from pathlib import Path

POP2_DIR     = Path(__file__).resolve().parents[2] / "pop_2"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers):
    parser = subparsers.add_parser(
        'zoho-auth',
        help='Exchange Zoho OAuth code for access/refresh tokens (run once)',
        description=(
            'Reads ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_AUTH_CODE from .pop_2_env '
            'and saves tokens to zoho_tokens.json. '
            'The auth code has a 10-minute TTL — paste it into .pop_2_env before running.'
        )
    )
    parser.set_defaults(func=execute)


def execute(args):
    cmd = [sys.executable, str(POP2_DIR / "zoho_token_exchange.py")]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    sys.exit(result.returncode)
