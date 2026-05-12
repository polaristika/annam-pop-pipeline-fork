import csv
import json
import re
import time

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

INPUT_CSV  = "temp3(1).csv"
OUTPUT_CSV = "temp2.csv"
TOKENS_FILE = "zoho_tokens.json"
WD_BASE    = "https://workdrive.zoho.in/api/v1"
TIMEOUT    = (10, 30)

# ── Load output.csv into a flat set of all known links ──────────────────────
known_links: set[str] = set()
try:
    with open("output.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("primary_link"):
                known_links.add(row["primary_link"].strip())
    print(f"Loaded {len(known_links)} known links from output.csv")
except FileNotFoundError:
    print("[WARN] output.csv not found — in_output will always be False")

# ── Zoho auth ────────────────────────────────────────────────────────────────
with open(TOKENS_FILE) as f:
    tokens = json.load(f)

_ACCESS_TOKEN       = tokens["access_token"]
_REFRESH_TOKEN      = tokens.get("refresh_token", "")
_CLIENT_ID          = tokens.get("client_id", "")
_CLIENT_SECRET      = tokens.get("client_secret", "")
_token_refreshed_at = 0.0

session = requests.Session()
session.headers.update({"Authorization": f"Zoho-oauthtoken {_ACCESS_TOKEN}"})
retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
session.mount("https://", HTTPAdapter(max_retries=retry))

_FILE_ID_RE = re.compile(r'/file/([a-zA-Z0-9]+)')


def _refresh_token():
    global _ACCESS_TOKEN, _token_refreshed_at
    if time.time() - _token_refreshed_at < 3500 or not _REFRESH_TOKEN:
        return False
    try:
        resp = requests.post(
            "https://accounts.zoho.in/oauth/v2/token",
            params={"refresh_token": _REFRESH_TOKEN, "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET, "grant_type": "refresh_token"},
            timeout=(10, 30),
        )
        new_token = resp.json().get("access_token")
        if not new_token:
            return False
        _ACCESS_TOKEN = new_token
        session.headers.update({"Authorization": f"Zoho-oauthtoken {new_token}"})
        tokens["access_token"] = new_token
        with open(TOKENS_FILE, "w") as f:
            json.dump(tokens, f, indent=2)
        _token_refreshed_at = time.time()
        return True
    except Exception:
        return False


def is_accessible(url: str) -> bool:
    m = _FILE_ID_RE.search(url)
    if not m:
        return False
    file_id = m.group(1)
    wd_base = "https://workdrive.zohoexternal.in/api/v1" if "zohoexternal" in url else WD_BASE
    dl_url  = f"{wd_base}/download/{file_id}"
    _refreshed = False
    for attempt in range(2):
        try:
            resp = session.get(dl_url, stream=True, timeout=TIMEOUT)
            resp.close()
        except requests.exceptions.RequestException:
            return False
        if resp.status_code == 401 and not _refreshed:
            _refresh_token()
            _refreshed = True
            continue
        ct = resp.headers.get("Content-Type", "")
        return resp.status_code == 200 and "json" not in ct and "html" not in ct
    return False


# ── Main loop ────────────────────────────────────────────────────────────────
with open(INPUT_CSV, newline="") as f:
    rows = list(csv.DictReader(f))

results = []
for row in tqdm(rows, desc="Checking links"):
    link        = row.get("source", "").strip()
    source_name = row.get("source_name", "")
    if not link:
        continue
    in_output  = link in known_links
    accessible = is_accessible(link)
    results.append({
        "source_name": source_name,
        "link":        link,
        "in_output":   in_output,
        "accessible":  accessible,
    })
    print(f"{'IN_OUTPUT' if in_output else 'MISSING  '} | {'OK  ' if accessible else 'FAIL'} | {link}")

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["source_name", "link", "in_output", "accessible"])
    writer.writeheader()
    writer.writerows(results)

in_out_count  = sum(1 for r in results if r["in_output"])
accessible_count = sum(1 for r in results if r["accessible"])
print(f"\nDone. {len(results)} links checked → {OUTPUT_CSV}")
print(f"  in output.csv : {in_out_count}")
print(f"  accessible    : {accessible_count}")
print(f"  missing+broken: {len(results) - in_out_count} missing, {len(results) - accessible_count} inaccessible")
