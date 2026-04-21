"""
Minimal Phase 6 pipeline stub for garbled text processing.

This implementation is intentionally lightweight: it reuses the Phase 2
workflow (PDF -> MD -> JSON) and returns outputs. It's a placeholder until
the full text-replacement pipeline is available.
"""
from pathlib import Path
import json

def _generate_md_and_json(pdf_path: str, out_dir: str, doc_id: str, state: str = None):
    """Reuse Phase 2 components to generate MD and JSON as placeholders."""
    try:
        from extract.direct_doc_generator import generate_doc_md_direct
        from structure.md_to_json_converter_ultra import UltraFastMarkdownToJsonConverter
    except Exception as e:
        return {'status': 'failed', 'error': f'Missing pipeline components: {e}'}

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: generate md
    md_path = generate_doc_md_direct(pdf_path, out_dir, doc_id)
    if not md_path or not Path(md_path).exists():
        return {'status': 'failed', 'error': 'Markdown generation failed'}

    # Step 2: convert md to json
    converter = UltraFastMarkdownToJsonConverter()
    json_data = converter.convert_md_to_json(str(md_path), doc_id, metadata={'Source': 'phase6_fallback', 'State': state or ''})
    json_path = out_dir / f"{Path(pdf_path).stem}_output.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    # Rename md
    final_md_path = out_dir / f"{Path(pdf_path).stem}_document.md"
    if Path(md_path) != final_md_path:
        Path(md_path).rename(final_md_path)

    return {
        'status': 'success',
        'json_path': str(json_path.absolute()),
        'md_path': str(final_md_path.absolute())
    }


class ImprovedPhase6PipelineV2:
    """Minimal Phase 6 pipeline wrapper."""

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu

    def process_pdf(self, pdf_path: str, state: str = None, output_dir: str = None, doc_id: str = None):
        """Process a PDF and write outputs to the provided directory.

        This stub produces an MD and JSON using the Phase 2 flow.
        """
        if output_dir is None:
            output_dir = '.'

        if doc_id is None:
            doc_id = Path(pdf_path).stem

        return _generate_md_and_json(pdf_path, output_dir, doc_id, state=state)
