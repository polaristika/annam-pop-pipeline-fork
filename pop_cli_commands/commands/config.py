"""
Config command for managing configuration
"""

import yaml
from pathlib import Path
from typing import Dict, Any
import sys

code_src_path = Path(__file__).parent.parent.parent / "code" / "src"
sys.path.insert(0, str(code_src_path))
sys.path.insert(0, str(code_src_path.parent))

from pop_cli_commands.core.base import BaseCommand
from pop_cli_commands.core.config import create_default_config_file


class ConfigCommand(BaseCommand):
    """Command for managing configuration."""
    
    @staticmethod
    def add_arguments(parser):
        """Add command-specific arguments."""
        parser.add_argument('--show', action='store_true',
                           help='Show current configuration')
        parser.add_argument('--create-default', action='store_true',
                           help='Create default configuration file')
        parser.add_argument('--set', nargs=2, metavar=('KEY', 'VALUE'),
                           help='Set configuration value (use dot notation)')
        parser.add_argument('--get', metavar='KEY',
                           help='Get configuration value (use dot notation)')
        parser.add_argument('--edit', action='store_true',
                           help='Open configuration file in editor')
        parser.add_argument('--validate', action='store_true',
                           help='Validate configuration file')
        parser.add_argument('--output', metavar='FILE',
                           help='Output file for --create-default')
    
    def execute(self) -> bool:
        """Execute config command."""
        try:
            if self.args.create_default:
                return self._create_default_config()
            elif self.args.show:
                return self._show_config()
            elif self.args.set:
                return self._set_config_value()
            elif self.args.get:
                return self._get_config_value()
            elif self.args.edit:
                return self._edit_config()
            elif self.args.validate:
                return self._validate_config()
            else:
                print("No action specified. Use --help for options.")
                return False
                
        except Exception as e:
            self.logger.error(f"Config command failed: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _create_default_config(self) -> bool:
        """Create default configuration file."""
        output_path = self.args.output or 'config/pop_cli.yaml'
        
        try:
            create_default_config_file(output_path)
            print(f"✅ Created default configuration at: {output_path}")
            print()
            print("Next steps:")
            print(f"1. Review and customize: {output_path}")
            print("2. Test configuration: pop-cli config --validate")
            print("3. View configuration: pop-cli config --show")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create configuration: {e}")
            return False
    
    def _show_config(self) -> bool:
        """Show current configuration."""
        print("⚙️  CURRENT CONFIGURATION")
        print("=" * 50)
        
        config_data = self.config.data
        self._print_config_section(config_data, "")
        
        print()
        print("📍 Configuration Sources:")
        print("  - Default values (built-in)")
        print("  - Config files (if found):")
        
        # Show potential config file locations
        config_files = [
            'pop_cli.yaml',
            'config/pop_cli.yaml', 
            'config/pipeline.yaml'
        ]
        
        for config_file in config_files:
            if Path(config_file).exists():
                print(f"    ✅ {config_file}")
            else:
                print(f"    ❌ {config_file}")
        
        return True
    
    def _print_config_section(self, data: Dict[str, Any], prefix: str, indent: int = 0):
        """Recursively print configuration sections."""
        indent_str = "  " * indent
        
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                print(f"{indent_str}{key}:")
                self._print_config_section(value, full_key, indent + 1)
            else:
                # Format value display
                if isinstance(value, str) and len(value) > 50:
                    value = f"{value[:47]}..."
                print(f"{indent_str}{key}: {value}")
    
    def _set_config_value(self) -> bool:
        """Set a configuration value."""
        key, value = self.args.set
        
        # Try to parse value as appropriate type
        parsed_value = self._parse_config_value(value)
        
        try:
            self.config.set(key, parsed_value)
            print(f"✅ Set {key} = {parsed_value}")
            
            # Save configuration
            config_file = 'config/pop_cli.yaml'
            self.config.save(config_file)
            print(f"💾 Saved to: {config_file}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to set configuration: {e}")
            return False
    
    def _get_config_value(self) -> bool:
        """Get a configuration value."""
        key = self.args.get
        
        try:
            value = self.config.get(key)
            
            if value is None:
                print(f"❌ Configuration key not found: {key}")
                return False
            
            print(f"{key}: {value}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to get configuration: {e}")
            return False
    
    def _edit_config(self) -> bool:
        """Open configuration file in editor."""
        import os
        
        config_file = 'config/pop_cli.yaml'
        
        # Create config file if it doesn't exist
        if not Path(config_file).exists():
            print(f"Configuration file doesn't exist. Creating: {config_file}")
            create_default_config_file(config_file)
        
        # Try to open in editor
        editors = ['code', 'nano', 'vim', 'vi']
        
        for editor in editors:
            try:
                os.system(f"{editor} {config_file}")
                print(f"✅ Opened {config_file} in {editor}")
                return True
            except:
                continue
        
        print(f"❌ Could not find suitable editor. Please edit manually: {config_file}")
        return False
    
    def _validate_config(self) -> bool:
        """Validate configuration file."""
        print("🔍 CONFIGURATION VALIDATION")
        print("=" * 40)
        
        validation_passed = True
        
        # Check required paths
        required_paths = [
            'paths.raw_pdfs',
            'paths.output_base', 
            'paths.logs'
        ]
        
        print("📁 Path Validation:")
        for path_key in required_paths:
            path_value = self.config.get(path_key)
            if path_value:
                path_obj = Path(path_value)
                if path_key == 'paths.raw_pdfs':
                    # Input path should exist
                    if path_obj.exists():
                        print(f"  ✅ {path_key}: {path_value}")
                    else:
                        print(f"  ❌ {path_key}: {path_value} (not found)")
                        validation_passed = False
                else:
                    # Output paths will be created
                    print(f"  ✅ {path_key}: {path_value}")
            else:
                print(f"  ❌ {path_key}: not configured")
                validation_passed = False
        
        print()
        
        # Check phase configuration
        print("🎯 Phase Configuration:")
        for phase in [1, 2]:
            phase_config = self.config.get_phase_config(phase)
            if phase_config:
                criteria = phase_config.get('criteria', {})
                required_criteria = ['lang_guess', 'lang_conf_min', 'digital_guess', 'garbled_detected']
                
                missing_criteria = [c for c in required_criteria if c not in criteria]
                if missing_criteria:
                    print(f"  ❌ Phase {phase}: missing criteria: {missing_criteria}")
                    validation_passed = False
                else:
                    print(f"  ✅ Phase {phase}: criteria complete")
            else:
                print(f"  ❌ Phase {phase}: not configured")
                validation_passed = False
        
        print()
        
        # Check processing configuration
        print("⚙️  Processing Configuration:")
        processing_config = self.config.get('processing', {})
        required_settings = ['default_batch_size', 'max_parallel_processes', 'timeout_per_pdf']
        
        for setting in required_settings:
            if setting in processing_config:
                value = processing_config[setting]
                if isinstance(value, (int, float)) and value > 0:
                    print(f"  ✅ {setting}: {value}")
                else:
                    print(f"  ❌ {setting}: invalid value ({value})")
                    validation_passed = False
            else:
                print(f"  ❌ {setting}: not configured")
                validation_passed = False
        
        print()
        
        # Overall result
        if validation_passed:
            print("✅ Configuration validation passed")
        else:
            print("❌ Configuration validation failed")
            print("   Run 'pop-cli config --create-default' to create a valid configuration")
        
        return validation_passed
    
    def _parse_config_value(self, value: str) -> Any:
        """Parse string value to appropriate type."""
        # Try boolean
        if value.lower() in ['true', 'false']:
            return value.lower() == 'true'
        
        # Try integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value