from __future__ import annotations
import tempfile
import shutil
from googletrans import Translator
def translate_markdown_to_english(markdown: str, logger: logging.Logger) -> str:
    try:
        translator = Translator()
        # googletrans has a 5000 char limit per call, so split if needed
        chunks = [markdown[i:i+4500] for i in range(0, len(markdown), 4500)]
        translated = []
        for chunk in chunks:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = translator.translate(chunk, dest='en')
                    translated.append(result.text)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        logger.warning(f"Translation failed after {max_retries} attempts: {str(e)[:80]}")
                        translated.append(chunk)
        return '\n'.join(translated)
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        return markdown

def split_pdf_by_pages(pdf_path: Path, max_pages: int = 98, logger: Optional[logging.Logger] = None) -> list:
    """
    Splits a PDF into chunks of max_pages. Returns list of temp file paths.
    """
    from PyPDF2 import PdfReader, PdfWriter
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    if total_pages <= max_pages:
        return [pdf_path]
    temp_files = []
    for start in range(0, total_pages, max_pages):
        writer = PdfWriter()
        for i in range(start, min(start+max_pages, total_pages)):
            writer.add_page(reader.pages[i])
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_fd)
        with open(temp_path, 'wb') as f:
            writer.write(f)
        temp_files.append(Path(temp_path))
        if logger:
            logger.info(f"Created PDF chunk: {temp_path} [{start+1}-{min(start+max_pages, total_pages)}]")
    return temp_files

#!/usr/bin/env python3
"""
DPT-2 batch processor and retrieval helper.

Batch mode reads `garbled_pdfs.csv` by default, submits each PDF to a
configurable Landing AI DPT-2 endpoint, and writes outputs to
`dpt2_processing/processed_data/{state}/{pdf_name}/dpt2_result.{md,json}`.

Query mode scans existing DPT-2 JSON outputs, filters them by state/crop,
and returns the top 5 matches with score >= 0.8.
"""
import tempfile
import shutil
from deep_translator import GoogleTranslator
import argparse
import base64
import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pandas as pd
import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
DPT2_ROOT = REPO_ROOT / "dpt2_processing"
DEFAULT_GARBLED_CSV = DPT2_ROOT / "garbled_pdfs.csv"
DEFAULT_UNPROCESSED_CSV = DPT2_ROOT / "unprocessed_pdfs.csv"
PROCESSED_ROOT = DPT2_ROOT / "processed_data"
LOG_PATH = DPT2_ROOT / "processing_log.txt"

STATE_PATTERN = re.compile(r"\bstate\s*[:=]\s*['\"]?([A-Za-z][A-Za-z\s.-]*)", re.IGNORECASE)
CROP_PATTERN = re.compile(r"\bcrop\s*[:=]\s*['\"]?([A-Za-z][A-Za-z\s.-]*)", re.IGNORECASE)


@dataclass
class MetadataRecord:
    primary_link: str = ""
    crop: str = ""
    state: str = ""
    language: str = ""
    season: str = ""
    organization_name: str = ""
    organization_location: str = ""
    format_name: str = ""
    agri_expert_name: str = ""
    source_sheet: str = ""


@dataclass
class ApiKeyManager:
    keys: List[str]
    auth_scheme: str = ""
    index: int = 0

    def _build_auth_header(self, api_key: str) -> str:
        scheme = normalize_text(self.auth_scheme).lower()
        if scheme == "basic":
            return f"Basic {api_key}"
        if scheme == "bearer":
            return f"Bearer {api_key}"
        if api_key.lower().startswith("basic ") or api_key.lower().startswith("bearer "):
            return api_key

        use_basic = False
        try:
            decoded = base64.b64decode(api_key + "===", validate=False).decode("utf-8", errors="ignore")
            use_basic = ":" in decoded
        except Exception:
            use_basic = False
        return f"Basic {api_key}" if use_basic else f"Bearer {api_key}"

    def current_key(self) -> str:
        if not self.keys:
            return ""
        idx = self.index % len(self.keys)
        return self.keys[idx]

    def current_auth_header(self) -> str:
        key = self.current_key()
        if not key:
            return ""
        return self._build_auth_header(key)

    def rotate(self) -> bool:
        if len(self.keys) <= 1:
            return False
        self.index = (self.index + 1) % len(self.keys)
        return True


def setup_logging(verbose: bool = False, log_path: Path = LOG_PATH, overwrite_log: bool = False) -> logging.Logger:
    logger = logging.getLogger("dpt2_batch_process")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(stream_handler)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="w" if overwrite_log else "a")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def slugify(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]", "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "unknown"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_state(value: Any) -> str:
    return slugify(normalize_text(value))


def safe_doc_id(pdf_path: Path) -> str:
    return hashlib.md5(str(pdf_path).encode("utf-8")).hexdigest()[:12]


def normalize_token(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9]+", "", lowered)
    return lowered


def normalize_name_key(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""

    base = Path(text).name.lower()
    base = re.sub(r"\.pdf$", "", base)
    base = re.sub(r"-[a-z0-9]{12,}$", "", base)
    base = re.sub(r"\.pdf", "", base)
    base = re.sub(r"\bpop\b", "", base)
    base = re.sub(r"[^a-z0-9]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def normalize_url(url: Any) -> str:
    text = normalize_text(url)
    if not text:
        return ""
    text = text.strip().strip("\"'")
    if text.lower() in {"nan", "none", "null", "-"}:
        return ""
    if not text.lower().startswith(("http://", "https://")):
        return ""

    split = urlsplit(text)
    query = parse_qs(split.query, keep_blank_values=True)
    filtered_items = [(k, v) for k, vals in query.items() if not k.lower().startswith("utm_") for v in vals]
    normalized_query = urlencode(sorted(filtered_items))
    normalized = urlunsplit((split.scheme.lower(), split.netloc.lower(), split.path, normalized_query, ""))
    return normalized


def split_duplicate_links(value: Any) -> List[str]:
    text = normalize_text(value)
    if not text:
        return []

    # Handle list-like strings and plain delimiter-separated cells.
    cleaned = text.strip().strip("[]")
    cleaned = cleaned.replace("\"", " ").replace("'", " ")
    parts = re.split(r"[\n,;|]+", cleaned)
    links: List[str] = []
    for part in parts:
        link = normalize_url(part)
        if link:
            links.append(link)
    return links


def first_present(row: Dict[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        if key in row:
            value = normalize_text(row.get(key))
            if value and value != "-":
                return value
    return ""


def split_org_name_location(value: str) -> Tuple[str, str]:
    if not value:
        return "", ""
    parts = [p.strip() for p in re.split(r"\s*[|,]\s*", value) if p and p.strip()]
    if len(parts) >= 2:
        return parts[0], ", ".join(parts[1:])
    return value.strip(), ""


def build_primary_link_lookup(link_map_xlsx: Optional[Path], logger: logging.Logger) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    if not link_map_xlsx:
        return lookup
    if not link_map_xlsx.exists():
        logger.warning(f"Link mapping workbook not found: {link_map_xlsx}")
        return lookup

    try:
        frame = pd.read_excel(link_map_xlsx)
    except Exception as exc:
        logger.warning(f"Unable to read link mapping workbook {link_map_xlsx}: {exc}")
        return lookup

    columns = {str(col).strip().lower(): col for col in frame.columns}
    primary_col = columns.get("primary_link")
    duplicates_col = columns.get("duplicates")
    if primary_col is None:
        logger.warning(f"Workbook {link_map_xlsx} does not contain 'primary_link' column")
        return lookup

    for _, rec in frame.iterrows():
        primary = normalize_url(rec.get(primary_col))
        if not primary:
            continue
        lookup[primary] = primary

        if duplicates_col is not None:
            for dup in split_duplicate_links(rec.get(duplicates_col)):
                lookup[dup] = primary

    logger.info(f"Loaded {len(lookup)} link normalization entries from {link_map_xlsx}")
    return lookup


def canonical_link(raw_link: Any, primary_lookup: Dict[str, str]) -> str:
    normalized = normalize_url(raw_link)
    if not normalized:
        return ""
    return primary_lookup.get(normalized, normalized)


def build_master_metadata_index(
    master_xlsx: Optional[Path],
    primary_lookup: Dict[str, str],
    logger: logging.Logger,
) -> Tuple[Dict[str, MetadataRecord], Dict[str, MetadataRecord]]:
    by_link: Dict[str, MetadataRecord] = {}
    by_name: Dict[str, MetadataRecord] = {}

    if not master_xlsx:
        return by_link, by_name
    if not master_xlsx.exists():
        logger.warning(f"Master metadata workbook not found: {master_xlsx}")
        return by_link, by_name

    try:
        workbook = pd.read_excel(master_xlsx, sheet_name=None)
    except Exception as exc:
        logger.warning(f"Unable to read master workbook {master_xlsx}: {exc}")
        return by_link, by_name

    for sheet_name, frame in workbook.items():
        if frame is None or frame.empty:
            continue
        records = frame.fillna("").to_dict(orient="records")
        for rec in records:
            row = {str(k).strip(): v for k, v in rec.items()}
            link_value = first_present(row, ["Link", "link", "URL", "Url"])
            normalized_link = canonical_link(link_value, primary_lookup)

            state_value = first_present(row, ["In which States it's Used for", "State"])
            crop_value = first_present(row, ["In which Crops it's Used for", "Crop"])
            language_value = first_present(row, ["Language"])
            format_value = first_present(row, ["Format"])
            season_value = first_present(row, ["Season"])
            org_value = first_present(row, ["Organization Name, with Location", "Headquater"])
            agri_expert = first_present(row, ["Agri Expert name"])
            org_name, org_location = split_org_name_location(org_value)

            record = MetadataRecord(
                primary_link=normalized_link,
                crop=crop_value,
                state=state_value,
                language=language_value,
                season=season_value,
                organization_name=org_name,
                organization_location=org_location,
                format_name=format_value,
                agri_expert_name=agri_expert,
                source_sheet=sheet_name,
            )

            if normalized_link and normalized_link not in by_link:
                by_link[normalized_link] = record

            for name_key in ("Name of POPs", "Show Name"):
                token = normalize_name_key(row.get(name_key))
                if token and token not in by_name:
                    by_name[token] = record

    logger.info(
        f"Loaded master metadata index from {master_xlsx}: "
        f"{len(by_link)} link keys, {len(by_name)} name keys"
    )
    return by_link, by_name


def find_metadata_for_row(
    row: Dict[str, str],
    pdf_path: Path,
    link_index: Dict[str, MetadataRecord],
    name_index: Dict[str, MetadataRecord],
    primary_lookup: Dict[str, str],
) -> Optional[MetadataRecord]:
    # First preference: map by file-name/title against master sheet.
    file_tokens = {
        normalize_name_key(pdf_path.name),
        normalize_name_key(pdf_path.stem),
        normalize_name_key(Path(normalize_text(row.get("file_path"))).name),
        normalize_name_key(Path(normalize_text(row.get("file_path"))).stem),
    }
    for token in file_tokens:
        if token and token in name_index:
            return name_index[token]

    # Fallback: explicit link fields from CSV, normalized to primary link.
    candidate_links = [
        row.get("doc_link"),
        row.get("link"),
        row.get("Link"),
        row.get("url"),
        row.get("URL"),
    ]
    for value in candidate_links:
        link = canonical_link(value, primary_lookup)
        if link and link in link_index:
            return link_index[link]

    return None


def build_api_key_manager() -> ApiKeyManager:
    combined = normalize_text(os.environ.get("DPT2_API_KEYS"))
    single = normalize_text(os.environ.get("DPT2_API_KEY"))
    keys: List[str] = []
    if combined:
        keys.extend([part.strip() for part in combined.split(",") if part.strip()])
    if single:
        keys.append(single)

    deduped: List[str] = []
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)

    if not deduped:
        raise RuntimeError("DPT2_API_KEY or DPT2_API_KEYS must be set.")

    return ApiKeyManager(keys=deduped, auth_scheme=normalize_text(os.environ.get("DPT2_AUTH_SCHEME")))


def is_credit_or_rate_limit_error(response: requests.Response) -> bool:
    # Returns True if it's a rate-limit or credit error (legacy)
    # Deprecated: use classify_api_error instead
    if response.status_code in (402, 429):
        return True
    body = (response.text or "").lower()
    markers = ("insufficient", "quota", "credit", "rate limit", "too many requests")
    return any(marker in body for marker in markers)

# New: classify API error for smarter handling
def classify_api_error(response: requests.Response) -> str:
    """
    Returns one of: 'rate_limit', 'credit', 'other', or 'none'
    """
    if response.status_code == 429:
        # Check if it's a rate limit or credit exhaustion
        body = (response.text or "").lower()
        if "rate limit" in body or "too many requests" in body:
            return "rate_limit"
        if "credit" in body or "quota" in body or "insufficient" in body:
            return "credit"
        return "rate_limit"  # fallback
    if response.status_code == 402:
        return "credit"
    return "none"


def sort_rows_by_lang_priority(rows: List[Dict[str, str]], lang_priority: Sequence[str]) -> List[Dict[str, str]]:
    if not rows:
        return rows
    priority_map = {normalize_text(value).lower(): idx for idx, value in enumerate(lang_priority)}

    def sort_key(row: Dict[str, str]) -> Tuple[int, str]:
        lang = normalize_text(row.get("lang_guess")).lower()
        return (priority_map.get(lang, 999), normalize_text(row.get("file_path")).lower())

    return sorted(rows, key=sort_key)


def read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _unique_paths(paths: List[Path]) -> List[Path]:
    unique: List[Path] = []
    seen = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def resolve_pdf_path(
    row: Dict[str, str],
    pdf_root: Optional[Path] = None,
    strict_paths: bool = False,
) -> Tuple[Optional[Path], List[Path]]:
    raw_path = normalize_text(row.get("file_path"))
    attempted: List[Path] = []

    if raw_path:
        candidates = []
        raw_candidate = Path(raw_path)
        candidates.append(raw_candidate)

        if not raw_candidate.is_absolute():
            candidates.append(REPO_ROOT / raw_candidate)

        if pdf_root and not raw_candidate.is_absolute():
            candidates.append(pdf_root / raw_candidate)

            # For new datasets, allow CSV paths that still contain legacy prefixes.
            for marker in ("data/raw/", "data/", "POP Bank/"):
                if marker in raw_path:
                    tail = raw_path.split(marker, 1)[-1].lstrip("/\\")
                    candidates.append(pdf_root / tail)

            candidates.append(pdf_root / raw_candidate.name)

        if not strict_paths and "data/raw" in raw_path:
            tail = raw_path.split("data/raw", 1)[-1].lstrip("/\\")
            candidates.append(REPO_ROOT / "data" / "raw" / tail)

        if not strict_paths and "POP Bank" in raw_path:
            tail = raw_path.split("POP Bank", 1)[-1].lstrip("/\\")
            candidates.append(REPO_ROOT / "data" / "raw" / "POP Bank" / tail)

        candidates = _unique_paths(candidates)
        attempted.extend(candidates)
        for candidate in candidates:
            if candidate.exists():
                return candidate, attempted

    file_name = Path(normalize_text(row.get("file_path"))).name if normalize_text(row.get("file_path")) else ""
    if file_name:
        search_roots: List[Path] = []
        if pdf_root:
            search_roots.append(pdf_root)
        if not strict_paths:
            search_roots.append(REPO_ROOT)

        for root in _unique_paths(search_roots):
            try:
                for candidate in root.rglob(file_name):
                    attempted.append(candidate)
                    if candidate.is_file():
                        return candidate, attempted
            except Exception:
                continue

    return None, _unique_paths(attempted)


def infer_query_filters(query: str, explicit_state: Optional[str], explicit_crop: Optional[str]) -> Tuple[str, str]:
    state = normalize_text(explicit_state)
    crop = normalize_text(explicit_crop)

    if not state:
        match = STATE_PATTERN.search(query)
        if match:
            state = match.group(1).strip().strip(".,;:")

    if not crop:
        match = CROP_PATTERN.search(query)
        if match:
            crop = match.group(1).strip().strip(".,;:")

    return state, crop


def load_json_file(json_path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_doc_usage(document_block: Dict[str, Any]) -> List[Dict[str, Any]]:
    usage = document_block.get("doc_usage")
    if isinstance(usage, list):
        return [item for item in usage if isinstance(item, dict)]
    if isinstance(usage, dict):
        return [usage]
    return []


def extract_chunks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    chunks = payload.get("chunks")
    if isinstance(chunks, list):
        return [item for item in chunks if isinstance(item, dict)]

    chunk = payload.get("chunk")
    if isinstance(chunk, dict):
        return [chunk]

    return []


def text_for_search(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    if document:
        parts.append(normalize_text(document.get("doc_name")))
        parts.append(normalize_text(document.get("app_name")))
        parts.append(normalize_text(document.get("doc_origin")))
        meta = document.get("meta_data") if isinstance(document.get("meta_data"), dict) else {}
        for value in meta.values():
            parts.append(normalize_text(value))
        for usage in extract_doc_usage(document):
            parts.append(normalize_text(usage.get("state")))
            parts.append(normalize_text(usage.get("crop")))
            parts.append(normalize_text(usage.get("verified_by")))

    for chunk in extract_chunks(payload):
        parts.append(normalize_text(chunk.get("chunk_content")))

    return " ".join(part for part in parts if part)


def match_state_crop(payload: Dict[str, Any], state: str, crop: str) -> bool:
    if not state or not crop:
        return False

    document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
    doc_origin = normalize_text(document.get("doc_origin")).lower()
    usage_rows = extract_doc_usage(document)

    def usage_matches(usage_row: Dict[str, Any]) -> bool:
        return (
            normalize_text(usage_row.get("state")).strip().lower() == state.strip().lower()
            and normalize_text(usage_row.get("crop")).strip().lower() == crop.strip().lower()
        )

    if not usage_rows:
        return False

    if doc_origin:
        if doc_origin == "central" or doc_origin == "state" or doc_origin != state.lower():
            return any(usage_matches(row) for row in usage_rows)

    return any(usage_matches(row) for row in usage_rows)


def score_payload(payload: Dict[str, Any], state: str, crop: str, query_terms: Sequence[str]) -> float:
    if not match_state_crop(payload, state, crop):
        return 0.0

    search_text = text_for_search(payload).lower()
    if not search_text:
        return 0.8

    hits = 0
    terms = [term.lower() for term in query_terms if term]
    for term in terms:
        if term in search_text:
            hits += 1

    if not terms:
        return 0.8

    bonus = min(0.2, 0.2 * (hits / len(terms)))
    return round(0.8 + bonus, 4)


def query_documents(query: str, state: Optional[str], crop: Optional[str], top_k: int = 5) -> List[Dict[str, Any]]:
    state_value, crop_value = infer_query_filters(query, state, crop)
    if not state_value or not crop_value:
        raise ValueError("Query mode requires a state and crop, either explicitly or in the query text.")

    query_terms = [state_value, crop_value] + re.findall(r"[A-Za-z][A-Za-z\-']+", query)
    results: List[Dict[str, Any]] = []

    if not PROCESSED_ROOT.exists():
        return results

    for json_path in PROCESSED_ROOT.rglob("dpt2_result.json"):
        payload = load_json_file(json_path)
        if not payload:
            continue

        score = score_payload(payload, state_value, crop_value, query_terms)
        if score < 0.8:
            continue

        document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
        results.append({
            "score": score,
            "json_path": str(json_path),
            "doc_id": normalize_text(document.get("doc_id")) or json_path.parent.name,
            "doc_name": normalize_text(document.get("doc_name")) or json_path.parent.name,
            "state": state_value,
            "crop": crop_value,
            "doc_origin": normalize_text(document.get("doc_origin")),
        })

    results.sort(key=lambda item: (-item["score"], item["doc_name"].lower()))
    return results[:top_k]


def parse_api_response(response: requests.Response) -> Tuple[str, Dict[str, Any]]:
    content_type = response.headers.get("content-type", "").lower()
    raw_text = response.text or ""

    if "application/json" in content_type:
        payload = response.json()
        if isinstance(payload, dict):
            markdown = normalize_text(
                payload.get("markdown")
                or payload.get("result_markdown")
                or payload.get("text")
                or payload.get("content")
            )
            if not markdown:
                markdown = raw_text.strip()
            return markdown, payload

        return raw_text.strip(), {"raw_response": payload}

    try:
        payload = response.json()
        if isinstance(payload, dict):
            markdown = normalize_text(
                payload.get("markdown")
                or payload.get("result_markdown")
                or payload.get("text")
                or payload.get("content")
            )
            if not markdown:
                markdown = raw_text.strip()
            return markdown, payload
    except Exception:
        pass

    return raw_text.strip(), {"raw_response": raw_text.strip()}


def build_project_json(
    row: Dict[str, str],
    pdf_path: Path,
    markdown: str,
    raw_payload: Dict[str, Any],
    state: str,
    metadata: Optional[MetadataRecord],
) -> Dict[str, Any]:
    pdf_name = pdf_path.stem
    doc_id = normalize_text(row.get("doc_id")) or safe_doc_id(pdf_path)
    crop = normalize_text(row.get("crop")) or (metadata.crop if metadata else "")
    meta_language = (
        (metadata.language if metadata else "")
        or normalize_text(row.get("lang_guess"))
        or normalize_text(row.get("language"))
        or "eng"
    )
    metadata_link = metadata.primary_link if metadata else ""
    fallback_doc_link = normalize_text(row.get("doc_link"))
    if not metadata_link:
        fallback_doc_link = canonical_link(fallback_doc_link, {}) or str(pdf_path)

    document = {
        "doc_id": doc_id,
        "doc_name": pdf_name,
        "app_name": normalize_text(row.get("app_name")) or pdf_name.replace("_", " ").replace("-", " ").strip(),
        "doc_link": metadata_link or fallback_doc_link,
        "doc_origin": normalize_text(row.get("doc_origin")) or (metadata.state if metadata else "") or state,
        "meta_data": {
            "language": meta_language,
            "organization_name": normalize_text(row.get("organization_name")) or (metadata.organization_name if metadata else ""),
            "organization_location": (
                normalize_text(row.get("organization_location"))
                or normalize_text(row.get("organization_locatio"))
                or (metadata.organization_location if metadata else "")
            ),
            "season": normalize_text(row.get("season")) or (metadata.season if metadata else ""),
            "format": normalize_text(row.get("format")) or (metadata.format_name if metadata else ""),
            "agri_expert_name": normalize_text(row.get("agri_expert_name")) or (metadata.agri_expert_name if metadata else ""),
        },
        "doc_usage": [
            {
                "state": state,
                "crop": crop,
                "verified_by": normalize_text(row.get("verified_by")) or "dpt2_batch_process",
            }
        ],
    }

    chunks_payload = raw_payload.get("chunks") if isinstance(raw_payload.get("chunks"), list) else []
    chunks: List[Dict[str, Any]] = []

    if chunks_payload:
        for idx, item in enumerate(chunks_payload, start=1):
            if not isinstance(item, dict):
                continue
            chunk_text = (
                normalize_text(item.get("chunk_content"))
                or normalize_text(item.get("markdown"))
                or normalize_text(item.get("text"))
                or normalize_text(item.get("content"))
            )
            if not chunk_text:
                continue
            page_no = item.get("page_no") or item.get("page") or item.get("page_number") or item.get("start_page") or 1
            embedding_vector = item.get("embedding_vector")
            if not isinstance(embedding_vector, list):
                embedding_vector = []
            chunks.append(
                {
                    "chunk_id": hashlib.md5(f"{doc_id}:{idx}:{page_no}".encode("utf-8")).hexdigest()[:12],
                    "associated_doc_id": doc_id,
                    "embedding_vector": embedding_vector,
                    "chunk_content": chunk_text,
                    "page_no": page_no,
                }
            )

    if not chunks:
        chunks.append(
            {
                "chunk_id": hashlib.md5(f"{doc_id}:{pdf_name}".encode("utf-8")).hexdigest()[:12],
                "associated_doc_id": doc_id,
                "embedding_vector": raw_payload.get("embedding_vector", []) if isinstance(raw_payload.get("embedding_vector"), list) else [],
                "chunk_content": markdown,
                "page_no": raw_payload.get("page_no", 1),
            }
        )

    return {
        "document": document,
        "chunks": chunks,
    }


def write_outputs(output_dir: Path, markdown: str, payload: Dict[str, Any], logger: logging.Logger) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "dpt2_result.md"
    json_path = output_dir / "dpt2_result.json"

    markdown_path.write_text(markdown or "", encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved {markdown_path} and {json_path}")


def call_dpt2_api(
    pdf_path: Path,
    logger: logging.Logger,
    key_manager: ApiKeyManager,
    timeout: int = 300,
) -> Tuple[str, Dict[str, Any]]:
    api_url = normalize_text(os.environ.get("DPT2_API_URL")) or "https://api.va.landing.ai/v1/ade/parse"
    model_name = normalize_text(os.environ.get("DPT2_MODEL")) or "dpt-2"
    output_format = normalize_text(os.environ.get("DPT2_OUTPUT_FORMAT"))

    data = {
        "model": model_name,
    }
    if output_format:
        data["output_format"] = output_format

    last_error: Optional[Exception] = None
    max_key_attempts = max(1, len(key_manager.keys))
    attempted_keys = 0

    while attempted_keys < max_key_attempts:
        headers = {
            "Authorization": key_manager.current_auth_header(),
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
        }
        try:
            with pdf_path.open("rb") as pdf_handle:
                files = {"document": (pdf_path.name, pdf_handle, "application/pdf")}
                response = requests.post(api_url, headers=headers, data=data, files=files, timeout=timeout)
            error_type = classify_api_error(response)
            if error_type == "rate_limit":
                logger.warning("API key rate-limited; switching to next key.")
                if key_manager.rotate():
                    attempted_keys += 1
                    continue
            elif error_type == "credit":
                logger.error("API key credit exhausted or payment required; NOT rotating to next key for this file.")
                # Flag this file as permanently failed due to credit error
                flag_path = pdf_path.parent / (pdf_path.name + ".credit_exhausted.flag")
                try:
                    flag_path.write_text("credit_exhausted", encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to write credit flag: {flag_path} ({e})")
                raise RuntimeError(f"DPT-2 API request failed: {response.status_code} {response.text}")
            response.raise_for_status()
            import time; time.sleep(5)
            return parse_api_response(response)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 422:
                raise RuntimeError(f"DPT-2 API request failed: {exc}") from exc
            last_error = exc
            attempted_keys += 1
            if len(key_manager.keys) > 1:
                key_manager.rotate()
        except Exception as exc:
            raise

    raise RuntimeError(f"DPT-2 API request failed: {last_error}")


def process_batch(
    csv_path: Path,
    limit: Optional[int],
    force: bool,
    timeout: int,
    logger: logging.Logger,
    output_root: Path,
    pdf_root: Optional[Path],
    strict_paths: bool,
    missing_as_failure: bool,
    lang_filters: Optional[Sequence[str]],
    lang_priority: Optional[Sequence[str]],
    master_xlsx: Optional[Path],
    link_map_xlsx: Optional[Path],
    skip: int = 0,
) -> int:
    rows = read_csv_rows(csv_path)
    normalized_filters = {normalize_text(value).lower() for value in (lang_filters or []) if normalize_text(value)}
    if normalized_filters:
        rows = [row for row in rows if normalize_text(row.get("lang_guess")).lower() in normalized_filters]

    rows = sort_rows_by_lang_priority(rows, lang_priority or [])

    if skip > 0:
        rows = rows[skip:]

    if limit is not None:
        rows = rows[:limit]

    primary_lookup = build_primary_link_lookup(link_map_xlsx, logger)
    link_index, name_index = build_master_metadata_index(master_xlsx, primary_lookup, logger)
    key_manager = build_api_key_manager()

    logger.info("Starting DPT-2 batch processing")
    logger.info(f"Input CSV: {csv_path}")
    logger.info(f"Rows selected: {len(rows)}")

    success_count = 0
    failure_count = 0
    skipped_count = 0
    failed_rows = []

    # Process files in reverse order (from last to first)
    rows = rows[::-1]
    for index, row in enumerate(rows, start=1):
        row = dict(row)
        row["_input_csv"] = str(csv_path)
        pdf_path, attempted_paths = resolve_pdf_path(row, pdf_root=pdf_root, strict_paths=strict_paths)
        state = normalize_state(row.get("state")) or normalize_state(Path(normalize_text(row.get("file_path"))).parent.name)
        pdf_name = Path(normalize_text(row.get("file_path"))).stem or (pdf_path.stem if pdf_path else f"document_{index}")

        if not pdf_path or not pdf_path.exists():
            logger.warning(f"[{index}] SKIP: PDF not found - {normalize_text(row.get('file_path'))}")
            if logger.isEnabledFor(logging.DEBUG) and attempted_paths:
                logger.debug(f"[{index}] attempted paths: {', '.join(str(p) for p in attempted_paths[:10])}")
            skipped_count += 1
            if missing_as_failure:
                failure_count += 1
            continue

        output_dir = output_root / state / pdf_name
        markdown_path = output_dir / "dpt2_result.md"
        json_path = output_dir / "dpt2_result.json"
        credit_flag_path = pdf_path.parent / (pdf_path.name + ".credit_exhausted.flag")

        if credit_flag_path.exists():
            logger.info(f"[{index}] SKIP: Credit exhausted for - {pdf_path}")
            skipped_count += 1
            continue

        if markdown_path.exists() and json_path.exists() and not force:
            logger.info(f"[{index}] SKIP: Already processed - {pdf_path}")
            success_count += 1
            continue

        logger.info(f"[{index}] Processing {pdf_path}")
        try:
            # --- PDF splitting logic ---
            try:
                from PyPDF2 import PdfReader
                total_pages = len(PdfReader(str(pdf_path)).pages)
            except Exception:
                total_pages = 0
            pdf_chunks = split_pdf_by_pages(pdf_path, max_pages=98, logger=logger) if total_pages > 100 else [pdf_path]
            all_markdown = []
            all_chunks = []
            all_raw_payloads = []
            for chunk_pdf in pdf_chunks:
                markdown, raw_payload = call_dpt2_api(chunk_pdf, logger, key_manager=key_manager, timeout=timeout)
                if not markdown:
                    markdown = normalize_text(raw_payload.get("markdown")) if isinstance(raw_payload, dict) else ""
                all_markdown.append(markdown)
                all_raw_payloads.append(raw_payload)
                # If chunked, collect all chunks for final output
                if isinstance(raw_payload.get("chunks"), list):
                    all_chunks.extend(raw_payload["chunks"])
                elif isinstance(raw_payload.get("chunk"), dict):
                    all_chunks.append(raw_payload["chunk"])
            # --- Concatenate markdown and chunks ---
            final_markdown = '\n\n'.join(all_markdown)
            # --- Translate to English ---
            final_markdown_en = translate_markdown_to_english(final_markdown, logger)
            # --- Use first raw_payload for metadata, but all chunks ---
            metadata = find_metadata_for_row(row, pdf_path, link_index, name_index, primary_lookup)
            # Patch raw_payload for build_project_json to use all chunks
            raw_payload = all_raw_payloads[0] if all_raw_payloads else {}
            raw_payload["chunks"] = all_chunks
            payload = build_project_json(row, pdf_path, final_markdown_en, raw_payload, state, metadata)
            write_outputs(output_dir, final_markdown_en, payload, logger)
            # Clean up temp files
            for chunk_pdf in pdf_chunks:
                if chunk_pdf != pdf_path and chunk_pdf.exists():
                    try:
                        chunk_pdf.unlink()
                    except Exception:
                        pass
            success_count += 1
        except Exception as exc:
            failure_count += 1
            logger.error(f"[{index}] FAILED: {pdf_path} :: {exc}")
            failed_rows.append({**row, "failure_reason": str(exc)})

    if failed_rows:
        failed_csv = output_root / "failed_pdfs.csv"
        failed_csv.parent.mkdir(parents=True, exist_ok=True)
        import csv as _csv
        with open(failed_csv, "w", newline="", encoding="utf-8") as f:
            writer = _csv.DictWriter(f, fieldnames=list(failed_rows[0].keys()))
            writer.writeheader()
            writer.writerows(failed_rows)
        logger.info(f"Failed PDFs saved to: {failed_csv} ({len(failed_rows)} entries)")
    logger.info("Batch processing complete")
    logger.info(f"Success: {success_count}")
    logger.info(f"Skipped: {skipped_count}")
    logger.info(f"Failed: {failure_count}")
    return 0 if failure_count == 0 else 1


def print_query_results(results: Sequence[Dict[str, Any]], state: str, crop: str, query: str) -> None:
    print(f"Query: {query}")
    print(f"State: {state}")
    print(f"Crop: {crop}")
    print(f"Matches: {len(results)}")
    for index, result in enumerate(results, start=1):
        print(
            f"{index}. score={result['score']:.3f} | {result['doc_name']} | {result['state']} | {result['crop']} | {result['json_path']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DPT-2 batch processor and query helper")
    parser.add_argument("--mode", choices=["batch", "query"], default="batch")
    parser.add_argument("--input-csv", type=Path, default=None, help="Override input CSV path")
    parser.add_argument("--all", action="store_true", help="Use unprocessed_pdfs.csv instead of garbled_pdfs.csv")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N rows")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--timeout", type=int, default=300, help="Per-PDF API timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--pdf-root", type=Path, default=None, help="Root directory for your current PDF dataset")
    parser.add_argument("--output-root", type=Path, default=None, help="Output root for processed markdown/json")
    parser.add_argument("--log-path", type=Path, default=None, help="Log file path for this run")
    parser.add_argument("--overwrite-log", action="store_true", help="Overwrite log file instead of appending")
    parser.add_argument("--strict-paths", action="store_true", help="Disable legacy POP path rewrites during PDF resolution")
    parser.add_argument("--missing-as-failure", action="store_true", help="Count missing PDFs as failures (default is skip)")
    parser.add_argument("--lang-filter", type=str, default="", help="Comma-separated lang_guess filter list, e.g. 'unsure,indic'")
    parser.add_argument("--lang-priority", type=str, default="unsure,indic", help="Processing order by lang_guess, e.g. 'unsure,indic'")
    parser.add_argument("--skip", type=int, default=0, help="Skip the first N rows before processing (for testing specific files)")
    parser.add_argument("--master-xlsx", type=Path, default=None, help="Master metadata workbook path")
    parser.add_argument("--link-map-xlsx", type=Path, default=None, help="Workbook with primary_link and duplicates columns")
    parser.add_argument("--query", type=str, default="", help="Free-form query for query mode")
    parser.add_argument("--state", type=str, default="", help="State filter for query mode")
    parser.add_argument("--crop", type=str, default="", help="Crop filter for query mode")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum query results to return")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_path = args.log_path or LOG_PATH
    logger = setup_logging(verbose=args.verbose, log_path=log_path, overwrite_log=args.overwrite_log)

    if args.mode == "query":
        query = normalize_text(args.query)
        if not query and not args.state and not args.crop:
            parser.error("query mode requires --query or explicit --state/--crop")

        results = query_documents(query, args.state, args.crop, top_k=args.top_k)
        state_value, crop_value = infer_query_filters(query, args.state, args.crop)
        print_query_results(results[:5], state_value, crop_value, query)
        return 0 if results else 1

    if args.input_csv is not None:
        csv_path = args.input_csv
    else:
        csv_path = DEFAULT_UNPROCESSED_CSV if args.all else DEFAULT_GARBLED_CSV

    if not csv_path.exists():
        fallback = DEFAULT_UNPROCESSED_CSV if csv_path == DEFAULT_GARBLED_CSV else DEFAULT_GARBLED_CSV
        if fallback.exists():
            logger.warning(f"Input CSV not found: {csv_path}. Falling back to {fallback}")
            csv_path = fallback
        else:
            logger.error(f"Input CSV not found: {csv_path}")
            return 1

    output_root = args.output_root or PROCESSED_ROOT
    pdf_root = args.pdf_root.resolve() if args.pdf_root else None
    master_xlsx = args.master_xlsx.resolve() if args.master_xlsx else None
    link_map_xlsx = args.link_map_xlsx.resolve() if args.link_map_xlsx else None
    lang_filters = [part.strip() for part in normalize_text(args.lang_filter).split(",") if part.strip()]
    lang_priority = [part.strip() for part in normalize_text(args.lang_priority).split(",") if part.strip()]

    return process_batch(
        csv_path=csv_path,
        limit=args.limit,
        force=args.force,
        timeout=args.timeout,
        logger=logger,
        output_root=output_root,
        pdf_root=pdf_root,
        strict_paths=args.strict_paths,
        missing_as_failure=args.missing_as_failure,
        lang_filters=lang_filters,
        lang_priority=lang_priority,
        skip=args.skip,
        master_xlsx=master_xlsx,
        link_map_xlsx=link_map_xlsx,
    )


if __name__ == "__main__":
    raise SystemExit(main())