#!/usr/bin/env python3
"""
Step 1: Exchange Zoho authorization code for access + refresh tokens.
Run this ONCE while the auth code is still valid (within 10 minutes).
Credentials are read from .pop_2_env at project root.
"""

import json
import os
from pathlib import Path

import requests


def _load_pop2_env():
    """Load .pop_2_env from project root into os.environ (existing vars take priority)."""
    candidates = [
        Path(__file__).resolve().parent.parent / ".pop_2_env",
        Path(".pop_2_env"),
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break


TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"


def exchange_code():
    _load_pop2_env()

    client_id     = os.environ.get("ZOHO_CLIENT_ID", "")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
    auth_code     = os.environ.get("ZOHO_AUTH_CODE", "")
    tokens_file   = os.environ.get("ZOHO_TOKENS_FILE", "zoho_tokens.json")

    if not client_id or not client_secret:
        print("ERROR: ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET must be set in .pop_2_env")
        return
    if not auth_code:
        print("ERROR: ZOHO_AUTH_CODE must be set in .pop_2_env (10-min TTL — paste fresh code)")
        return

    resp = requests.post(TOKEN_URL, params={
        "code":          auth_code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "grant_type":    "authorization_code",
    })
    data = resp.json()

    if "access_token" not in data:
        print("ERROR:", data)
        return

    data["client_id"]     = client_id
    data["client_secret"] = client_secret

    with open(tokens_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Success! Tokens saved to {tokens_file}")
    print("  access_token  :", data["access_token"][:20], "...")
    print("  refresh_token :", data.get("refresh_token", "N/A")[:20], "...")


if __name__ == "__main__":
    exchange_code()
