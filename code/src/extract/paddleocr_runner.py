# src/extract/paddleocr_runner.py
import argparse, json
from pdf2image import convert_from_path
from paddleocr import PaddleOCR
from pathlib import Path
from src.utils.io import ensure_dir
import numpy as np

def paddle_ocr_pdf(pdf_path, out_jsonl, lang="en", dpi=300):
    # Map ISO to PaddleOCR lang codes
    lang_map = {
        "en": "en",
        "hi": "hi",
        "te": "te",
        "ta": "ta",
        "kn": "kn",
        "ml": "ml",
        "bn": "bn",
        "gu": "gu",
        "mr": "mr",
        "or": "or",
        "pa": "pa"
    }
    paddle_lang = lang_map.get(lang, "en")
    ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
    pages = convert_from_path(pdf_path, dpi=dpi)
    ensure_dir(Path(out_jsonl).parent)
    with open(out_jsonl, 'w', encoding='utf-8') as f:
        for i, img in enumerate(pages, start=1):
            np_img = np.array(img)
            result = ocr.ocr(np_img, cls=True)
            page = []
            for line in result[0]:
                bbox = [[float(x) for x in pt] for pt in line[0]]
                text = line[1][0]
                conf = float(line[1][1])
                page.append({"bbox": bbox, "text": text, "conf": conf})
            f.write(json.dumps({"page_index": i, "items": page}, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    paddle_ocr_pdf(args.doc, args.out, args.lang, args.dpi)
    print("paddleocr done:", args.out)
