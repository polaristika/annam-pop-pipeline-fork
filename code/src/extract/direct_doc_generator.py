"""
Direct doc.md generation without intermediate files.
Single-pass: PDF → Docling → VLM → doc.md (with base64 images)
"""

import hashlib
import base64
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import torch
from docling.document_converter import DocumentConverter
from src.utils.vlm_utils import load_blip_model, batch_blip_captions
from src.utils.io import ensure_dir


def image_to_base64(pil_img):
    """Convert PIL image to base64 string"""
    buffered = BytesIO()
    pil_img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def generate_doc_md_direct(pdf_path, output_dir, doc_id):
    """
    Single-pass generation: PDF → doc.md with VLM descriptions and base64 images.
    
    Args:
        pdf_path: Path to input PDF
        output_dir: Directory to save doc.md
        doc_id: Document identifier for logging
    
    Returns:
        Path to generated doc.md file
    """
    print(f"[{doc_id}] Starting direct doc.md generation...")
    
    # Ensure output directory exists
    output_dir = Path(output_dir)
    ensure_dir(output_dir)
    
    # Step 1: Initialize Docling converter with image extraction enabled (ONCE!)
    print(f"[{doc_id}] Initializing Docling converter with image extraction...")
    from docling.document_converter import PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions, AcceleratorOptions, AcceleratorDevice
    from docling.datamodel.base_models import InputFormat

    pipeline_options = PdfPipelineOptions(
        generate_picture_images=True,  # CRITICAL: Enable image extraction
        images_scale=2.0,
        do_ocr=True,
        ocr_options=EasyOcrOptions(),
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CUDA)
    )
    
    conv = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    
    # Step 2: Convert PDF and extract all data
    print(f"[{doc_id}] Converting PDF: {pdf_path}")
    res = conv.convert(pdf_path)
    
    # Step 3: Extract markdown template
    print(f"[{doc_id}] Extracting markdown template...")
    md_template = None
    if hasattr(res, "document") and hasattr(res.document, "export_to_markdown"):
        try:
            md_template = res.document.export_to_markdown()
        except Exception as e:
            print(f"[{doc_id}] WARNING: Markdown export failed: {e}")
    
    # Fallback to text export if markdown not available
    if md_template is None and hasattr(res, "document") and hasattr(res.document, "export_to_text"):
        try:
            md_template = res.document.export_to_text()
        except Exception as e:
            print(f"[{doc_id}] WARNING: Text export failed: {e}")
    
    # Last resort: generate simple markdown from structure
    if md_template is None:
        print(f"[{doc_id}] Using fallback markdown generation...")
        if hasattr(res, "document") and hasattr(res.document, "export_to_dict"):
            data = res.document.export_to_dict()
            elements = data.get("elements", [])
            md_template = "# Document\n\n" + "\n\n".join(
                str(el.get("text", el.get("content", "")))
                for el in elements
                if isinstance(el, dict)
            )
        else:
            md_template = "# Document\n\nNo content extracted."
    
    # Step 4: Extract images (CRITICAL: do this once!)
    print(f"[{doc_id}] Extracting images from PDF...")
    images_data = []
    try:
        # Extract images using Docling's document iteration
        from docling_core.types.doc import PictureItem
        doc = res.document
        for item, _ in doc.iterate_items():
            if isinstance(item, PictureItem):
                pil_image = item.get_image(doc)
                if pil_image:
                    images_data.append((item, pil_image))
        print(f"[{doc_id}] Extracted {len(images_data)} images")
    except Exception as e:
        print(f"[{doc_id}] WARNING: Image extraction failed: {e}")
    
    # Step 5: VLM enrichment - batch BLIP inference on GPU + parallel base64
    print(f"[{doc_id}] Generating VLM descriptions for {len(images_data)} images...")
    enriched_images = []
    if images_data:
        pil_imgs = [pil_img for _, pil_img in images_data]

        # Deduplicate images by MD5 to avoid re-captioning identical images
        seen: dict[str, int] = {}
        unique_imgs = []
        img_to_unique: list[int] = []
        for img in pil_imgs:
            h = hashlib.md5(img.tobytes()).hexdigest()
            if h not in seen:
                seen[h] = len(unique_imgs)
                unique_imgs.append(img)
            img_to_unique.append(seen[h])
        print(f"[{doc_id}] {len(unique_imgs)} unique images (deduped from {len(pil_imgs)})")

        # Dynamic batch size: larger batches = better GPU utilization
        batch_size = min(32, max(8, len(unique_imgs)))

        blip_model = load_blip_model()
        try:
            unique_captions = batch_blip_captions(blip_model, unique_imgs, batch_size=batch_size)
        except Exception as e:
            print(f"[{doc_id}] WARNING: Batch VLM failed: {e}")
            unique_captions = ["Image from document."] * len(unique_imgs)

        torch.cuda.empty_cache()
        captions = [unique_captions[i] for i in img_to_unique]

        # Parallel base64 encoding (CPU-bound, runs while GPU is free)
        def _encode(img):
            try:
                return image_to_base64(img)
            except Exception:
                return ""

        with ThreadPoolExecutor() as executor:
            base64_results = list(executor.map(_encode, pil_imgs))

        for idx, (description, base64_data) in enumerate(zip(captions, base64_results)):
            print(f"[{doc_id}] Image {idx}: {description[:60]}...")
            enriched_images.append({'description': description, 'base64': base64_data})
    
    # Step 6: Generate final enriched markdown
    print(f"[{doc_id}] Merging markdown template with enriched images...")
    md_lines = md_template.splitlines()
    final_lines = []
    img_idx = 0
    
    for line in md_lines:
        final_lines.append(line)
        
        # Look for image markers
        if line.strip() == "<!-- image -->" and img_idx < len(enriched_images):
            img = enriched_images[img_idx]
            
            # Add image description
            final_lines.append(f"\n**Image Description:** {img['description']}\n")
            
            # Add base64 in collapsible section
            if img['base64']:
                final_lines.append("<details><summary>Base64 Image Data</summary>\n")
                final_lines.append("```")
                final_lines.append(img['base64'])
                final_lines.append("```")
                final_lines.append("</details>\n")
            
            img_idx += 1
    
    # Step 7: Write only doc.md (single file output!)
    out_path = output_dir / 'doc.md'
    final_content = '\n'.join(final_lines)
    
    print(f"[{doc_id}] Writing doc.md ({len(final_content)} chars)...")
    out_path.write_text(final_content, encoding='utf-8')
    
    print(f"[{doc_id}] ✓ Generated: {out_path}")
    print(f"[{doc_id}] ✓ Images processed: {img_idx}/{len(enriched_images)}")
    
    return out_path


if __name__ == "__main__":
    import argparse
    
    ap = argparse.ArgumentParser(description="Generate doc.md directly from PDF")
    ap.add_argument("--pdf", required=True, help="Path to input PDF")
    ap.add_argument("--out_dir", required=True, help="Output directory for doc.md")
    ap.add_argument("--doc_id", required=True, help="Document ID for logging")
    
    args = ap.parse_args()
    
    generate_doc_md_direct(args.pdf, args.out_dir, args.doc_id)
