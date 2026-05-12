"""
Configuration management for POP CLI
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


DEFAULT_CONFIG = {
    'paths': {
        'raw_pdfs': 'data/raw/POP Bank',
        'inventory_csv': 'pdf_inventory.csv',
        'output_base': 'artifacts',
        'phase1_output': 'artifacts/phase1_english',
        'phase2_output': 'artifacts/phase2_indic',
        'logs': 'logs',
        'temp': 'temp'
    },
    'processing': {
        'default_batch_size': 10,
        'max_parallel_processes': 4,
        'timeout_per_pdf': 300,  # seconds
        'retry_attempts': 2
    },
    'classification': {
        'fasttext_model': 'lid.176.bin',
        'english_confidence_threshold': 0.5,
        'indic_confidence_threshold': 0.3,
        'require_digital': True,
        'exclude_garbled': True
    },
    'phase1': {
        'name': 'English Processing',
        'criteria': {
            'lang_guess': 'en',
            'lang_conf_min': 0.5,
            'digital_guess': True,
            'garbled_detected': False
        },
        'processing': {
            'enable_translation': False,
            'ocr_validation': True
        }
    },
    'phase2': {
        'name': 'Indic Processing', 
        'criteria': {
            'lang_guess': 'indic',
            'lang_conf_min': 0.3,
            'digital_guess': True,
            'garbled_detected': False
        },
        'processing': {
            'enable_translation': True,
            'ocr_validation': True,
            'target_language': 'en'
        }
    },
    'output': {
        'formats': ['json', 'markdown'],
        'include_images': True,
        'image_processing': True,
        'validation': True
    }
}


class Config:
    """Configuration manager for POP CLI."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self._data = config_data
        self._ensure_paths()
    
    def _ensure_paths(self):
        """Ensure all configured paths exist."""
        for path_key, path_value in self._data.get('paths', {}).items():
            # Skip input path and file paths (not directories)
            if path_key in ['raw_pdfs', 'inventory_csv']:
                continue
            # Only create directories, not files
            path_obj = Path(path_value)
            if not path_value.endswith(('.csv', '.json', '.yaml', '.yml', '.txt', '.log')):
                path_obj.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        keys = key.split('.')
        value = self._data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation."""
        keys = key.split('.')
        data = self._data
        
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        
        data[keys[-1]] = value
    
    def get_phase_criteria(self, phase: int) -> Dict[str, Any]:
        """Get selection criteria for a specific phase."""
        phase_key = f'phase{phase}'
        return self.get(f'{phase_key}.criteria', {})
    
    def get_phase_config(self, phase: int) -> Dict[str, Any]:
        """Get complete configuration for a specific phase."""
        phase_key = f'phase{phase}'
        return self.get(phase_key, {})
    
    def save(self, filepath: Optional[str] = None) -> None:
        """Save configuration to file."""
        if not filepath:
            filepath = 'config/pop_cli.yaml'
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            yaml.dump(self._data, f, default_flow_style=False, indent=2)
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get the raw configuration data."""
        return self._data


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from file or use defaults."""
    config_data = DEFAULT_CONFIG.copy()
    
    # Look for config files in order of preference
    config_files = []
    if config_path:
        config_files.append(config_path)
    
    config_files.extend([
        'pop_cli.yaml',
        'config/pop_cli.yaml', 
        'config/pipeline.yaml',
        os.path.expanduser('~/.pop_cli.yaml')
    ])
    
    # Load first available config file
    for config_file in config_files:
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    user_config = yaml.safe_load(f) or {}
                
                # Merge with defaults (deep merge)
                config_data = _deep_merge(config_data, user_config)
                break
            except Exception as e:
                print(f"Warning: Could not load config from {config_file}: {e}")
                continue
    
    return Config(config_data)


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def create_default_config_file(output_path: str = 'config/pop_cli.yaml') -> None:
    """Create a default configuration file."""
    config = Config(DEFAULT_CONFIG)
    config.save(output_path)
    print(f"Created default configuration at: {output_path}")