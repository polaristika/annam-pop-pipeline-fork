"""GPU-optimized batch stitcher for H200.

Key optimizations:
1. Batch VLM inference for image descriptions (all images loaded into GPU memory once)
2. Shared BLIP model instance across all documents
3. Parallel image encoding (CPU-bound work)
4. Memory-efficient streaming for large batches

This avoids per-image model load overhead.
"""

import os, json, argparse, base64, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from src.utils.io import ensure_dir, write_json
from PIL import Image
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import PictureItem

# Global VLM model cache (loaded once)
_VLM_MODEL = None

def get_vlm_model():
    global _VLM_MODEL
    if _VLM_MODEL is None:
        try:
            from src.utils.vlm_utils import load_blip_model
            _VLM_MODEL = load_blip_model()
        except Exception as e:
            print(f"[WARN] VLM model load failed: {e}", file=sys.stderr)
            _VLM_MODEL = "ERROR"
    return _VLM_MODEL if _VLM_MODEL != "ERROR" else None


def batch_vlm_descriptions(images):
    """Generate descriptions for multiple images in one GPU pass."""
    model = get_vlm_model()
    if model is None:
        return ["[VLM unavailable]"] * len(images)
    
    try:
        from src.utils.vlm_utils import batch_blip_captions
        return batch_blip_captions(model, images)
    except Exception as e:
        print(f"[WARN] Batch VLM failed, falling back: {e}", file=sys.stderr)
        # Fallback to single
        descs = []
        for img in images:
            try:
                from src.utils.vlm_utils import get_blip_caption_with_model
                descs.append(get_blip_caption_with_model(model, img))
            except Exception:
                descs.append("[VLM error]")
        return descs


def image_to_base64(img):
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def extract_images_with_docling(pdf_path):
    pipeline_options = PdfPipelineOptions(
        generate_picture_images=True,
        images_scale=2.0,
        do_ocr=True,
        ocr_options=EasyOcrOptions()
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(pdf_path)
    doc = result.document
    images = []
    for item, _ in doc.iterate_items():
        if isinstance(item, PictureItem):
            pil_image = item.get_image(doc)
            if pil_image:
                images.append((item, pil_image))
    return images


def process_single_doc(doc_id, docling_json_path, pdf_path):
    """Process one document: extract images, batch VLM, write outputs."""
    art_dir = Path("artifacts") / doc_id
    ensure_dir(art_dir)
    
    with open(docling_json_path, "r", encoding="utf-8") as f:
        docling_json = json.load(f)
    
    pic_map = {p['self_ref']: p for p in docling_json.get('pictures', [])}
    text_map = {t['self_ref']: t for t in docling_json.get('texts', [])}
    body_children = docling_json.get('body', {}).get('children', [])
    
    # Extract all images
    images = []
    if pdf_path:
        try:
            images = extract_images_with_docling(pdf_path)
        except Exception as e:
            print(f"[ERROR] {doc_id}: Docling image extraction failed: {e}", file=sys.stderr)
    
    # Batch VLM descriptions for all images at once
    pil_images = [pil for _, pil in images]
    if pil_images:
        descriptions = batch_vlm_descriptions(pil_images)
    else:
        descriptions = []
    
    # Encode images to base64 in parallel (CPU-bound)
    base64_images = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        base64_images = list(ex.map(image_to_base64, pil_images))
    
    # Build blocks
    blocks = []
    img_idx = 0
    for elem in body_children:
        if isinstance(elem, dict) and '$ref' in elem:
            ref = elem['$ref']
        else:
            ref = elem
        
        if ref.startswith('#/texts/'):
            t = text_map.get(ref)
            if t:
                blocks.append({"type": "paragraph", "text_native": t.get("text", ""), "confidence": 1.0})
        
        elif ref.startswith('#/pictures/'):
            if img_idx < len(images):
                desc = descriptions[img_idx] if img_idx < len(descriptions) else "Image from document."
                b64 = base64_images[img_idx] if img_idx < len(base64_images) else ""
                img_idx += 1
            else:
                desc = "Image from document."
                b64 = ""
            blocks.append({
                "type": "image",
                "description": desc,
                "base64": b64,
                "confidence": 1.0
            })
    
    if not blocks and "text" in docling_json:
        blocks.append({"type": "paragraph", "text_native": docling_json["text"], "confidence": 1.0})
    
    # Write doc.json
    write_json({"doc_id": doc_id, "blocks": blocks}, art_dir / "doc.json")
    
    # Generate doc.md with descriptions and base64
    docling_md = Path(docling_json_path).with_name("docling.md")
    out_md = art_dir / "doc.md"
    if docling_md.exists():
        md_lines = docling_md.read_text(encoding="utf-8").splitlines()
        new_lines = []
        img_idx = 0
        for line in md_lines:
            new_lines.append(line)
            if line.strip() == "<!-- image -->":
                while img_idx < len(blocks) and blocks[img_idx].get("type") != "image":
                    img_idx += 1
                if img_idx < len(blocks):
                    img_block = blocks[img_idx]
                    desc = img_block.get("description") or "Image from document."
                    b64 = img_block.get("base64")
                    new_lines.append(f"**Image Description:** {desc}")
                    if b64:
                        b64_single_line = b64.replace("\n", "")
                        new_lines.append(f"<details><summary>Base64</summary>\n\n```")
                        new_lines.append(b64_single_line)
                        new_lines.append("```")
                        new_lines.append("</details>")
                    img_idx += 1
        out_md.write_text("\n".join(new_lines), encoding="utf-8")
    else:
        md = "\n\n".join(b.get("text_native", "") for b in blocks if b.get("type") == "paragraph")
        out_md.write_text(md, encoding="utf-8")
    
    return {"doc_id": doc_id, "n_blocks": len(blocks)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Batch stitcher (GPU-optimized VLM)")
    ap.add_argument("--batch_file", required=True, help="JSON file with list of {doc_id, docling_json, pdf_path} dicts")
    args = ap.parse_args()
    
    with open(args.batch_file, 'r') as f:
        batch = json.load(f)
    
    print(f"[BATCH STITCH] Processing {len(batch)} documents...", file=sys.stderr)
    
    # Pre-load VLM model once
    get_vlm_model()
    
    results = []
    for item in batch:
        try:
            result = process_single_doc(item["doc_id"], item["docling_json"], item.get("pdf_path"))
            results.append({"success": True, "doc_id": item["doc_id"], "n_blocks": result["n_blocks"]})
        except Exception as e:
            results.append({"success": False, "doc_id": item["doc_id"], "error": str(e)[:100]})
    
    success_count = sum(1 for r in results if r["success"])
    print(f"[BATCH STITCH] Completed: {success_count}/{len(results)} success", file=sys.stderr)
    
    # Output results as JSON lines
    for r in results:
        print(json.dumps(r))
