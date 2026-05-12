"""
Inventory command for PDF scanning and classification
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
import sys
import os

# Add code modules to path
code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

try:
    from src.ingest.inventory import main as run_inventory, iter_pdfs
except ImportError:
    # Fallback to direct import
    from ingest.inventory import main as run_inventory, iter_pdfs
from pop_cli_commands.core.base import BaseCommand


class InventoryCommand(BaseCommand):
    """Command for PDF inventory and classification."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--scan', action='store_true',
                           help='Scan and classify all PDFs')
        parser.add_argument('--update', action='store_true', 
                           help='Update existing inventory with new files')
        parser.add_argument('--show', action='store_true',
                           help='Show current inventory summary')
        parser.add_argument('--export', metavar='FORMAT',
                           choices=['csv', 'json', 'excel'],
                           help='Export inventory in specified format')
        parser.add_argument('--filter-phase', type=int, choices=[1, 2],
                           help='Show only files eligible for specific phase')
        parser.add_argument('--min-confidence', type=float, default=0.0,
                           help='Minimum confidence threshold for filtering')
        parser.add_argument('--state', 
                           help='Filter by specific state')
        parser.add_argument('--force', action='store_true',
                           help='Force rescan even if inventory exists')
    
    def execute(self) -> bool:
        """Execute inventory command."""
        try:
            if self.args.scan or self.args.force:
                return self._scan_pdfs()
            elif self.args.update:
                return self._update_inventory()
            elif self.args.show:
                return self._show_inventory()
            elif self.args.export:
                return self._export_inventory()
            else:
                print("No action specified. Use --help for options.")
                return False
                
        except Exception as e:
            self.logger.error(f"Inventory command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _scan_pdfs(self) -> bool:
        """Scan and classify all PDFs."""
        raw_path = self.config.get('paths.raw_pdfs')
        inventory_path = self.config.get('paths.inventory_csv')
        
        if not Path(raw_path).exists():
            print(f"Error: Raw PDFs directory not found: {raw_path}")
            return False
        
        # Count total PDFs first
        pdf_files = list(iter_pdfs(raw_path))
        total_pdfs = len(pdf_files)
        
        print(f"🔍 Scanning {total_pdfs} PDFs for classification...")
        print(f"📁 Source: {raw_path}")
        print(f"📄 Output: {inventory_path}")
        print()
        
        # Run the inventory process
        old_cwd = os.getcwd()
        try:
            # Change to project root for inventory to work correctly
            os.chdir(Path(__file__).parent.parent.parent)
            run_inventory()
            
            print(f"✅ Inventory complete! Results saved to {inventory_path}")
            
            # Show summary
            return self._show_inventory()
            
        except Exception as e:
            print(f"❌ Error during scanning: {e}")
            return False
        finally:
            os.chdir(old_cwd)
    
    def _update_inventory(self) -> bool:
        """Update existing inventory with new files."""
        print("🔄 Updating inventory with new files...")
        # This would implement incremental updates
        return self._scan_pdfs()
    
    def _show_inventory(self) -> bool:
        """Show inventory summary."""
        inventory_path = Path(self.config.get('paths.inventory_csv', 'pdf_inventory.csv'))
        
        # Handle directory case
        if inventory_path.is_dir():
            inventory_path = inventory_path / 'pdf_inventory.csv'
        
        if not inventory_path.exists() or not inventory_path.is_file():
            print(f"❌ Inventory file not found: {inventory_path}")
            print("Run 'pop-cli inventory --scan' first.")
            return False
        
        try:
            df = pd.read_csv(inventory_path)
            return self._display_summary(df)
            
        except Exception as e:
            print(f"❌ Error reading inventory: {e}")
            return False
    
    def _display_summary(self, df: pd.DataFrame) -> bool:
        """Display inventory summary."""
        total = len(df)
        
        print("📊 INVENTORY SUMMARY")
        print("=" * 50)
        print(f"Total PDFs: {total}")
        print()
        
        # Classification summary
        print("🔤 Basic Classification (class field):")
        class_counts = df['class'].value_counts()
        for cls, count in class_counts.items():
            pct = (count / total) * 100
            print(f"  {cls:<15} {count:>4} ({pct:>5.1f}%)")
        print()
        
        # Language detection summary  
        print("🧠 Advanced Classification (lang_guess field):")
        lang_counts = df['lang_guess'].value_counts()
        for lang, count in lang_counts.items():
            pct = (count / total) * 100
            print(f"  {lang:<15} {count:>4} ({pct:>5.1f}%)")
        print()
        
        # Phase eligibility
        phase1_criteria = self.config.get_phase_criteria(1)
        phase2_criteria = self.config.get_phase_criteria(2)
        
        phase1_eligible = self._filter_by_criteria(df, phase1_criteria)
        phase2_eligible = self._filter_by_criteria(df, phase2_criteria)
        
        print("🎯 Processing Eligibility:")
        print(f"  Phase 1 (English): {len(phase1_eligible):>4} files")
        print(f"  Phase 2 (Indic):   {len(phase2_eligible):>4} files")
        print(f"  Total Eligible:    {len(phase1_eligible) + len(phase2_eligible):>4} files")
        print(f"  Success Rate:      {((len(phase1_eligible) + len(phase2_eligible)) / total * 100):>5.1f}%")
        print()
        
        # State distribution
        if 'state' in df.columns:
            print("📍 Top States:")
            state_counts = df['state'].value_counts().head(10)
            for state, count in state_counts.items():
                print(f"  {state:<20} {count:>4}")
            print()
        
        # Apply filters if specified
        if self.args.filter_phase:
            criteria = self.config.get_phase_criteria(self.args.filter_phase)
            filtered_df = self._filter_by_criteria(df, criteria)
            
            if self.args.min_confidence > 0:
                filtered_df = filtered_df[filtered_df['lang_conf'] >= self.args.min_confidence]
            
            if self.args.state:
                filtered_df = filtered_df[filtered_df['state'].str.contains(self.args.state, case=False, na=False)]
            
            print(f"🔍 Filtered Results (Phase {self.args.filter_phase}):")
            print(f"  Matching files: {len(filtered_df)}")
            
            if len(filtered_df) > 0 and not self.args.quiet:
                print("\n📋 Sample files:")
                sample = filtered_df.head(10)[['file_path', 'state', 'lang_guess', 'lang_conf']]
                for _, row in sample.iterrows():
                    filename = Path(row['file_path']).name
                    print(f"  {filename:<30} {row['state']:<15} {row['lang_guess']:<8} {row['lang_conf']:.3f}")
        
        return True
    
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
    
    def _export_inventory(self) -> bool:
        """Export inventory in specified format."""
        inventory_path = self.config.get('paths.inventory_csv')
        
        if not Path(inventory_path).exists():
            print(f"❌ Inventory file not found: {inventory_path}")
            return False
        
        try:
            df = pd.read_csv(inventory_path)
            
            output_base = Path(inventory_path).stem
            
            if self.args.export == 'json':
                output_path = f"{output_base}.json"
                df.to_json(output_path, orient='records', indent=2)
            elif self.args.export == 'excel':
                output_path = f"{output_base}.xlsx"
                df.to_excel(output_path, index=False)
            else:  # csv (redundant but for completeness)
                output_path = f"{output_base}_export.csv"
                df.to_csv(output_path, index=False)
            
            print(f"✅ Exported inventory to: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Export failed: {e}")
            return False