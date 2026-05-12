# Configuration Files

- `pipeline.yaml` - Pipeline processing settings
- `paths.yaml` - All project paths (update here when restructuring)
- `models.yaml` - Model configurations
- `env.example` - Environment variables template

## Usage

Import paths in Python:
```python
import yaml
from pathlib import Path

with open('config/paths.yaml') as f:
    paths = yaml.safe_load(f)
    
data_dir = Path(paths['data']['raw'])
```
