# src/extract/docling_runner.py
import os, json, argparse
from pathlib import Path
from utils.io import ensure_dir, write_json
from docling.document_converter import DocumentConverter

def run_docling(pdf_path, out_json):
    conv = DocumentConverter()
    res = conv.convert(pdf_path)

    # --- JSON serialization (as you already had, with robust fallbacks) ---
    data = None
    if hasattr(res, "document") and hasattr(res.document, "export_to_dict"):
        data = res.document.export_to_dict()
    if data is None and hasattr(res, "to_json"):
        try:
            data = json.loads(res.to_json())
        except Exception:
            data = None
    if data is None:
        data = {"elements": [], "meta": {"note": "fallback serialization"}}

    out_json_path = Path(out_json)
    ensure_dir(out_json_path.parent)
    write_json(data, out_json_path)

    # --- NEW: direct Markdown export from Docling ---
    # Write alongside the JSON: same folder, name 'docling.md'
    out_md_path = out_json_path.with_name("docling.md")
    md_text = None
    # Preferred API on recent Docling:
    if hasattr(res, "document") and hasattr(res.document, "export_to_markdown"):
        try:
            md_text = res.document.export_to_markdown()
        except Exception:
            md_text = None
    # Fallback: some versions expose HTML export; we can degrade to plain text if needed
    if md_text is None and hasattr(res, "document") and hasattr(res.document, "export_to_text"):
        try:
            md_text = res.document.export_to_text()  # less rich than markdown, but still structured text
        except Exception:
            md_text = None

    if md_text is None:
        # last-resort degenerate MD if exporter isn’t available
        md_text = "# Document\n\n" + "\n\n".join(
            (el.get("text") or el.get("content") or "")
            for el in data.get("elements", [])
            if isinstance(el, dict)
        )

    with open(out_md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)  # e.g., artifacts/<doc_id>/docling.json
    args = ap.parse_args()
    run_docling(args.doc, args.out)
    print("docling done:", args.out, "and docling.md")
