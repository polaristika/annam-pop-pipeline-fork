"""
Cleanup command for resetting and cleaning project state
"""

import shutil
from pathlib import Path
from typing import List, Set
import sys

code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

from pop_cli_commands.core.base import BaseCommand


class CleanupCommand(BaseCommand):
    """Command for cleaning up and resetting project state."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--target', choices=['outputs', 'logs', 'temp', 'cache', 'all'],
                           default='temp', help='What to clean (default: temp)')
        parser.add_argument('--phase', type=int, choices=[1, 2],
                           help='Clean specific phase outputs only')
        parser.add_argument('--state', 
                           help='Clean outputs for specific state only')
        parser.add_argument('--dry-run', action='store_true',
                           help='Show what would be deleted without deleting')
        parser.add_argument('--force', action='store_true',
                           help='Skip confirmation prompts')
        parser.add_argument('--keep-recent', type=int, metavar='N',
                           help='Keep N most recent files/folders')
        parser.add_argument('--older-than', type=int, metavar='DAYS',
                           help='Only clean files older than N days')
        parser.add_argument('--reset-inventory', action='store_true',
                           help='Reset inventory database (WARNING: loses classification data)')
    
    def execute(self) -> bool:
        """Execute cleanup command."""
        try:
            print(f"🧹 CLEANUP: {self.args.target.upper()}")
            print("=" * 50)
            
            if self.args.reset_inventory:
                return self._reset_inventory()
            elif self.args.target == 'all':
                return self._cleanup_all()
            elif self.args.target == 'outputs':
                return self._cleanup_outputs()
            elif self.args.target == 'logs':
                return self._cleanup_logs()
            elif self.args.target == 'temp':
                return self._cleanup_temp()
            elif self.args.target == 'cache':
                return self._cleanup_cache()
            else:
                print(f"Unknown cleanup target: {self.args.target}")
                return False
                
        except Exception as e:
            self.logger.error(f"Cleanup command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _cleanup_all(self) -> bool:
        """Clean up everything."""
        if not self.args.force:
            print("⚠️  WARNING: This will clean ALL project outputs, logs, temp files, and cache!")
            print("This includes:")
            print("  - All processed PDF outputs (Phase 1 & 2)")
            print("  - All log files")
            print("  - All temporary files")
            print("  - All cached data")
            print()
            
            response = input("Are you sure you want to continue? (type 'yes' to confirm): ")
            if response.lower() != 'yes':
                print("❌ Cleanup cancelled")
                return False
        
        success = True
        success &= self._cleanup_outputs()
        success &= self._cleanup_logs()
        success &= self._cleanup_temp()
        success &= self._cleanup_cache()
        
        if success:
            print("✅ Complete cleanup finished successfully")
        else:
            print("⚠️  Some cleanup operations failed")
        
        return success
    
    def _cleanup_outputs(self) -> bool:
        """Clean up processing outputs."""
        output_base = Path(self.config.get('paths.output_base', 'artifacts'))
        
        if not output_base.exists():
            print(f"📂 Output directory doesn't exist: {output_base}")
            return True
        
        cleanup_paths = []
        
        # Phase-specific cleanup
        if self.args.phase:
            phase_dirs = {
                1: ['phase1_english'],
                2: ['phase2_indic']
            }
            
            for dir_name in phase_dirs[self.args.phase]:
                phase_dir = output_base / dir_name
                if phase_dir.exists():
                    if self.args.state:
                        # Clean specific state within phase
                        state_dir = phase_dir / self.args.state
                        if state_dir.exists():
                            cleanup_paths.append(state_dir)
                    else:
                        # Clean entire phase
                        cleanup_paths.append(phase_dir)
        else:
            # Clean all outputs
            for phase_dir in ['phase1_english', 'phase2_indic']:
                phase_path = output_base / phase_dir
                if phase_path.exists():
                    if self.args.state:
                        # Clean specific state from all phases
                        state_dir = phase_path / self.args.state
                        if state_dir.exists():
                            cleanup_paths.append(state_dir)
                    else:
                        cleanup_paths.append(phase_path)
        
        return self._execute_cleanup(cleanup_paths, "Processing Outputs")
    
    def _cleanup_logs(self) -> bool:
        """Clean up log files."""
        logs_dir = Path(self.config.get('paths.logs', 'logs'))
        
        if not logs_dir.exists():
            print(f"📂 Logs directory doesn't exist: {logs_dir}")
            return True
        
        cleanup_paths = []
        
        # Phase-specific log cleanup
        if self.args.phase:
            phase_log_dir = logs_dir / f"phase{self.args.phase}"
            if phase_log_dir.exists():
                cleanup_paths.append(phase_log_dir)
        else:
            # Clean all logs
            for item in logs_dir.iterdir():
                if item.is_dir() or item.suffix in ['.log', '.txt']:
                    cleanup_paths.append(item)
        
        return self._execute_cleanup(cleanup_paths, "Log Files")
    
    def _cleanup_temp(self) -> bool:
        """Clean up temporary files."""
        temp_paths = []
        
        # Common temporary directories and files
        temp_locations = [
            '__pycache__',
            '.pytest_cache',
            'temp',
            'tmp',
            '.temp'
        ]
        
        # Find temp files and directories
        for location in temp_locations:
            path = Path(location)
            if path.exists():
                temp_paths.append(path)
        
        # Find Python cache directories recursively
        for pycache in Path('.').rglob('__pycache__'):
            temp_paths.append(pycache)
        
        # Find .pyc files
        for pyc_file in Path('.').rglob('*.pyc'):
            temp_paths.append(pyc_file)
        
        return self._execute_cleanup(temp_paths, "Temporary Files")
    
    def _cleanup_cache(self) -> bool:
        """Clean up cache files."""
        cache_paths = []
        
        # Model caches
        cache_locations = [
            Path.home() / '.cache' / 'torch',
            Path.home() / '.cache' / 'transformers',
            Path.home() / '.cache' / 'huggingface',
            'models_cache',
            'cache',
            '.cache'
        ]
        
        for cache_path in cache_locations:
            if cache_path.exists():
                # Only clean if user explicitly requested cache cleanup
                if self.args.target == 'cache' or self.args.target == 'all':
                    cache_paths.append(cache_path)
        
        if not cache_paths and (self.args.target == 'cache' or self.args.target == 'all'):
            print("📂 No cache directories found")
            return True
        
        return self._execute_cleanup(cache_paths, "Cache Files")
    
    def _reset_inventory(self) -> bool:
        """Reset inventory database."""
        inventory_files = [
            'data/processed/pdf_inventory.csv',
            'data/processed/classification_results.csv',
            'artifacts/pdf_inventory.csv'
        ]
        
        if not self.args.force:
            print("⚠️  WARNING: This will delete all PDF classification data!")
            print("You will need to run inventory scan again to reclassify PDFs.")
            print()
            
            response = input("Are you sure you want to reset inventory? (type 'yes' to confirm): ")
            if response.lower() != 'yes':
                print("❌ Inventory reset cancelled")
                return False
        
        cleanup_paths = []
        for inv_file in inventory_files:
            path = Path(inv_file)
            if path.exists():
                cleanup_paths.append(path)
        
        success = self._execute_cleanup(cleanup_paths, "Inventory Files")
        
        if success:
            print()
            print("📋 Next steps after inventory reset:")
            print("1. Run: pop-cli inventory scan")
            print("2. Check results: pop-cli inventory show")
            print("3. Process PDFs: pop-cli process --phase 1")
        
        return success
    
    def _execute_cleanup(self, paths: List[Path], category: str) -> bool:
        """Execute cleanup for given paths."""
        if not paths:
            print(f"📂 No {category.lower()} found to clean")
            return True
        
        # Apply filters
        filtered_paths = self._apply_filters(paths)
        
        if not filtered_paths:
            print(f"📂 No {category.lower()} match cleanup criteria")
            return True
        
        # Calculate cleanup statistics
        total_size = 0
        file_count = 0
        
        for path in filtered_paths:
            if path.is_file():
                total_size += path.stat().st_size
                file_count += 1
            elif path.is_dir():
                for file_path in path.rglob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                        file_count += 1
        
        # Show cleanup summary
        print(f"🎯 {category} Cleanup Summary:")
        print(f"   Items to clean: {len(filtered_paths)}")
        print(f"   Files affected: {file_count}")
        print(f"   Space to free: {self._format_size(total_size)}")
        print()
        
        if self.args.dry_run:
            print("🔍 DRY RUN - Would delete:")
            for path in filtered_paths:
                print(f"   📁 {path}")
            return True
        
        # Confirm deletion
        if not self.args.force and len(filtered_paths) > 0:
            response = input(f"Delete {len(filtered_paths)} items? (y/N): ")
            if response.lower() not in ['y', 'yes']:
                print("❌ Cleanup cancelled")
                return False
        
        # Execute deletion
        success = True
        deleted_count = 0
        
        for path in filtered_paths:
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
                
                deleted_count += 1
                if self.args.verbose:
                    print(f"   ✅ Deleted: {path}")
                    
            except Exception as e:
                print(f"   ❌ Failed to delete {path}: {e}")
                success = False
        
        if success:
            print(f"✅ Successfully cleaned {deleted_count} {category.lower()}")
            print(f"   Freed: {self._format_size(total_size)}")
        else:
            print(f"⚠️  Partially cleaned {deleted_count}/{len(filtered_paths)} {category.lower()}")
        
        return success
    
    def _apply_filters(self, paths: List[Path]) -> List[Path]:
        """Apply cleanup filters to paths."""
        filtered_paths = paths[:]
        
        # Filter by age
        if self.args.older_than:
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=self.args.older_than)
            
            age_filtered = []
            for path in filtered_paths:
                try:
                    if path.exists():
                        mod_time = datetime.fromtimestamp(path.stat().st_mtime)
                        if mod_time < cutoff_date:
                            age_filtered.append(path)
                except:
                    # If we can't get modification time, skip
                    pass
            
            filtered_paths = age_filtered
        
        # Keep recent files
        if self.args.keep_recent and self.args.keep_recent > 0:
            # Sort by modification time (newest first)
            try:
                filtered_paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
                # Keep N most recent
                filtered_paths = filtered_paths[self.args.keep_recent:]
            except:
                # If sorting fails, don't apply this filter
                pass
        
        return filtered_paths
    
    def _format_size(self, size_bytes: int) -> str:
        """Format size in human readable format."""
        if size_bytes == 0:
            return "0 B"
        
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size = float(size_bytes)
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"