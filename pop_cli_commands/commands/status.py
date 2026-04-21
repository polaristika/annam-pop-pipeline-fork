"""
Status command for showing processing status and statistics
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Any, List
import sys
import json
import os
from datetime import datetime

code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

from pop_cli_commands.core.base import BaseCommand


class StatusCommand(BaseCommand):
    """Command for showing processing status and statistics."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--summary', action='store_true',
                           help='Show overall processing summary')
        parser.add_argument('--phase', type=int, choices=[1, 2],
                           help='Show status for specific phase')
        parser.add_argument('--detailed', action='store_true',
                           help='Show detailed statistics')
        parser.add_argument('--recent', type=int, default=10,
                           help='Show N most recent processing activities')
        parser.add_argument('--failed', action='store_true',
                           help='Show only failed processing attempts')
        parser.add_argument('--progress', action='store_true',
                           help='Show progress towards processing goals')
    
    def execute(self) -> bool:
        """Execute status command."""
        try:
            # Load inventory if available
            inventory_path = Path(self.config.get('paths.inventory_csv', 'pdf_inventory.csv'))
            
            # If it's a directory, look for the file inside
            if inventory_path.is_dir():
                inventory_path = inventory_path / 'pdf_inventory.csv'
            
            if not inventory_path.exists() or not inventory_path.is_file():
                print("⚠️  Inventory not found. Run 'pop-cli inventory scan' first.")
                inventory_df = None
            else:
                try:
                    inventory_df = pd.read_csv(inventory_path)
                except Exception as e:
                    print(f"⚠️  Could not read inventory file: {e}")
                    inventory_df = None
            
            if self.args.summary or (not any([self.args.phase, self.args.detailed, self.args.recent, self.args.failed, self.args.progress])):
                return self._show_summary(inventory_df)
            
            if self.args.phase:
                return self._show_phase_status(inventory_df, self.args.phase)
            
            if self.args.detailed:
                return self._show_detailed_status(inventory_df)
            
            if self.args.failed:
                return self._show_failed_processing()
            
            if self.args.progress:
                return self._show_progress(inventory_df)
            
            if self.args.recent:
                return self._show_recent_activity()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Status command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _show_summary(self, inventory_df: pd.DataFrame) -> bool:
        """Show overall processing summary."""
        print("📊 PROCESSING STATUS SUMMARY")
        print("=" * 50)
        
        if inventory_df is None:
            print("❌ No inventory data available")
            return False
        
        total_pdfs = len(inventory_df)
        
        # Classification summary
        print(f"📁 Total PDFs scanned: {total_pdfs}")
        print()
        
        # Phase eligibility
        phase1_criteria = self.config.get_phase_criteria(1)
        phase2_criteria = self.config.get_phase_criteria(2)
        
        phase1_eligible = self._filter_by_criteria(inventory_df, phase1_criteria)
        phase2_eligible = self._filter_by_criteria(inventory_df, phase2_criteria)
        
        print("🎯 Processing Eligibility:")
        print(f"  Phase 1 (English): {len(phase1_eligible):>4} eligible")
        print(f"  Phase 2 (Indic):   {len(phase2_eligible):>4} eligible")
        print(f"  Total Eligible:    {len(phase1_eligible) + len(phase2_eligible):>4} files")
        print(f"  Eligibility Rate:  {((len(phase1_eligible) + len(phase2_eligible)) / total_pdfs * 100):>5.1f}%")
        print()
        
        # Processing status
        phase1_processed = self._count_processed_files(1)
        phase2_processed = self._count_processed_files(2)
        
        print("✅ Processing Status:")
        print(f"  Phase 1 Processed: {phase1_processed:>4} / {len(phase1_eligible):>4} ({(phase1_processed/max(1,len(phase1_eligible))*100):>5.1f}%)")
        print(f"  Phase 2 Processed: {phase2_processed:>4} / {len(phase2_eligible):>4} ({(phase2_processed/max(1,len(phase2_eligible))*100):>5.1f}%)")
        print(f"  Total Processed:   {phase1_processed + phase2_processed:>4} / {len(phase1_eligible) + len(phase2_eligible):>4}")
        print()
        
        # System status
        self._show_system_status()
        
        return True
    
    def _show_phase_status(self, inventory_df: pd.DataFrame, phase: int) -> bool:
        """Show detailed status for a specific phase."""
        phase_name = "English" if phase == 1 else "Indic"
        print(f"📋 PHASE {phase} ({phase_name.upper()}) STATUS")
        print("=" * 50)
        
        if inventory_df is None:
            print("❌ No inventory data available")
            return False
        
        # Get eligible files
        phase_criteria = self.config.get_phase_criteria(phase)
        eligible_files = self._filter_by_criteria(inventory_df, phase_criteria)
        
        print(f"🎯 Eligible Files: {len(eligible_files)}")
        
        # Processing status
        processed_count = self._count_processed_files(phase)
        print(f"✅ Processed: {processed_count}")
        print(f"⏳ Remaining: {len(eligible_files) - processed_count}")
        print(f"📊 Progress: {(processed_count/max(1,len(eligible_files))*100):0.1f}%")
        print()
        
        # Confidence distribution
        if len(eligible_files) > 0:
            print("🎯 Confidence Distribution:")
            ranges = [
                (0.9, 1.0, "Very High"),
                (0.7, 0.9, "High"),
                (0.5, 0.7, "Medium"),
                (0.3, 0.5, "Low")
            ]
            
            for min_conf, max_conf, label in ranges:
                count = len(eligible_files[
                    (eligible_files['lang_conf'] >= min_conf) & 
                    (eligible_files['lang_conf'] < max_conf)
                ])
                if count > 0:
                    pct = (count / len(eligible_files)) * 100
                    print(f"  {label:<10} {count:>4} ({pct:>5.1f}%)")
            print()
        
        # State distribution (top 10)
        if 'state' in eligible_files.columns and len(eligible_files) > 0:
            print("📍 Top States:")
            state_counts = eligible_files['state'].value_counts().head(10)
            for state, count in state_counts.items():
                processed_in_state = self._count_processed_in_state(phase, state)
                print(f"  {state:<20} {processed_in_state:>3}/{count:<3} ({(processed_in_state/count*100):>5.1f}%)")
            print()
        
        return True
    
    def _show_detailed_status(self, inventory_df: pd.DataFrame) -> bool:
        """Show detailed processing statistics."""
        print("📊 DETAILED PROCESSING STATISTICS")
        print("=" * 60)
        
        if inventory_df is None:
            print("❌ No inventory data available")
            return False
        
        # File type analysis
        print("📄 File Analysis:")
        if 'class' in inventory_df.columns:
            class_counts = inventory_df['class'].value_counts()
            total = len(inventory_df)
            for cls, count in class_counts.items():
                pct = (count / total) * 100
                print(f"  {cls:<20} {count:>5} ({pct:>5.1f}%)")
        print()
        
        # Language detection analysis
        print("🌐 Language Detection:")
        if 'lang_guess' in inventory_df.columns:
            lang_counts = inventory_df['lang_guess'].value_counts()
            for lang, count in lang_counts.items():
                pct = (count / len(inventory_df)) * 100
                print(f"  {lang:<20} {count:>5} ({pct:>5.1f}%)")
        print()
        
        # Quality indicators
        print("🔍 Quality Indicators:")
        if 'garbled_detected' in inventory_df.columns:
            garbled_count = (inventory_df['garbled_detected'] == True).sum()
            print(f"  Garbled files:       {garbled_count:>5} ({(garbled_count/len(inventory_df)*100):>5.1f}%)")
        
        if 'digital_guess' in inventory_df.columns:
            digital_count = (inventory_df['digital_guess'] == True).sum()
            print(f"  Digital files:       {digital_count:>5} ({(digital_count/len(inventory_df)*100):>5.1f}%)")
        
        # Size distribution
        if 'size_bytes' in inventory_df.columns:
            sizes = inventory_df['size_bytes'].dropna()
            if len(sizes) > 0:
                print(f"  Average file size:   {sizes.mean()/1024/1024:>5.1f} MB")
                print(f"  Largest file:        {sizes.max()/1024/1024:>5.1f} MB")
                print(f"  Smallest file:       {sizes.min()/1024/1024:>5.1f} MB")
        print()
        
        return True
    
    def _show_recent_activity(self) -> bool:
        """Show recent processing activity."""
        print(f"⏰ RECENT PROCESSING ACTIVITY (Last {self.args.recent})")
        print("=" * 60)
        
        recent_files = []
        
        # Check both phase output directories
        for phase in [1, 2]:
            output_base = Path(self.config.get(f'paths.phase{phase}_output'))
            raw_dir = output_base
            
            if raw_dir.exists():
                for doc_dir in raw_dir.iterdir():
                    if doc_dir.is_dir():
                        # Check for processing info
                        info_file = doc_dir / 'processing_info.json'
                        if info_file.exists():
                            try:
                                with open(info_file, 'r') as f:
                                    info = json.load(f)
                                info['doc_dir'] = doc_dir
                                info['phase'] = phase
                                recent_files.append(info)
                            except Exception:
                                pass
                        else:
                            # Use directory modification time as fallback
                            recent_files.append({
                                'doc_id': doc_dir.name,
                                'phase': phase,
                                'processing_time': doc_dir.stat().st_mtime,
                                'status': 'unknown',
                                'doc_dir': doc_dir
                            })
        
        # Sort by processing time (most recent first)
        recent_files.sort(key=lambda x: x.get('processing_time', 0), reverse=True)
        
        if not recent_files:
            print("❌ No recent processing activity found")
            return True
        
        # Display recent activity
        shown = 0
        for item in recent_files[:self.args.recent]:
            doc_id = item.get('doc_id', 'unknown')
            phase = item.get('phase', '?')
            status = item.get('status', 'unknown')
            timestamp = item.get('processing_time', 0)
            
            if timestamp:
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = 'unknown'
            
            phase_name = 'English' if phase == 1 else 'Indic' if phase == 2 else '?'
            status_icon = '✅' if status == 'success' else '❌' if status == 'failed' else '❓'
            
            print(f"  {status_icon} {doc_id:<30} Phase {phase} ({phase_name:<7}) {time_str}")
            shown += 1
        
        print(f"\nShowing {shown} of {len(recent_files)} recent activities")
        return True
    
    def _show_failed_processing(self) -> bool:
        """Show failed processing attempts."""
        print("❌ FAILED PROCESSING ATTEMPTS")
        print("=" * 50)
        
        failed_files = []
        
        # Check both phase output directories for failed attempts
        for phase in [1, 2]:
            output_base = Path(self.config.get(f'paths.phase{phase}_output'))
            raw_dir = output_base
            
            if raw_dir.exists():
                for doc_dir in raw_dir.iterdir():
                    if doc_dir.is_dir():
                        info_file = doc_dir / 'processing_info.json'
                        if info_file.exists():
                            try:
                                with open(info_file, 'r') as f:
                                    info = json.load(f)
                                if info.get('status') == 'failed':
                                    info['phase'] = phase
                                    failed_files.append(info)
                            except Exception:
                                pass
        
        if not failed_files:
            print("✅ No failed processing attempts found")
            return True
        
        print(f"Found {len(failed_files)} failed processing attempts:")
        print()
        
        for item in failed_files:
            doc_id = item.get('doc_id', 'unknown')
            phase = item.get('phase', '?')
            error = item.get('error', 'Unknown error')
            timestamp = item.get('processing_time', 0)
            
            if timestamp:
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = 'unknown'
            
            phase_name = 'English' if phase == 1 else 'Indic'
            print(f"❌ {doc_id}")
            print(f"   Phase: {phase} ({phase_name})")
            print(f"   Time: {time_str}")
            print(f"   Error: {error}")
            print()
        
        return True
    
    def _show_progress(self, inventory_df: pd.DataFrame) -> bool:
        """Show progress towards processing goals."""
        print("📈 PROCESSING PROGRESS")
        print("=" * 40)
        
        if inventory_df is None:
            print("❌ No inventory data available")
            return False
        
        # Calculate progress for each phase
        for phase in [1, 2]:
            phase_name = "English" if phase == 1 else "Indic"
            phase_criteria = self.config.get_phase_criteria(phase)
            eligible_files = self._filter_by_criteria(inventory_df, phase_criteria)
            processed_count = self._count_processed_files(phase)
            
            if len(eligible_files) > 0:
                progress_pct = (processed_count / len(eligible_files)) * 100
                remaining = len(eligible_files) - processed_count
                
                print(f"Phase {phase} ({phase_name}):")
                print(f"  Progress: {'█' * int(progress_pct // 5)}{'░' * (20 - int(progress_pct // 5))} {progress_pct:5.1f}%")
                print(f"  Completed: {processed_count:>4} / {len(eligible_files):<4}")
                print(f"  Remaining: {remaining:>4}")
                print()
        
        return True
    
    def _show_system_status(self):
        """Show system resource status."""
        print("💻 System Status:")
        
        # Check disk space
        for phase in [1, 2]:
            output_path = Path(self.config.get(f'paths.phase{phase}_output'))
            if output_path.exists():
                try:
                    stat = os.statvfs(output_path)
                    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                    print(f"  Phase {phase} disk space: {free_gb:.1f} GB free")
                except:
                    pass
        
        # Check log directory
        log_dir = Path(self.config.get('paths.logs', 'logs'))
        if log_dir.exists():
            log_files = list(log_dir.glob('*.log'))
            total_log_size = sum(f.stat().st_size for f in log_files) / (1024**2)
            print(f"  Log files: {len(log_files)} files, {total_log_size:.1f} MB")
        
        print()
    
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
    
    def _count_processed_files(self, phase: int) -> int:
        """Count processed files for a phase."""
        output_base = Path(self.config.get(f'paths.phase{phase}_output'))
        raw_dir = output_base
        
        if not raw_dir.exists():
            return 0
        
        return len([d for d in raw_dir.iterdir() if d.is_dir()])
    
    def _count_processed_in_state(self, phase: int, state: str) -> int:
        """Count processed files for a specific state."""
        # This would require additional metadata tracking
        # For now, return 0 as placeholder
        return 0