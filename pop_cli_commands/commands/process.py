"""
Process command for individual or small batch PDF processing
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys
import json
import time

code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

from pop_cli_commands.core.base import BaseCommand


class ProcessCommand(BaseCommand):
    """Command for processing individual PDFs or small batches."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--phase', type=int, choices=[1, 2], required=True,
                           help='Processing phase (1=English, 2=Indic)')
        parser.add_argument('--count', type=int, default=1,
                           help='Number of PDFs to process (default: 1)')
        parser.add_argument('--file', type=str,
                           help='Specific PDF file to process')
        parser.add_argument('--doc-id', type=str,
                           help='Specific document ID to process')
        parser.add_argument('--min-confidence', type=float,
                           help='Minimum confidence threshold (overrides config)')
        parser.add_argument('--state', type=str,
                           help='Process only files from specific state')
        parser.add_argument('--dry-run', action='store_true',
                           help='Show what would be processed without actually processing')
        parser.add_argument('--force', action='store_true',
                           help='Force reprocessing even if output exists')
        parser.add_argument('--gpu', action='store_true',
                           help='Enable GPU acceleration if available')
    
    def execute(self) -> bool:
        """Execute process command."""
        try:
            # Load inventory
            inventory_path = self.config.get('paths.inventory_csv')
            if not Path(inventory_path).exists():
                print("❌ Inventory not found. Run 'pop-cli inventory --scan' first.")
                return False
            
            df = pd.read_csv(inventory_path)
            
            # Select files to process
            files_to_process = self._select_files(df)
            
            if not files_to_process:
                print("❌ No files match the specified criteria.")
                return False
            
            # Show what will be processed
            print(f"🎯 Selected {len(files_to_process)} files for Phase {self.args.phase} processing:")
            for i, (_, row) in enumerate(files_to_process.iterrows(), 1):
                filename = Path(row['file_path']).name
                print(f"  {i:2d}. {filename:<30} {row['state']:<15} conf: {row['lang_conf']:.3f}")
            print()
            
            if self.args.dry_run:
                print("🔍 Dry run complete. Use --count to process these files.")
                return True
            
            # Confirm processing
            if not self.args.force and len(files_to_process) > 1:
                response = input(f"Process {len(files_to_process)} files? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("❌ Processing cancelled.")
                    return False
            
            # Process files
            return self._process_files(files_to_process)
            
        except Exception as e:
            self.logger.error(f"Process command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _select_files(self, df: pd.DataFrame) -> pd.DataFrame:
        """Select files based on criteria."""
        # Start with phase criteria
        phase_criteria = self.config.get_phase_criteria(self.args.phase)
        selected = self._filter_by_criteria(df, phase_criteria)
        
        # Apply additional filters
        if self.args.min_confidence:
            selected = selected[selected['lang_conf'] >= self.args.min_confidence]
        
        if self.args.state:
            selected = selected[selected['state'].str.contains(self.args.state, case=False, na=False)]
        
        if self.args.file:
            # Specific file
            file_path = Path(self.args.file)
            if file_path.is_absolute():
                selected = selected[selected['file_path'] == str(file_path)]
            else:
                # Match by filename
                selected = selected[selected['file_path'].str.endswith(str(file_path))]
        
        if self.args.doc_id:
            # This would require a doc_id column in inventory
            if 'doc_id' in selected.columns:
                selected = selected[selected['doc_id'] == self.args.doc_id]
        
        # Limit count
        if self.args.count and len(selected) > self.args.count:
            # Sort by confidence (highest first) for best results
            selected = selected.nlargest(self.args.count, 'lang_conf')
        
        return selected
    
    def _filter_by_criteria(self, df: pd.DataFrame, criteria: Dict[str, Any]) -> pd.DataFrame:
        """Filter DataFrame by phase criteria."""
        filtered = df.copy()
        
        for field, value in criteria.items():
            if field.endswith('_min'):
                # Handle minimum value criteria
                base_field = field.replace('_min', '')
                if base_field in filtered.columns:
                    filtered = filtered[filtered[base_field] >= value]
            else:
                # Handle exact match criteria
                if field in filtered.columns:
                    filtered = filtered[filtered[field] == value]
        
        return filtered
    
    def _process_files(self, files_df: pd.DataFrame) -> bool:
        """Process the selected files."""
        phase_config = self.config.get_phase_config(self.args.phase)
        output_base = self.config.get(f'paths.phase{self.args.phase}_output')
        
        print(f"🔄 Starting Phase {self.args.phase} processing...")
        print(f"📂 Output directory: {output_base}")
        print()
        
        success_count = 0
        failure_count = 0
        
        for i, (_, row) in enumerate(files_df.iterrows(), 1):
            pdf_path = row['file_path']
            filename = Path(pdf_path).name
            doc_id = Path(pdf_path).stem
            state = row['state']
            
            print(f"[{i}/{len(files_df)}] Processing: {filename}")
            
            try:
                # Check if already processed
                output_dir = Path(output_base) / 'raw' / doc_id
                if output_dir.exists() and not self.args.force:
                    print(f"  ⏭️  Already processed (use --force to reprocess)")
                    success_count += 1
                    continue
                
                # Process the file
                success = self._process_single_file(pdf_path, doc_id, state, output_dir)
                
                if success:
                    print(f"  ✅ Success")
                    success_count += 1
                else:
                    print(f"  ❌ Failed")
                    failure_count += 1
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
                failure_count += 1
                self.logger.error(f"Failed to process {filename}: {e}")
        
        # Summary
        print()
        print("📊 PROCESSING SUMMARY")
        print("=" * 30)
        print(f"✅ Successful: {success_count}")
        print(f"❌ Failed:     {failure_count}")
        print(f"📊 Success rate: {(success_count / len(files_df) * 100):0.1f}%")
        
        return failure_count == 0
    
    def _process_single_file(self, pdf_path: str, doc_id: str, state: str, output_dir: Path) -> bool:
        """Process a single PDF file."""
        try:
            # This is where we would call the actual pipeline
            # For now, create a placeholder implementation
            
            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create placeholder files
            results = {
                'doc_id': doc_id,
                'state': state,
                'phase': self.args.phase,
                'input_file': pdf_path,
                'processing_time': time.time(),
                'status': 'success',
                'outputs': {
                    'extracted_json': str(output_dir / 'doc_extracted.json'),
                    'translated_json': str(output_dir / 'doc_translated.json'),
                    'markdown': str(output_dir / 'doc_translated.md'),
                    'images_dir': str(output_dir / 'images')
                }
            }
            
            # Save processing metadata
            with open(output_dir / 'processing_info.json', 'w') as f:
                json.dump(results, f, indent=2)
            
            # TODO: Replace with actual pipeline call:
            # pipeline = ImprovedPhase6PipelineV2(use_gpu=self.args.gpu)
            # result = pipeline.process_pdf(
            #     pdf_path=Path(pdf_path),
            #     output_dir=output_dir,
            #     doc_id=doc_id,
            #     state=state
            # )
            
            print(f"  📄 Created processing metadata")
            return True
            
        except Exception as e:
            self.logger.error(f"Processing failed for {doc_id}: {e}")
            return False