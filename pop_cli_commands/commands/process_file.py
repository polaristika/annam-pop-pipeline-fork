"""
Process single PDF file command.

Directly process any PDF file by:
1. Classifying it (Phase 1 English or Phase 2 Indic)
2. Routing to appropriate processor
3. Generating JSON + Markdown outputs
4. Returning output paths

Usage:
    python pop_cli.py process-file <pdf_path>
    python pop_cli.py process-file <pdf_path> --output-dir custom/path
    python pop_cli.py process-file <pdf_path> --force-phase 1
"""

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
import json
from datetime import datetime

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "code" / "src"))

from classify.english_vs_indic import english_vs_indic
from pop_cli_commands.core.config import load_config


class ProcessFileCommand:
    """Process single PDF file directly."""
    
    def __init__(self, config=None):
        self.config = config or load_config()
        self.output_base = Path("artifacts/direct_processing")
        self.output_base.mkdir(parents=True, exist_ok=True)
    
    def classify_pdf(self, pdf_path: str) -> Tuple[Optional[int], Dict]:
        """
        Classify PDF and determine which phase can process it.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (phase_number, classification_result)
            phase_number: 1 (English), 2 (Indic), or None (not processable)
            classification_result: Dict with classification details
        """
        print(f"\n📊 Classifying PDF: {Path(pdf_path).name}")
        
        try:
            # Run classification
            result = english_vs_indic(pdf_path, pages=3)
            
            lang_guess = result.get('lang_guess', 'unsure')
            lang_conf = result.get('lang_conf', 0.0)
            garbled = result.get('garbled_detected', False)
            
            print(f"   Language: {lang_guess}")
            print(f"   Confidence: {lang_conf:.2f}")
            print(f"   Garbled: {garbled}")
            
            # Determine phase based on classification results
            # Priority: Garbled → Phase 6, then Indic → Phase 2, then English → Phase 1
            
            # Phase 6: Garbled text PDFs (HIGHEST PRIORITY)
            # Criteria: garbled_detected=True
            # These need OCR + text replacement, not standard Docling extraction
            if garbled:
                print(f"   ⚠️  Phase 6 (Garbled Text) - Not yet integrated")
                print(f"      Reason: Contains garbled Unicode requiring OCR text replacement")
                print(f"      Action: Phase 6 pipeline exists but not yet integrated into CLI")
                return None, result
            
            # Phase 1: English PDFs
            # Criteria: lang_guess='en', lang_conf>=0.5, digital_guess=True
            if lang_guess == 'en' and lang_conf >= 0.5:
                print(f"   ✅ Phase 1 (English) - Processable")
                return 1, result
            
            # Phase 2: Clean Indic PDFs (no garbled text)
            # Criteria: lang_guess='indic', lang_conf>=0.3, garbled_detected=False
            if lang_guess == 'indic' and lang_conf >= 0.3:
                print(f"   ✅ Phase 2 (Indic) - Processable")
                return 2, result
            
            # Not processable by current phases
            print(f"   ❌ Not processable (Phase 3-6 required)")
            print(f"      Reason: Confidence too low or needs scanned PDF processing")
            return None, result
            
        except Exception as e:
            print(f"   ❌ Classification failed: {e}")
            return None, {'error': str(e)}
    
    def process_phase1(self, pdf_path: str, output_dir: Path) -> Dict:
        """
        Process English PDF using Phase 1 pipeline (Docling).
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save outputs
            
        Returns:
            Dict with output paths and processing status
        """
        print(f"\n🔄 Processing with Phase 1 pipeline (Docling)...")
        
        try:
            from pop_cli_commands.utils.processors import process_with_docling
            
            # Process PDF
            result = process_with_docling(pdf_path, output_dir=str(output_dir))
            
            if result.get('status') == 'success':
                print(f"   ✅ Processing complete")
                return {
                    'status': 'success',
                    'phase': 1,
                    'json_path': result.get('json_path'),
                    'md_path': result.get('md_path'),
                    'output_dir': str(output_dir)
                }
            else:
                print(f"   ❌ Processing failed: {result.get('error', 'Unknown error')}")
                return {
                    'status': 'failed',
                    'phase': 1,
                    'error': result.get('error', 'Unknown error')
                }
                
        except ImportError as e:
            print(f"   ❌ Phase 1 processor not available: {e}")
            return {
                'status': 'failed',
                'phase': 1,
                'error': f'Phase 1 processor not available: {e}'
            }
        except Exception as e:
            print(f"   ❌ Processing failed: {e}")
            return {
                'status': 'failed',
                'phase': 1,
                'error': str(e)
            }
    
    def process_phase2(self, pdf_path: str, output_dir: Path) -> Dict:
        """
        Process Indic PDF using Phase 2 pipeline (OCR + Translation).
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save outputs
            
        Returns:
            Dict with output paths and processing status
        """
        print(f"\n🔄 Processing with Phase 2 pipeline (OCR + Translation)...")
        
        try:
            from pop_cli_commands.utils.processors import process_with_phase2
            
            # Process PDF
            result = process_with_phase2(pdf_path, output_dir=str(output_dir))
            
            if result.get('status') == 'success':
                print(f"   ✅ Processing complete")
                return {
                    'status': 'success',
                    'phase': 2,
                    'json_path': result.get('json_path'),
                    'md_path': result.get('md_path'),
                    'output_dir': str(output_dir)
                }
            else:
                print(f"   ❌ Processing failed: {result.get('error', 'Unknown error')}")
                return {
                    'status': 'failed',
                    'phase': 2,
                    'error': result.get('error', 'Unknown error')
                }
                
        except ImportError as e:
            print(f"   ❌ Phase 2 processor not available: {e}")
            return {
                'status': 'failed',
                'phase': 2,
                'error': f'Phase 2 processor not available: {e}'
            }
        except Exception as e:
            print(f"   ❌ Processing failed: {e}")
            return {
                'status': 'failed',
                'phase': 2,
                'error': str(e)
            }
    
    def save_manifest(self, pdf_path: str, classification: Dict, processing_result: Dict, output_dir: Path):
        """Save processing manifest with all details."""
        manifest = {
            'timestamp': datetime.now().isoformat(),
            'input_pdf': str(Path(pdf_path).absolute()),
            'pdf_name': Path(pdf_path).name,
            'classification': classification,
            'processing': processing_result,
            'outputs': {
                'json': processing_result.get('json_path'),
                'markdown': processing_result.get('md_path'),
                'directory': str(output_dir)
            }
        }
        
        manifest_path = output_dir / "processing_manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Manifest saved: {manifest_path}")
        return manifest_path
    
    def run(self, pdf_path: str, output_dir: Optional[str] = None, force_phase: Optional[int] = None, dry_run: bool = False) -> Dict:
        """
        Main execution method for process-file command.
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Custom output directory (optional)
            force_phase: Force specific phase (1 or 2), skip classification
            dry_run: Only classify, don't process
            
        Returns:
            Dict with processing results
        """
        # Validate PDF exists
        pdf_path = Path(pdf_path).absolute()
        if not pdf_path.exists():
            print(f"❌ Error: PDF not found: {pdf_path}")
            return {'status': 'failed', 'error': 'File not found'}
        
        if not pdf_path.suffix.lower() == '.pdf':
            print(f"❌ Error: Not a PDF file: {pdf_path}")
            return {'status': 'failed', 'error': 'Not a PDF file'}
        
        print(f"\n{'='*60}")
        print(f"🚀 Processing PDF: {pdf_path.name}")
        print(f"{'='*60}")
        
        # Determine output directory
        if output_dir:
            out_dir = Path(output_dir)
        else:
            # Create timestamped directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = pdf_path.stem.replace(' ', '_')[:50]
            out_dir = self.output_base / f"{safe_name}_{timestamp}"
        
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Output directory: {out_dir}")
        
        # Classify PDF (unless forced)
        if force_phase:
            print(f"\n⚠️  Forced to Phase {force_phase} (skipping classification)")
            phase = force_phase
            classification = {'forced': True, 'phase': force_phase}
        else:
            phase, classification = self.classify_pdf(str(pdf_path))
        
        if phase is None:
            print(f"\n❌ Cannot process this PDF with current phases (1-2)")
            print(f"   This PDF requires Phase 3-6 processing (not yet implemented)")
            return {
                'status': 'not_processable',
                'classification': classification,
                'reason': 'Requires Phase 3-6 (scanned PDFs or error recovery)'
            }
        
        if dry_run:
            print(f"\n🔍 DRY RUN - Classification only")
            print(f"   Would process with Phase {phase}")
            return {
                'status': 'dry_run',
                'phase': phase,
                'classification': classification,
                'output_dir': str(out_dir)
            }
        
        # Route to appropriate processor
        if phase == 1:
            result = self.process_phase1(str(pdf_path), out_dir)
        elif phase == 2:
            result = self.process_phase2(str(pdf_path), out_dir)
        else:
            return {'status': 'failed', 'error': f'Invalid phase: {phase}'}
        
        # Save manifest
        if result.get('status') == 'success':
            self.save_manifest(str(pdf_path), classification, result, out_dir)
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS!")
            print(f"{'='*60}")
            print(f"📊 Phase: {phase}")
            if result.get('json_path'):
                print(f"📄 JSON: {result['json_path']}")
            if result.get('md_path'):
                print(f"📝 Markdown: {result['md_path']}")
            print(f"📁 All files: {out_dir}")
            print(f"{'='*60}\n")
        
        return result


def add_parser(subparsers):
    """Add process-file command to CLI argument parser."""
    parser = subparsers.add_parser(
        'process-file',
        help='Process a single PDF file directly',
        description='Classify and process any PDF file directly without inventory scan'
    )
    
    parser.add_argument(
        'pdf_path',
        type=str,
        help='Path to PDF file to process'
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        help='Custom output directory (default: artifacts/direct_processing/<filename>_<timestamp>)'
    )
    
    parser.add_argument(
        '--force-phase',
        type=int,
        choices=[1, 2],
        help='Force specific phase (1=English, 2=Indic), skip classification'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Only classify PDF, do not process'
    )
    
    parser.set_defaults(func=execute)


def execute(args):
    """Execute process-file command."""
    command = ProcessFileCommand()
    result = command.run(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        force_phase=args.force_phase,
        dry_run=args.dry_run
    )
    
    # Exit with appropriate code
    if result.get('status') == 'success':
        sys.exit(0)
    elif result.get('status') == 'not_processable':
        sys.exit(2)  # Special code for "not processable"
    else:
        sys.exit(1)
