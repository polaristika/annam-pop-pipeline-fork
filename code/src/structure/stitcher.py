# src/structure/stitcher.py
import os, json, argparse, base64
from pathlib import Path
from utils.io import ensure_dir, write_json
from PIL import Image
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import PictureItem

def extract_images_with_docling(pdf_path):
    # Use Docling pipeline to extract images as PIL Images
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

def image_to_base64(img):
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def get_vlm_description(image):
    try:
        from utils.vlm_utils import get_blip_caption
        return get_blip_caption(image)
    except Exception as e:
        print(f"[VLM ERROR] {e}")
        return "[VLM description error]"

def from_docling(docling_json, pdf_path=None):
    blocks=[]
    pic_map = {p['self_ref']: p for p in docling_json.get('pictures',[])}
    text_map = {t['self_ref']: t for t in docling_json.get('texts',[])}
    body_children = docling_json.get('body',{}).get('children', [])
    # Extract all images from PDF using Docling
    images = []
    if pdf_path:
        try:
            images = extract_images_with_docling(pdf_path)
        except Exception as e:
            print(f"[ERROR] Docling image extraction failed: {e}")
    img_idx = 0
    for idx, elem in enumerate(body_children):
        if isinstance(elem, dict) and '$ref' in elem:
            ref = elem['$ref']
        else:
            ref = elem
        if ref.startswith('#/texts/'):
            t = text_map.get(ref)
            if t:
                blocks.append({"type":"paragraph","text_native":t.get("text",""),"confidence":1.0})
        elif ref.startswith('#/pictures/'):
            img_b64 = None
            img_desc = None
            if img_idx < len(images):
                item, pil_image = images[img_idx]
                try:
                    img_b64 = image_to_base64(pil_image)
                    print(f"[DEBUG] Encoded image {img_idx} to base64, length: {len(img_b64) if img_b64 else 0}")
                except Exception as e:
                    print(f"[ERROR] Base64 encoding failed: {e}")
                try:
                    img_desc = get_vlm_description(pil_image)
                except Exception as e:
                    print(f"[ERROR] VLM description failed: {e}")
                img_idx += 1
            else:
                img_desc = "Image from document."
            blocks.append({
                "type": "image",
                "description": img_desc,
                "base64": img_b64 if img_b64 is not None else "",
                "confidence": 1.0
            })
    if not blocks and "text" in docling_json:
        t = docling_json["text"]
        blocks.append({"type":"paragraph","text_native":t,"confidence":1.0})
    return blocks

def from_ocr(jsonl_path):
    # (unchanged)
    blocks=[]
    with open(jsonl_path,'r',encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            page = json.loads(line)
            items = page.get("items", [])
            if not items:
                blocks.append({"type":"paragraph","text_native":"", "confidence":0.0})
                continue
            txt = " ".join([i.get("text","") for i in items]).strip()
            confs = [float(i.get("conf",0.0)) for i in items if i.get("conf") is not None]
            conf = sum(confs)/len(confs) if confs else 0.0
            blocks.append({"type":"paragraph","text_native":txt,"confidence":conf})
    return blocks

if __name__=="__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc_id", required=True)
    ap.add_argument("--source_type", choices=["docling","ocr"], required=True)
    ap.add_argument("--source_path", required=True)
    ap.add_argument("--pdf_path", required=False)
    args = ap.parse_args()

    art_dir = Path("artifacts")/args.doc_id
    ensure_dir(art_dir)

    if args.source_type=="docling":
        # Load the docling JSON for doc.json
        with open(args.source_path,"r",encoding="utf-8") as f:
            doc = json.load(f)
        pdf_path = args.pdf_path if args.pdf_path else None
        blocks = from_docling(doc, pdf_path=pdf_path)
        write_json({"doc_id": args.doc_id, "blocks": blocks}, art_dir/"doc.json")

        # Generate Markdown with image description and base64 after <!-- image -->
        docling_md = Path(args.source_path).with_name("docling.md")
        out_md = art_dir/"doc.md"
        if docling_md.exists():
            md_lines = docling_md.read_text(encoding="utf-8").splitlines()
            new_lines = []
            img_idx = 0
            for line in md_lines:
                new_lines.append(line)
                if line.strip() == "<!-- image -->":
                    # Find next image block
                    while img_idx < len(blocks) and blocks[img_idx].get("type") != "image":
                        img_idx += 1
                    if img_idx < len(blocks):
                        img_block = blocks[img_idx]
                        desc = img_block.get("description") or "Image from document."
                        b64 = img_block.get("base64")
                        new_lines.append(f"**Image Description:** {desc}")
                        if b64:
                            # Ensure base64 is a single line
                            b64_single_line = b64.replace("\n", "")
                            new_lines.append(f"<details><summary>Base64</summary>\n\n```")
                            new_lines.append(b64_single_line)
                            new_lines.append("```")
                            new_lines.append("</details>")
                        img_idx += 1
            out_md.write_text("\n".join(new_lines), encoding="utf-8")
        else:
            # fallback: minimal MD from blocks
            md = "\n\n".join(b.get("text_native","") for b in blocks if b.get("type")=="paragraph")
            out_md.write_text(md, encoding="utf-8")
        print("wrote:", art_dir/"doc.json", out_md)

    else:
        # OCR path unchanged: create JSON & a simple MD
        blocks = from_ocr(args.source_path)
        write_json({"doc_id": args.doc_id, "blocks": blocks}, art_dir/"doc.json")
        md = "\n\n".join(b.get("text_native","") for b in blocks)
        (art_dir/"doc.md").write_text(md, encoding="utf-8")
        print("wrote:", art_dir/"doc.json", art_dir/"doc.md")