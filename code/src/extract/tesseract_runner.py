# src/extract/tesseract_runner.py
import argparse, json
from pdf2image import convert_from_path
from pathlib import Path
from utils.io import ensure_dir
from PIL import Image
import pytesseract
import numpy as np

def tesseract_ocr_pdf(pdf_path, out_jsonl, lang="eng", dpi=300):
    pages = convert_from_path(pdf_path, dpi=dpi)
    ensure_dir(Path(out_jsonl).parent)
    with open(out_jsonl, 'w', encoding='utf-8') as f:
        for i, img in enumerate(pages, start=1):
            np_img = np.array(img)
            # PIL expects RGB, pytesseract expects PIL Image
            pil_img = Image.fromarray(np_img)
            try:
                text = pytesseract.image_to_string(pil_img, lang=lang)
            except Exception as e:
                text = f"[Tesseract error: {str(e)}]"
            # No bbox/confidence per word, so just wrap as one block
            page = [{"bbox": None, "text": text.strip(), "conf": 1.0 if text.strip() else 0.0}]
            f.write(json.dumps({"page_index": i, "items": page}, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="eng")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    tesseract_ocr_pdf(args.doc, args.out, args.lang, args.dpi)
    print("tesseract ocr done:", args.out)
