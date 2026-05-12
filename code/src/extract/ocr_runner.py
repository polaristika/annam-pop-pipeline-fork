# src/extract/ocr_runner.py
import argparse, json
from pdf2image import convert_from_path
import easyocr
from pathlib import Path
from src.utils.io import ensure_dir
import numpy as np

def ocr_pdf(pdf_path, out_jsonl, dpi=300, lang_list=['en']):
    pages = convert_from_path(pdf_path, dpi=dpi)
    reader = easyocr.Reader(lang_list, gpu=True)
    ensure_dir(Path(out_jsonl).parent)
    with open(out_jsonl,'w',encoding='utf-8') as f:
        for i, img in enumerate(pages, start=1):
            np_img = np.array(img)  # RGB
            res = reader.readtext(np_img, detail=1)
            page = []
            for bbox, text, conf in res:
                # Convert bbox to list of lists of floats
                bbox_py = [[float(x) for x in pt] for pt in bbox]
                page.append({"bbox": bbox_py, "text": text, "conf": float(conf)})
            f.write(json.dumps({"page_index": i, "items": page}, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--langs", nargs="+", default=["en"])
    args = ap.parse_args()
    ocr_pdf(args.doc, args.out, args.dpi, args.langs)
    print("ocr done:", args.out)
