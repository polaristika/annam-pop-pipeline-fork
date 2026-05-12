"""Lightweight English vs Indic probe.

We use FastText language identification model to detect language from extracted PDF text:
  * Extracting text from the first few pages of the PDF using PyPDF2
  * Using FastText lid.176.bin model to identify the language
  * Mapping detected languages to 'en', 'indic', or 'unsure'

Returned dictionary fields:
  lang_guess : 'en' | 'indic' | 'unsure'
  lang_source: 'osd' (fixed label to align with future OCR-based detectors)
  lang_conf  : float in [0,1] derived from FastText confidence
  osd_votes  : list of per-page votes (for optional debugging)
  garbled_detected: bool indicating if garbled text (encoding issues) was detected

Heuristics:
  - If FastText detects English with confidence >= 0.5: 'en'
  - If FastText detects Indic language (hi, te, ta, bn, mr, gu, kn, ml, pa, or) with conf >= 0.3: 'indic'
  - Low confidence detections (< 0.3 for indic, < 0.5 for en): 'unsure'

INDIC_LANGS: Set of all 22 officially recognized Indian language codes
  Devanagari: hi (Hindi), mr (Marathi), ne (Nepali), sa (Sanskrit), kok (Konkani), doi (Dogri), mai (Maithili)
  Bengali-Assamese: bn (Bengali), as (Assamese)
  Gurmukhi: pa (Punjabi)
  Gujarati: gu (Gujarati)
  Oriya: or (Odia)
  Tamil: ta (Tamil)
  Telugu: te (Telugu)
  Kannada: kn (Kannada)
  Malayalam: ml (Malayalam)
  Sinhala: si (Sinhala)
  Perso-Arabic: ur (Urdu), ks (Kashmiri), sd (Sindhi)
  Other: sat (Santali), mni (Manipuri), bo (Bodo)

NOTE: This is intentionally very lightweight and *does not* attempt OCR for image PDFs.
If the PDF has no extractable text the result will be 'unsure' with low confidence.
"""

from __future__ import annotations

from typing import Dict, List
from PyPDF2 import PdfReader
import fasttext
import os

# All 22 officially recognized Indian languages (Constitution of India, 8th Schedule)
# Organized by script family for reference
INDIC_LANGS = {
    # Devanagari script (U+0900-U+097F)
    'hi',  # Hindi
    'mr',  # Marathi
    'ne',  # Nepali
    'sa',  # Sanskrit
    
    # Bengali-Assamese script (U+0980-U+09FF)
    'bn',  # Bengali/Bangla
    'as',  # Assamese
    
    # Gurmukhi script (U+0A00-U+0A7F)
    'pa',  # Punjabi
    
    # Gujarati script (U+0A80-U+0AFF)
    'gu',  # Gujarati
    
    # Oriya script (U+0B00-U+0B7F)
    'or',  # Odia/Oriya
    
    # Tamil script (U+0B80-U+0BFF)
    'ta',  # Tamil
    
    # Telugu script (U+0C00-U+0C7F)
    'te',  # Telugu
    
    # Kannada script (U+0C80-U+0CFF)
    'kn',  # Kannada
    
    # Malayalam script (U+0D00-U+0D7F)
    'ml',  # Malayalam
    
    # Sinhala script (U+0D80-U+0DFF) - Sri Lankan but included
    'si',  # Sinhala
    
    # Perso-Arabic script variants
    'ur',  # Urdu (U+0600-U+06FF Arabic + U+0750-U+077F Arabic Supplement)
    'ks',  # Kashmiri (Perso-Arabic)
    
    # Tibetan script (U+0F00-U+0FFF)
    'bo',  # Bodo (uses Devanagari but Tibetan for traditional)
    
    # Additional languages (using existing scripts)
    'sd',  # Sindhi (Perso-Arabic/Devanagari)
    'kok', # Konkani (Devanagari)
    'doi', # Dogri (Devanagari)
    'mai', # Maithili (Devanagari)
    'sat', # Santali (Ol Chiki script U+1C50-U+1C7F)
    'mni', # Manipuri/Meitei (Meitei Mayek U+ABC0-U+ABFF)
}

# Global model instance
_FASTTEXT_MODEL = None

def _get_fasttext_model():
    """Lazy load FastText model."""
    global _FASTTEXT_MODEL
    if _FASTTEXT_MODEL is None:
        # model_path = 'lid.176.bin'
        # if not os.path.exists(model_path):
        #     # Try absolute path from project root
        #     model_path = os.path.join(os.path.dirname(__file__), '../../lid.176.bin')
        _project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )

        model_path = os.path.join(_project_root, 'lid.176.bin')
        if not os.path.exists(model_path):
            model_path = os.path.join(_project_root, 'misc', 'lid.176.bin')
        if os.path.exists(model_path):
            _FASTTEXT_MODEL = fasttext.load_model(model_path)
        else:
            raise FileNotFoundError(f"FastText model not found. Expected at: lid.176.bin")
    return _FASTTEXT_MODEL


def _detect_garbled_text(text: str) -> bool:
    """Detect if text extraction is garbled (Unicode corruption).
    
    Universal detection for ALL 22 official Indian languages + their scripts:
    
    Script Families & Unicode Blocks:
    - Devanagari (U+0900-U+097F): Hindi, Marathi, Nepali, Sanskrit, Konkani, Dogri, Maithili
    - Bengali-Assamese (U+0980-U+09FF): Bengali, Assamese
    - Gurmukhi (U+0A00-U+0A7F): Punjabi
    - Gujarati (U+0A80-U+0AFF): Gujarati
    - Oriya (U+0B00-U+0B7F): Odia
    - Tamil (U+0B80-U+0BFF): Tamil
    - Telugu (U+0C00-U+0C7F): Telugu
    - Kannada (U+0C80-U+0CFF): Kannada
    - Malayalam (U+0D00-U+0D7F): Malayalam
    - Sinhala (U+0D80-U+0DFF): Sinhala
    - Arabic/Urdu (U+0600-U+06FF, U+0750-U+077F): Urdu, Kashmiri, Sindhi
    - Ol Chiki (U+1C50-U+1C7F): Santali
    - Meitei Mayek (U+ABC0-U+ABFF): Manipuri
    
    When ANY of these scripts get corrupted during PDF extraction, they produce:
    → Latin-1 Supplement (U+0080-U+00FF): Ä, ç, ø, £, etc.
    → Mathematical operators (U+2200-U+22FF): ∑, √, ∫, ≈, etc.
    → Diacritical marks (U+02B0-U+036F): ˚, ´, `, ¨, etc.
    
    This language-agnostic approach catches corruption from ALL Indic scripts.
    """
    if len(text) < 5:
        return False
    
    # Count different character categories
    latin1_supplement = 0  # U+0080-U+00FF (corruption from ALL Indic scripts)
    math_operators = 0     # U+2200-U+22FF (∑, ∫, √, ≈, etc.)
    diacriticals = 0       # U+02B0-U+036F (combining marks)
    box_drawing = 0        # U+2500-U+257F (box drawing chars)
    general_punctuation = 0 # U+2000-U+206F (special spaces, invisible chars)
    ascii_letters = 0
    ascii_digits = 0
    spaces = 0
    indic_range_chars = 0  # Actual Indic Unicode characters (properly encoded)
    
    for c in text:
        code = ord(c)
        
        # Latin-1 Supplement range (PRIMARY corruption target from ALL Indic scripts)
        if 0x0080 <= code <= 0x00FF:
            latin1_supplement += 1
        # Mathematical operators (common corruption)
        elif 0x2200 <= code <= 0x22FF:
            math_operators += 1
        # Spacing modifier letters & combining diacriticals
        elif 0x02B0 <= code <= 0x036F:
            diacriticals += 1
        # Box drawing characters (seen in some corruptions)
        elif 0x2500 <= code <= 0x257F:
            box_drawing += 1
        # General punctuation (zero-width spaces, etc. from corruption)
        elif 0x2000 <= code <= 0x206F:
            general_punctuation += 1
        # Properly encoded Indic scripts (indicates NON-garbled text)
        # Devanagari, Bengali, Gurmukhi, Gujarati, Oriya, Tamil, Telugu, Kannada, Malayalam, Sinhala
        elif (0x0900 <= code <= 0x0DFF) or \
             (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or \
             (0x1C50 <= code <= 0x1C7F) or \
             (0xABC0 <= code <= 0xABFF):
            indic_range_chars += 1
        # ASCII letters
        elif ('A' <= c <= 'Z') or ('a' <= c <= 'z'):
            ascii_letters += 1
        # ASCII digits
        elif '0' <= c <= '9':
            ascii_digits += 1
        # Spaces
        elif c == ' ':
            spaces += 1
    
    # Count HTML entities (another corruption indicator)
    html_entity_count = (text.count('&lt;') + text.count('&gt;') + 
                        text.count('&amp;') + text.count('&quot;'))
    
    # Count backticks (common in garbled numbers across all languages)
    backtick_count = text.count('`')
    
    total_chars = len(text)
    
    # Calculate ratios
    latin1_ratio = latin1_supplement / total_chars
    math_ratio = math_operators / total_chars
    diacritic_ratio = diacriticals / total_chars
    box_ratio = box_drawing / total_chars
    punct_ratio = general_punctuation / total_chars
    indic_ratio = indic_range_chars / total_chars  # Properly encoded Indic text
    ascii_ratio = ascii_letters / total_chars
    space_ratio = spaces / total_chars
    
    # Combined "corruption score" (weighted sum of corruption indicators)
    corruption_score = latin1_ratio + math_ratio + diacritic_ratio + box_ratio + (punct_ratio * 0.5)
    
    # If we have properly encoded Indic characters, it's NOT garbled
    # (This prevents false positives on correctly extracted Indic PDFs)
    if indic_ratio > 0.20:  # >20% proper Indic Unicode = legitimate Indic text
        return False
    
    # Detection criteria (language-agnostic, tuned for both short and long texts):
    
    # 1. High corruption score (>25% of characters are suspicious)
    if corruption_score > 0.25:
        return True
    
    # 2. Moderate corruption (>12%) with low ASCII content (<50%)
    # Lowered thresholds to catch shorter garbled samples
    if corruption_score > 0.12 and ascii_ratio < 0.50:
        return True
    
    # 3. Latin-1 supplement alone >15% (more sensitive)
    if latin1_ratio > 0.15:
        return True
    
    # 4. Math operators alone >8% (highly suspicious)
    if math_ratio > 0.08:
        return True
    
    # 5. HTML entities + corruption indicates encoding issues
    if html_entity_count > 2 and corruption_score > 0.08:
        return True
    
    # 6. Multiple backticks with low spaces (garbled numbers pattern)
    if backtick_count > 2 and space_ratio < 0.10:
        return True
    
    # 7. Moderate corruption (>10%) with very low ASCII (<30%)
    # Additional check for short samples with heavy corruption
    if corruption_score > 0.10 and ascii_ratio < 0.30:
        return True

    non_ascii = latin1_supplement + math_operators + diacriticals + box_drawing + indic_range_chars
    if non_ascii > 0:
        latin1_of_non_ascii = latin1_supplement / non_ascii
        if latin1_of_non_ascii > 0.50 and latin1_supplement >= 3:
            return True
    
    return False


def english_vs_indic(pdf_path: str, dpi: int = 180, pages: int = 5) -> Dict[str, object]:  # dpi unused placeholder
    try:
        reader = PdfReader(pdf_path)
    except Exception:
        return {"lang_guess": "unsure", "lang_source": "osd", "lang_conf": 0.0, "osd_votes": []}

    # Load FastText model
    try:
        model = _get_fasttext_model()
    except Exception:
        # Fallback to unsure if model loading fails
        return {"lang_guess": "unsure", "lang_source": "osd", "lang_conf": 0.0, "osd_votes": []}

    votes: List[str] = []
    confidences: List[float] = []
    garbled_pages: List[bool] = []
    total_pages = len(reader.pages)

    # Walk pages from the start, collect the first `pages` that have >= 50 chars
    # of extractable text, checking at most 10 pages total.
    page_texts: List[str] = []
    for idx in range(min(10, total_pages)):
        try:
            txt = reader.pages[idx].extract_text() or ""
        except Exception:
            txt = ""
        if len(txt.strip()) >= 50:
            page_texts.append(txt)
        if len(page_texts) >= pages:
            break

    for txt in page_texts:
        
        # Check if text is garbled (Unicode corruption indicating Indic script)
        if _detect_garbled_text(txt):
            # Garbled text is a strong indicator of Indic language PDFs
            # where PyPDF2 can't extract Unicode properly
            votes.append("indic")
            confidences.append(0.8)  # High confidence for garbled text
            garbled_pages.append(True)
            continue
        
        # Clean text for FastText (remove newlines, limit length)
        txt_clean = txt.replace('\n', ' ').strip()[:1000]
        
        try:
            # FastText predict returns: (('__label__XX',), array([confidence]))
            labels, confs = model.predict(txt_clean)
            lang_code = labels[0].replace('__label__', '')
            conf = float(confs[0])
            
            # Classify based on detected language
            if lang_code == 'en' and conf >= 0.5:
                votes.append("en")
                confidences.append(conf)
                garbled_pages.append(False)
            elif lang_code in INDIC_LANGS and conf >= 0.3:
                votes.append("indic")
                confidences.append(conf)
                garbled_pages.append(False)
            else:
                # Very low confidence (< 0.2) often indicates garbled or non-standard text
                # This is common with Indic PDFs that PyPDF2 can't handle
                if conf < 0.2:
                    # CORNER CASE HANDLER: Secondary garbled text check
                    # If primary detection missed it, check again with cleaned text
                    is_garbled = _detect_garbled_text(txt_clean)
                    if is_garbled:
                        # Confirmed garbled text - high confidence it's Indic
                        votes.append("indic")
                        confidences.append(0.8)  # Higher confidence - confirmed garbled
                        garbled_pages.append(True)
                    else:
                        # Low confidence but not detectably garbled
                        # Still assume Indic (common in agricultural PDF context)
                        votes.append("indic")
                        confidences.append(0.5)  # Lower confidence - uncertain
                        garbled_pages.append(False)
                else:
                    votes.append("unsure")
                    confidences.append(conf)
                    garbled_pages.append(False)
        except Exception as e:
            import sys
            print(f"[english_vs_indic] FastText predict failed: {e}", file=sys.stderr)
            votes.append("unsure")
            confidences.append(0.0)
            garbled_pages.append(False)

    # Aggregate
    if not votes:
        return {
            "lang_guess": "unsure",
            "lang_source": "osd",
            "lang_conf": 0.0,
            "osd_votes": [],
            "garbled_detected": False
        }

    # Count votes
    en_votes = votes.count("en")
    indic_votes = votes.count("indic")
    
    # Average confidence for dominant category
    if en_votes > indic_votes:
        guess = "en"
        conf = sum(c for v, c in zip(votes, confidences) if v == "en") / max(1, en_votes)
    elif indic_votes > en_votes:
        guess = "indic"
        conf = sum(c for v, c in zip(votes, confidences) if v == "indic") / max(1, indic_votes)
    else:
        guess = "unsure"
        conf = sum(confidences) / len(confidences) * 0.5 if confidences else 0.0

    return {
        "lang_guess": guess,
        "lang_source": "osd",
        "lang_conf": round(float(conf), 4),
        "osd_votes": votes,
        "garbled_detected": any(garbled_pages),  # True if any page had garbled text
    }


__all__ = ["english_vs_indic"]
