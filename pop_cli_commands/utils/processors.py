"""
Processing utilities for direct PDF processing.

Wrappers around Phase 1 and Phase 2 pipelines for single PDF processing.
"""

import sys
from pathlib import Path
from typing import Dict

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "code" / "src"))


def process_with_docling(pdf_path: str, output_dir: str) -> Dict:
    """
    Process PDF using Phase 1 Docling pipeline.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save outputs
        
    Returns:
        Dict with status, json_path, md_path, or error
    """
    try:
        from extract.docling_runner import run_docling
        from pathlib import Path
        
        # Setup paths
        pdf_name = Path(pdf_path).stem
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        json_path = out_dir / f"{pdf_name}_output.json"
        md_path = out_dir / "docling.md"
        
        # Run Docling
        run_docling(pdf_path, str(json_path))
        
        # Verify outputs
        if not json_path.exists():
            return {
                'status': 'failed',
                'error': 'JSON output not generated'
            }
        
        if not md_path.exists():
            return {
                'status': 'failed',
                'error': 'Markdown output not generated'
            }
        
        # Rename MD to match PDF name
        final_md_path = out_dir / f"{pdf_name}_document.md"
        md_path.rename(final_md_path)
        
        return {
            'status': 'success',
            'json_path': str(json_path.absolute()),
            'md_path': str(final_md_path.absolute())
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


def process_with_phase2(pdf_path: str, output_dir: str) -> Dict:
    """
    Process PDF using Phase 2 pipeline (direct_doc_generator).
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save outputs
        
    Returns:
        Dict with status, json_path, md_path, or error
    """
    try:
        # Import Phase 2 modules
        from extract.direct_doc_generator import generate_doc_md_direct
        from structure.md_to_json_converter_ultra import UltraFastMarkdownToJsonConverter
        from pathlib import Path
        import json
        
        # Setup paths
        pdf_name = Path(pdf_path).stem
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        doc_id = pdf_name.replace(' ', '_').replace('-', '_')[:50]
        
        # Step 1: PDF → doc.md (with OCR and VLM)
        print(f"   [1/2] Generating markdown with OCR...")
        md_path = generate_doc_md_direct(pdf_path, out_dir, doc_id)
        
        if not md_path.exists():
            return {
                'status': 'failed',
                'error': 'Markdown generation failed'
            }
        
        # Step 2: doc.md → doc.json
        print(f"   [2/2] Converting to JSON...")
        converter = UltraFastMarkdownToJsonConverter()
        
        metadata = {
            "Name": pdf_name,
            "Source": "direct_processing"
        }
        
        json_data = converter.convert_md_to_json(str(md_path), doc_id, metadata)
        
        json_path = out_dir / f"{pdf_name}_output.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        if not json_path.exists():
            return {
                'status': 'failed',
                'error': 'JSON conversion failed'
            }
        
        # Rename MD to match naming convention
        final_md_path = out_dir / f"{pdf_name}_document.md"
        if md_path != final_md_path:
            md_path.rename(final_md_path)
        
        return {
            'status': 'success',
            'json_path': str(json_path.absolute()),
            'md_path': str(final_md_path.absolute())
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'error': str(e)
        }


__all__ = ['process_with_docling', 'process_with_phase2']


def process_with_phase6(pdf_path: str, output_dir: str, state: str = None) -> Dict:
    """
    Process PDF using Phase 6 pipeline (garbled text restoration).

    Falls back to Phase 2 pipeline if Phase 6 is not available.
    """
    try:
        # Try to import the Phase 6 pipeline
        from pipeline.phase6_improved_v2_json import ImprovedPhase6PipelineV2
        from pathlib import Path

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        pipeline = ImprovedPhase6PipelineV2()
        # Some pipeline implementations expect Path objects
        res = pipeline.process_pdf(pdf_path=str(pdf_path), state=state, output_dir=str(out_dir))

        # Expect res to include 'status' and possibly paths
        if res.get('status') == 'success':
            # Look for expected outputs
            json_path = res.get('json_path') or str(out_dir / (Path(pdf_path).stem + '_output.json'))
            md_path = res.get('md_path') or str(out_dir / (Path(pdf_path).stem + '_document.md'))
            return {
                'status': 'success',
                'json_path': json_path,
                'md_path': md_path
            }
        else:
            return {
                'status': 'failed',
                'error': res.get('error', 'Phase 6 pipeline failed')
            }

    except ImportError:
        # Phase 6 pipeline missing; fallback to Phase 2
        print("   ℹ️  Phase 6 pipeline not found, falling back to Phase 2 processing")
        return process_with_phase2(pdf_path, output_dir)
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


__all__ = ['process_with_docling', 'process_with_phase2', 'process_with_phase6']
