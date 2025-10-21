import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np
from PIL import Image, ImageOps
from pdf2image import convert_from_path

# Optional imports – guarded
try:
    import torch
    from transformers import pipeline, AutoProcessor, AutoModelForVision2Seq
    _HF_AVAILABLE = True
except Exception:
    _HF_AVAILABLE = False

# Optional Table Detector (Microsoft Table Transformer)
# If not installed, we skip table detection without failing the run
try:
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    _TT_AVAILABLE = True
except Exception:
    _TT_AVAILABLE = False


# ------------------------
# Data structures
# ------------------------
@dataclass
class Region:
    page_index: int               # 1-based page index
    bbox: List[Tuple[float, float]]  # 4-point polygon [(x0,y0),(x1,y1),(x2,y2),(x3,y3)] or [x1,y1,x2,y2]
    kind: str                     # "text" | "table" | "auto"
    source: str                   # "ocr_low_conf" | "table_detector" | "manual"
    score: float                  # heuristic score / confidence


# ------------------------
# Utilities
# ------------------------
def load_ocr_jsonl(ocr_jsonl_path: str) -> Dict[int, Dict[str, Any]]:
    """
    Load OCR JSONL produced by src/extract/ocr_runner.py
    Returns dict: {page_index: {"items": [{"bbox": [...], "text": str, "conf": float}, ...]}}
    """
    pages = {}
    with open(ocr_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            pages[int(obj["page_index"])] = obj
    return pages


def page_avg_conf(page_obj: Dict[str, Any]) -> float:
    items = page_obj.get("items", [])
    if not items:
        return 0.0
    return float(sum(i.get("conf", 0.0) for i in items) / max(1, len(items)))


def rasterize_pages(pdf_path: str, page_indices: List[int], dpi: int = 300) -> Dict[int, Image.Image]:
    """
    Rasterize only selected pages (1-based indices) to PIL Images at given DPI.
    """
    if not page_indices:
        return {}
    # pdf2image accepts "first_page" and "last_page" ranges, but we might need disjoint pages.
    # Simple path: render full doc range once if contiguous, else render individually.
    # For simplicity & robustness, render individually (fast enough for rescue pages).
    images = {}
    for idx in page_indices:
        imgs = convert_from_path(pdf_path, dpi=dpi, first_page=idx, last_page=idx)
        if imgs:
            images[idx] = imgs[0]
    return images


def poly_to_xyxy(bbox) -> Tuple[float, float, float, float]:
    """
    Convert EasyOCR polygon or already-xyxy to normalized (x1,y1,x2,y2).
    """
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
        x1, y1, x2, y2 = bbox
        return float(min(x1, x2)), float(min(y1, y2)), float(max(x1, x2)), float(max(y1, y2))
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(isinstance(pt, (list, tuple)) for pt in bbox):
        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
    raise ValueError(f"Unsupported bbox format: {bbox}")


def expand_xyxy(x1, y1, x2, y2, w_pad: int, h_pad: int, w_max: int, h_max: int):
    return max(0, x1 - w_pad), max(0, y1 - h_pad), min(w_max, x2 + w_pad), min(h_max, y2 + h_pad)


def merge_overlapping_boxes(boxes: List[Tuple[float, float, float, float]], iou_thr=0.2) -> List[Tuple[float, float, float, float]]:
    """
    Simple box merging using IOU threshold.
    """
    if not boxes:
        return []
    boxes = [tuple(map(float, b)) for b in boxes]
    used = [False] * len(boxes)
    merged = []
    for i, b in enumerate(boxes):
        if used[i]:
            continue
        x1, y1, x2, y2 = b
        for j in range(i+1, len(boxes)):
            if used[j]:
                continue
            u1, v1, u2, v2 = boxes[j]
            inter_x1 = max(x1, u1); inter_y1 = max(y1, v1)
            inter_x2 = min(x2, u2); inter_y2 = min(y2, v2)
            inter = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            area_a = (x2 - x1) * (y2 - y1)
            area_b = (u2 - u1) * (v2 - v1)
            iou = inter / max(1e-6, (area_a + area_b - inter))
            if iou >= iou_thr:
                # merge
                x1 = min(x1, u1); y1 = min(y1, v1)
                x2 = max(x2, u2); y2 = max(y2, v2)
                used[j] = True
        used[i] = True
        merged.append((x1, y1, x2, y2))
    return merged


# ------------------------
# Table detection (optional)
# ------------------------
class TableDetector:
    def __init__(self, model_name="microsoft/table-transformer-detection"):
        if not _TT_AVAILABLE:
            raise RuntimeError("Table Transformer not available")
        self.processor = AutoImageProcessor.from_pretrained(model_name)
        self.model = TableTransformerForObjectDetection.from_pretrained(model_name)

    @torch.no_grad()
    def detect(self, image: Image.Image, score_thr: float = 0.75) -> List[Tuple[int, int, int, int, float]]:
        """
        Returns list of (x1,y1,x2,y2,score) in pixel coords
        """
        inputs = self.processor(images=image, return_tensors="pt")
        outputs = self.model(**inputs)
        # Postprocess to image size
        target_sizes = torch.tensor([image.size[::-1]])  # (h, w)
        results = self.processor.post_process_object_detection(outputs, threshold=score_thr, target_sizes=target_sizes)[0]
        boxes = results["boxes"].tolist() if "boxes" in results else []
        scores = results["scores"].tolist() if "scores" in results else []
        return [(int(x1), int(y1), int(x2), int(y2), float(s)) for (x1, y1, x2, y2), s in zip(boxes, scores)]


# ------------------------
# VLM wrapper
# ------------------------
class VLMReader:
    def __init__(self, model_name: str):
        if not _HF_AVAILABLE:
            raise RuntimeError("Hugging Face transformers not available. Install transformers/torch.")
        # Many VLMs can be accessed via pipeline("image-to-text")
        # Qwen2-VL Instruct also works well with prompt+image inputs.
        try:
            self.pipe = pipeline(
                "image-to-text",
                model=model_name,
                torch_dtype=getattr(torch, "float16", None),
                device_map="auto"
            )
            self.use_pipeline = True
        except Exception:
            # Fallback to processor+model
            self.use_pipeline = False
            self.processor = AutoProcessor.from_pretrained(model_name)
            self.model = AutoModelForVision2Seq.from_pretrained(model_name, torch_dtype=getattr(torch, "float16", None), device_map="auto")

    @torch.no_grad()
    def read_text(self, image: Image.Image, prompt: str, max_new_tokens: int = 256) -> str:
        if self.use_pipeline:
            # Some models accept a prompt in "prompt=" kw (e.g., Llava variants); if unsupported, we fallback to plain image-to-text.
            try:
                out = self.pipe(image, prompt=prompt, max_new_tokens=max_new_tokens)
            except TypeError:
                out = self.pipe(image, max_new_tokens=max_new_tokens)
            text = out[0]["generated_text"] if out else ""
            return text.strip()
        # Processor path
        inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(self.model.device)
        generated_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        out = self.processor.batch_decode(generated_ids, skip_special_tokens=True)
        return out[0].strip() if out else ""


# ------------------------
# Region selection
# ------------------------
def select_regions_from_ocr(page_obj: Dict[str, Any],
                            img_w: int,
                            img_h: int,
                            low_box_thr: float = 0.6,
                            margin_px: int = 12) -> List[Tuple[int, int, int, int]]:
    """
    From OCR items, take low-confidence boxes, expand a bit, and merge overlaps.
    """
    boxes = []
    for item in page_obj.get("items", []):
        conf = float(item.get("conf", 0.0))
        if conf <= low_box_thr:
            x1, y1, x2, y2 = poly_to_xyxy(item["bbox"])
            x1, y1, x2, y2 = expand_xyxy(x1, y1, x2, y2, margin_px, margin_px, img_w, img_h)
            boxes.append((x1, y1, x2, y2))
    boxes = merge_overlapping_boxes(boxes, iou_thr=0.2)
    return [(int(x1), int(y1), int(x2), int(y2)) for (x1, y1, x2, y2) in boxes]


def build_regions(pdf_path: str,
                  ocr_pages: Dict[int, Dict[str, Any]],
                  target_pages: List[int],
                  dpi: int,
                  use_table_detector: bool,
                  table_score_thr: float,
                  low_box_thr: float) -> Tuple[Dict[int, Image.Image], List[Region]]:
    """
    Rasterize pages and compile regions from OCR low-conf, plus optional table detector.
    """
    # Rasterize
    page_images = rasterize_pages(pdf_path, target_pages, dpi=dpi)
    regions: List[Region] = []

    # Optional table detector
    td = None
    if use_table_detector and _TT_AVAILABLE:
        try:
            td = TableDetector()
        except Exception:
            td = None

    for pidx in target_pages:
        img = page_images.get(pidx)
        if img is None:
            continue
        w, h = img.size

        # OCR-based low conf regions
        ocr_page = ocr_pages.get(pidx, {"items": []})
        low_regions = select_regions_from_ocr(ocr_page, w, h, low_box_thr=low_box_thr)
        for (x1, y1, x2, y2) in low_regions:
            regions.append(Region(
                page_index=pidx,
                bbox=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
                kind="text",
                source="ocr_low_conf",
                score=0.5
            ))

        # Table detection regions
        if td is not None:
            try:
                dets = td.detect(img, score_thr=table_score_thr)
                for (x1, y1, x2, y2, sc) in dets:
                    regions.append(Region(
                        page_index=pidx,
                        bbox=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
                        kind="table",
                        source="table_detector",
                        score=sc
                    ))
            except Exception:
                pass

        # If no regions at all, fall back to reading the full page (rare)
        if not any(r.page_index == pidx for r in regions):
            regions.append(Region(
                page_index=pidx,
                bbox=[(0, 0), (w, 0), (w, h), (0, h)],
                kind="auto",
                source="page_fallback",
                score=0.1
            ))

    return page_images, regions


def crop_region(image: Image.Image, bbox_poly: List[Tuple[float, float]]) -> Image.Image:
    x1, y1, x2, y2 = poly_to_xyxy(bbox_poly)
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    crop = image.crop((x1, y1, x2, y2))
    # Small border to avoid cutting characters
    return ImageOps.expand(crop, border=2, fill="white")


# ------------------------
# Prompts
# ------------------------
PLAIN_PROMPT = (
    "Read all visible text verbatim from this image region. "
    "Return plain text with line breaks. Do not add commentary."
)

TABLE_PROMPT = (
    "This image is a table. Read it cell by cell, left to right, top to bottom, "
    "and output the table in TSV (tab-separated values) with one row per line. "
    "Do not add extra commentary."
)


# ------------------------
# Main
# ------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True, help="PDF path")
    ap.add_argument("--ocr_jsonl", required=True, help="OCR JSONL path for this doc")
    ap.add_argument("--out", required=True, help="Output JSON path for VLM reads")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--model", default="Qwen/Qwen2-VL-7B-Instruct")
    ap.add_argument("--min_page_conf", type=float, default=0.80, help="Select pages with avg OCR conf below this")
    ap.add_argument("--low_box_thr", type=float, default=0.60, help="Select individual OCR boxes below this for regions")
    ap.add_argument("--max_pages", type=int, default=4, help="Safety cap on pages to rescue")
    ap.add_argument("--enable_tables", action="store_true", help="Use table detector if available")
    ap.add_argument("--table_score_thr", type=float, default=0.75)
    args = ap.parse_args()

    # 1) Load OCR pages
    ocr_pages = load_ocr_jsonl(args.ocr_jsonl)
    if not ocr_pages:
        print("[VLM] No OCR pages found. Exiting.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"reads": [], "note": "no_ocr_pages"}, f, ensure_ascii=False, indent=2)
        return

    # 2) Pick target pages by low avg confidence
    low_pages = []
    for pidx, pobj in ocr_pages.items():
        avgc = page_avg_conf(pobj)
        if avgc < args.min_page_conf:
            low_pages.append((pidx, avgc))
    # Prioritize worst pages
    low_pages.sort(key=lambda x: x[1])
    target_pages = [p for p, _ in low_pages[:args.max_pages]]

    if not target_pages:
        print("[VLM] No pages below threshold; nothing to rescue.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"reads": [], "note": "no_low_conf_pages"}, f, ensure_ascii=False, indent=2)
        return

    # 3) Build regions (OCR low-conf + optional tables)
    page_images, regions = build_regions(
        pdf_path=args.doc,
        ocr_pages=ocr_pages,
        target_pages=target_pages,
        dpi=args.dpi,
        use_table_detector=args.enable_tables,
        table_score_thr=args.table_score_thr,
        low_box_thr=args.low_box_thr
    )

    if not regions:
        print("[VLM] No regions found; exiting.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"reads": [], "note": "no_regions"}, f, ensure_ascii=False, indent=2)
        return

    # 4) Init VLM
    try:
        vlm = VLMReader(args.model)
    except Exception as e:
        print(f"[VLM] Could not initialize model {args.model}: {e}")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"reads": [], "note": "vlm_init_error"}, f, ensure_ascii=False, indent=2)
        return

    # 5) Read each region
    reads = []
    for reg in regions:
        img = page_images.get(reg.page_index)
        if img is None:
            continue
        crop = crop_region(img, reg.bbox)
        prompt = TABLE_PROMPT if reg.kind == "table" else PLAIN_PROMPT
        try:
            text = vlm.read_text(crop, prompt=prompt, max_new_tokens=512 if reg.kind == "table" else 256)
        except Exception as e:
            text = ""
        # Simple heuristic "confidence": higher for tables with detector score, else mid
        conf_est = float(min(0.99, 0.6 + 0.4 * reg.score)) if reg.kind == "table" else float(min(0.95, 0.5 + 0.3 * reg.score))
        reads.append({
            "page_index": reg.page_index,
            "bbox_xyxy": list(poly_to_xyxy(reg.bbox)),
            "kind": reg.kind,
            "source": reg.source,
            "prompt": "table_tsv" if reg.kind == "table" else "plain_text",
            "text": text,
            "confidence_est": conf_est
        })

    # 6) Write output
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"reads": reads}, f, ensure_ascii=False, indent=2)
    print(f"[VLM] Wrote {args.out} with {len(reads)} region reads.")


if __name__ == "__main__":
    main()