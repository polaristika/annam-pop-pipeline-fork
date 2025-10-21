"""
List command for viewing available PDFs and their status
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
import sys

code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

from pop_cli_commands.core.base import BaseCommand


class ListCommand(BaseCommand):
    """Command for listing PDFs and their processing status."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--phase', type=int, choices=[1, 2],
                           help='Show only files eligible for specific phase')
        parser.add_argument('--processed', action='store_true',
                           help='Show only processed files')
        parser.add_argument('--unprocessed', action='store_true',
                           help='Show only unprocessed files')
        parser.add_argument('--state', type=str,
                           help='Filter by specific state')
        parser.add_argument('--min-confidence', type=float, default=0.0,
                           help='Minimum confidence threshold')
        parser.add_argument('--max-confidence', type=float, default=1.0,
                           help='Maximum confidence threshold')
        parser.add_argument('--limit', type=int, default=50,
                           help='Maximum number of files to display (default: 50)')
        parser.add_argument('--sort', choices=['confidence', 'state', 'filename', 'size'],
                           default='confidence',
                           help='Sort order (default: confidence)')
        parser.add_argument('--reverse', action='store_true',
                           help='Reverse sort order')
        parser.add_argument('--detailed', action='store_true',
                           help='Show detailed information')
        parser.add_argument('--export', metavar='FILE',
                           help='Export filtered list to CSV file')
    
    def execute(self) -> bool:
        """Execute list command."""
        try:
            # Load inventory
            inventory_path = Path(self.config.get('paths.inventory_csv', 'pdf_inventory.csv'))
            
            # If it's a directory, look for the file inside
            if inventory_path.is_dir():
                inventory_path = inventory_path / 'pdf_inventory.csv'
            
            if not inventory_path.exists() or not inventory_path.is_file():
                print("❌ Inventory not found. Run 'pop-cli inventory --scan' first.")
                return False
            
            try:
                df = pd.read_csv(inventory_path)
            except Exception as e:
                print(f"❌ Could not read inventory file: {e}")
                return False
            
            # Apply filters
            filtered_df = self._apply_filters(df)
            
            if len(filtered_df) == 0:
                print("❌ No files match the specified criteria.")
                return False
            
            # Add processing status
            filtered_df = self._add_processing_status(filtered_df)
            
            # Sort results
            filtered_df = self._sort_results(filtered_df)
            
            # Display results
            self._display_results(filtered_df)
            
            # Export if requested
            if self.args.export:
                self._export_results(filtered_df)
            
            return True
            
        except Exception as e:
            self.logger.error(f"List command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all specified filters."""
        filtered = df.copy()
        
        # Phase filter
        if self.args.phase:
            phase_criteria = self.config.get_phase_criteria(self.args.phase)
            filtered = self._filter_by_criteria(filtered, phase_criteria)
        
        # State filter
        if self.args.state:
            filtered = filtered[filtered['state'].str.contains(self.args.state, case=False, na=False)]
        
        # Confidence filters
        if 'lang_conf' in filtered.columns:
            filtered = filtered[
                (filtered['lang_conf'] >= self.args.min_confidence) &
                (filtered['lang_conf'] <= self.args.max_confidence)
            ]
        
        return filtered
    
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
    
    def _add_processing_status(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add processing status information."""
        df = df.copy()
        status_list = []
        
        for _, row in df.iterrows():
            doc_id = Path(row['file_path']).stem
            status = {'processed': False, 'phase': None, 'output_exists': False}
            
            # Check Phase 1 output
            phase1_output = Path(self.config.get('paths.phase1_output')) / 'raw' / doc_id
            if phase1_output.exists():
                status.update({'processed': True, 'phase': 1, 'output_exists': True})
            
            # Check Phase 2 output
            phase2_output = Path(self.config.get('paths.phase2_output')) / 'raw' / doc_id
            if phase2_output.exists():
                status.update({'processed': True, 'phase': 2, 'output_exists': True})
            
            status_list.append(status)
        
        # Add status columns
        df['processed'] = [s['processed'] for s in status_list]
        df['processed_phase'] = [s['phase'] for s in status_list]
        df['output_exists'] = [s['output_exists'] for s in status_list]
        
        # Apply processing status filters
        if self.args.processed:
            df = df[df['processed'] == True]
        elif self.args.unprocessed:
            df = df[df['processed'] == False]
        
        return df
    
    def _sort_results(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort results according to specified criteria."""
        sort_column = self.args.sort
        
        # Map sort names to actual columns
        sort_mapping = {
            'confidence': 'lang_conf',
            'state': 'state', 
            'filename': 'file_path',
            'size': 'size_bytes'
        }
        
        actual_column = sort_mapping.get(sort_column, sort_column)
        
        if actual_column in df.columns:
            df = df.sort_values(actual_column, ascending=not self.args.reverse)
        
        return df
    
    def _display_results(self, df: pd.DataFrame):
        """Display the filtered and sorted results."""
        total_shown = min(len(df), self.args.limit)
        
        print(f"📋 LISTING {total_shown} FILES")
        if len(df) > self.args.limit:
            print(f"   (Showing first {self.args.limit} of {len(df)} matching files)")
        print("=" * 80)
        
        # Header
        if self.args.detailed:
            print(f"{'#':<3} {'FILENAME':<35} {'STATE':<15} {'LANG':<8} {'CONF':<6} {'STATUS':<10}")
            print("-" * 80)
        else:
            print(f"{'#':<3} {'FILENAME':<40} {'STATE':<15} {'LANG':<8} {'CONF':<6}")
            print("-" * 75)
        
        # Display files
        for i, (_, row) in enumerate(df.head(self.args.limit).iterrows(), 1):
            filename = Path(row['file_path']).name
            state = row.get('state', 'Unknown')[:14]
            lang = row.get('lang_guess', 'unknown')[:7]
            conf = row.get('lang_conf', 0.0)
            
            if self.args.detailed:
                # Determine status
                if row.get('processed', False):
                    phase = row.get('processed_phase', '?')
                    status = f"Phase {phase}"
                else:
                    status = "Pending"
                
                print(f"{i:<3} {filename[:34]:<35} {state:<15} {lang:<8} {conf:<6.3f} {status:<10}")
            else:
                print(f"{i:<3} {filename[:39]:<40} {state:<15} {lang:<8} {conf:<6.3f}")
        
        print()
        
        # Summary statistics
        self._display_summary_stats(df)
    
    def _display_summary_stats(self, df: pd.DataFrame):
        """Display summary statistics."""
        print("📊 SUMMARY STATISTICS")
        print("-" * 30)
        
        # Basic counts
        total = len(df)
        processed = len(df[df.get('processed', False) == True]) if 'processed' in df.columns else 0
        unprocessed = total - processed
        
        print(f"Total files:      {total:>6}")
        print(f"Processed:        {processed:>6}")
        print(f"Unprocessed:      {unprocessed:>6}")
        
        # Language distribution
        if 'lang_guess' in df.columns:
            print(f"\nLanguage Distribution:")
            lang_counts = df['lang_guess'].value_counts()
            for lang, count in lang_counts.items():
                pct = (count / total) * 100
                print(f"  {lang:<10} {count:>4} ({pct:>5.1f}%)")
        
        # State distribution (top 5)
        if 'state' in df.columns:
            print(f"\nTop 5 States:")
            state_counts = df['state'].value_counts().head(5)
            for state, count in state_counts.items():
                print(f"  {state[:15]:<15} {count:>4}")
        
        # Confidence ranges
        if 'lang_conf' in df.columns:
            print(f"\nConfidence Ranges:")
            ranges = [
                (0.9, 1.0, "Very High"),
                (0.7, 0.9, "High"),
                (0.5, 0.7, "Medium"),
                (0.0, 0.5, "Low")
            ]
            
            for min_conf, max_conf, label in ranges:
                count = len(df[(df['lang_conf'] >= min_conf) & (df['lang_conf'] < max_conf)])
                if count > 0:
                    pct = (count / total) * 100
                    print(f"  {label:<10} {count:>4} ({pct:>5.1f}%)")
        
        print()
    
    def _export_results(self, df: pd.DataFrame):
        """Export results to CSV file."""
        try:
            output_path = Path(self.args.export)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Select relevant columns for export
            export_columns = [
                'file_path', 'state', 'lang_guess', 'lang_conf', 'class',
                'digital_guess', 'garbled_detected', 'page_count', 'size_bytes'
            ]
            
            # Add processing status columns if they exist
            if 'processed' in df.columns:
                export_columns.extend(['processed', 'processed_phase', 'output_exists'])
            
            # Filter to existing columns
            existing_columns = [col for col in export_columns if col in df.columns]
            export_df = df[existing_columns]
            
            export_df.to_csv(output_path, index=False)
            print(f"✅ Exported {len(export_df)} files to: {output_path}")
            
        except Exception as e:
            print(f"❌ Export failed: {e}")
            self.logger.error(f"Export failed: {e}")