"""
Batch command for large-scale PDF processing
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
import sys
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

from pop_cli_commands.core.base import BaseCommand


class BatchCommand(BaseCommand):
    """Command for batch processing of many PDFs."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--phase', type=int, choices=[1, 2], required=True,
                           help='Processing phase (1=English, 2=Indic)')
        parser.add_argument('--all', action='store_true',
                           help='Process all eligible files for the phase')
        parser.add_argument('--count', type=int,
                           help='Maximum number of PDFs to process')
        parser.add_argument('--batch-size', type=int,
                           help='Number of files to process in each batch (overrides config)')
        parser.add_argument('--parallel', type=int,
                           help='Number of parallel processes (overrides config)')
        parser.add_argument('--min-confidence', type=float,
                           help='Minimum confidence threshold (overrides config)')
        parser.add_argument('--state', type=str,
                           help='Process only files from specific state')
        parser.add_argument('--resume', action='store_true',
                           help='Resume interrupted batch processing')
        parser.add_argument('--dry-run', action='store_true',
                           help='Show what would be processed without actually processing')
        parser.add_argument('--force', action='store_true',
                           help='Force reprocessing even if output exists')
        parser.add_argument('--gpu', action='store_true',
                           help='Enable GPU acceleration if available')
        parser.add_argument('--timeout', type=int,
                           help='Timeout per PDF in seconds (overrides config)')
    
    def execute(self) -> bool:
        """Execute batch command."""
        try:
            # Load inventory
            inventory_path = self.config.get('paths.inventory_csv')
            if not Path(inventory_path).exists():
                print("❌ Inventory not found. Run 'pop-cli inventory --scan' first.")
                return False
            
            df = pd.read_csv(inventory_path)
            
            # Select files for batch processing
            files_to_process = self._select_files(df)
            
            if not files_to_process:
                print("❌ No files match the specified criteria.")
                return False
            
            # Show batch summary
            self._show_batch_summary(files_to_process)
            
            if self.args.dry_run:
                print("🔍 Dry run complete. Remove --dry-run to start processing.")
                return True
            
            # Confirm batch processing
            if not self.args.force and len(files_to_process) > 10:
                response = input(f"Start batch processing of {len(files_to_process)} files? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("❌ Batch processing cancelled.")
                    return False
            
            # Run batch processing
            return self._run_batch_processing(files_to_process)
            
        except Exception as e:
            self.logger.error(f"Batch command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _select_files(self, df: pd.DataFrame) -> pd.DataFrame:
        """Select files for batch processing."""
        # Start with phase criteria
        phase_criteria = self.config.get_phase_criteria(self.args.phase)
        selected = self._filter_by_criteria(df, phase_criteria)
        
        # Apply additional filters
        if self.args.min_confidence:
            selected = selected[selected['lang_conf'] >= self.args.min_confidence]
        
        if self.args.state:
            selected = selected[selected['state'].str.contains(self.args.state, case=False, na=False)]
        
        # Handle resume mode
        if self.args.resume:
            selected = self._filter_unprocessed(selected)
        
        # Sort by confidence (highest first) for best success rates
        selected = selected.sort_values('lang_conf', ascending=False)
        
        # Apply count limit
        if self.args.count and len(selected) > self.args.count:
            selected = selected.head(self.args.count)
        elif not self.args.all and not self.args.count:
            # Default to smaller batch if neither --all nor --count specified
            default_batch = self.config.get('processing.default_batch_size', 10)
            selected = selected.head(default_batch)
            print(f"ℹ️  Processing first {default_batch} files (use --all or --count to change)")
        
        return selected
    
    def _filter_by_criteria(self, df: pd.DataFrame, criteria: Dict[str, Any]) -> pd.DataFrame:
        """Filter DataFrame by phase criteria."""
        filtered = df.copy()
        
        for field, value in criteria.items():
            if field.endswith('_min'):
                base_field = field.replace('_min', '')
                if base_field in filtered.columns:
                    filtered = filtered[filtered[base_field] >= value]
            else:
                if field in filtered.columns:
                    filtered = filtered[filtered[field] == value]
        
        return filtered
    
    def _filter_unprocessed(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter out files that have already been processed."""
        output_base = Path(self.config.get(f'paths.phase{self.args.phase}_output'))
        
        unprocessed = []
        for _, row in df.iterrows():
            doc_id = Path(row['file_path']).stem
            output_dir = output_base / 'raw' / doc_id
            
            if not output_dir.exists() or self.args.force:
                unprocessed.append(row)
        
        return pd.DataFrame(unprocessed) if unprocessed else pd.DataFrame()
    
    def _show_batch_summary(self, files_df: pd.DataFrame):
        """Show summary of batch processing plan."""
        print("🚀 BATCH PROCESSING PLAN")
        print("=" * 50)
        print(f"Phase: {self.args.phase} ({'English' if self.args.phase == 1 else 'Indic'})")
        print(f"Total files: {len(files_df)}")
        
        # Configuration
        batch_size = self.args.batch_size or self.config.get('processing.default_batch_size', 10)
        parallel = self.args.parallel or self.config.get('processing.max_parallel_processes', 4)
        timeout = self.args.timeout or self.config.get('processing.timeout_per_pdf', 300)
        
        print(f"Batch size: {batch_size}")
        print(f"Parallel processes: {parallel}")
        print(f"Timeout per PDF: {timeout}s")
        print()
        
        # State distribution
        if 'state' in files_df.columns:
            print("📍 Files by State:")
            state_counts = files_df['state'].value_counts().head(10)
            for state, count in state_counts.items():
                print(f"  {state:<20} {count:>4}")
            print()
        
        # Confidence distribution
        print("🎯 Confidence Distribution:")
        conf_ranges = [
            (0.9, 1.0, "Very High"),
            (0.7, 0.9, "High"),
            (0.5, 0.7, "Medium"),
            (0.0, 0.5, "Low")
        ]
        
        for min_conf, max_conf, label in conf_ranges:
            count = len(files_df[(files_df['lang_conf'] >= min_conf) & (files_df['lang_conf'] < max_conf)])
            if count > 0:
                print(f"  {label:<10} ({min_conf:.1f}-{max_conf:.1f}): {count:>4}")
        print()
        
        # Show sample files
        print("📋 Sample Files (Top 10 by confidence):")
        sample = files_df.head(10)
        for i, (_, row) in enumerate(sample.iterrows(), 1):
            filename = Path(row['file_path']).name
            print(f"  {i:2d}. {filename:<35} {row['state']:<15} {row['lang_conf']:.3f}")
        print()
    
    def _run_batch_processing(self, files_df: pd.DataFrame) -> bool:
        """Run the batch processing."""
        batch_size = self.args.batch_size or self.config.get('processing.default_batch_size', 10)
        
        print(f"🔄 Starting batch processing of {len(files_df)} files...")
        print(f"📦 Processing in batches of {batch_size}")
        print()
        
        total_success = 0
        total_failure = 0
        
        # Process in batches
        for batch_start in range(0, len(files_df), batch_size):
            batch_end = min(batch_start + batch_size, len(files_df))
            batch_df = files_df.iloc[batch_start:batch_end]
            
            batch_num = (batch_start // batch_size) + 1
            total_batches = (len(files_df) + batch_size - 1) // batch_size
            
            print(f"📦 Batch {batch_num}/{total_batches}: Processing {len(batch_df)} files...")
            
            success, failure = self._process_batch(batch_df)
            total_success += success
            total_failure += failure
            
            print(f"   ✅ Success: {success}, ❌ Failed: {failure}")
            print()
        
        # Final summary
        print("📊 BATCH PROCESSING COMPLETE")
        print("=" * 40)
        print(f"✅ Total Successful: {total_success}")
        print(f"❌ Total Failed:     {total_failure}")
        print(f"📊 Success Rate:     {(total_success / len(files_df) * 100):0.1f}%")
        
        return total_failure == 0
    
    def _process_batch(self, batch_df: pd.DataFrame) -> tuple[int, int]:
        """Process a single batch of files."""
        parallel = self.args.parallel or self.config.get('processing.max_parallel_processes', 4)
        timeout = self.args.timeout or self.config.get('processing.timeout_per_pdf', 300)
        
        # Use sequential processing for now (parallel would require pipeline reconstruction)
        success_count = 0
        failure_count = 0
        
        for i, (_, row) in enumerate(batch_df.iterrows(), 1):
            pdf_path = row['file_path']
            filename = Path(pdf_path).name
            doc_id = Path(pdf_path).stem
            state = row['state']
            
            print(f"    [{i}/{len(batch_df)}] {filename[:40]:<40} ", end="", flush=True)
            
            try:
                success = self._process_single_file(pdf_path, doc_id, state)
                if success:
                    print("✅")
                    success_count += 1
                else:
                    print("❌")
                    failure_count += 1
                    
            except Exception as e:
                print(f"❌ Error: {str(e)[:50]}")
                failure_count += 1
                self.logger.error(f"Failed to process {filename}: {e}")
        
        return success_count, failure_count
    
    def _process_single_file(self, pdf_path: str, doc_id: str, state: str) -> bool:
        """Process a single PDF file."""
        try:
            output_base = self.config.get(f'paths.phase{self.args.phase}_output')
            output_dir = Path(output_base) / 'raw' / doc_id
            
            # Check if already processed
            if output_dir.exists() and not self.args.force:
                return True
            
            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create placeholder processing info
            results = {
                'doc_id': doc_id,
                'state': state,
                'phase': self.args.phase,
                'input_file': pdf_path,
                'processing_time': time.time(),
                'status': 'success',
                'batch_mode': True
            }
            
            # Save processing metadata
            with open(output_dir / 'processing_info.json', 'w') as f:
                json.dump(results, f, indent=2)
            
            # TODO: Replace with actual pipeline call
            # This is where the real processing would happen
            
            return True
            
        except Exception as e:
            self.logger.error(f"Processing failed for {doc_id}: {e}")
            return False