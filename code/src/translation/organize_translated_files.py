#!/usr/bin/env python3
"""
Organize translated Indic POP files by state
Similar to Phase 1 structure in "Extracted digital English POP data"
"""

import json
import shutil
from pathlib import Path
from collections import defaultdict

def truncate_filename(name, max_len=200):
    """Truncate filename if too long while keeping extension"""
    if len(name) <= max_len:
        return name
    
    # Split name and extension
    parts = name.rsplit('.', 1)
    if len(parts) == 2:
        base, ext = parts
        # Keep extension and truncate base
        return base[:max_len-len(ext)-1] + '.' + ext
    else:
        return name[:max_len]

def organize_translated_files():
    """Organize translated files into state-wise folders"""
    
    # Source directory
    source_dir = Path('artifacts/Extracted_Digital_Indic_POP_Data')
    
    # Target directory (similar to Phase 1)
    target_base = Path('artifacts/Extracted_Digital_Indic_POP_Data_Organized')
    target_base.mkdir(exist_ok=True)
    
    # Find all translated JSON files
    translated_files = list(source_dir.glob('*/doc_translated.json'))
    
    print(f"Found {len(translated_files)} translated files")
    print("="*70)
    
    # Collect files by state
    state_files = defaultdict(list)
    
    for json_path in translated_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = data.get('metadata', {})
            state = metadata.get('State', 'Unknown')
            name = metadata.get('Name', json_path.parent.name)
            
            state_files[state].append({
                'json_path': json_path,
                'name': name,
                'source_dir': json_path.parent
            })
            
        except Exception as e:
            print(f"⚠️  Error reading {json_path.parent.name}: {e}")
    
    # Create state folders and move files
    print(f"\nFound {len(state_files)} unique states:\n")
    
    for state, files in sorted(state_files.items()):
        print(f"📁 {state}: {len(files)} files")
        
        # Create state folder
        state_folder = target_base / state
        state_folder.mkdir(exist_ok=True)
        
        # Process each file
        for file_info in files:
            source_dir = file_info['source_dir']
            name = file_info['name']
            
            # Files to move
            files_to_move = [
                ('doc_translated.json', f"{name}.json"),
                ('doc_translated.md', f"{name}.md"),
                ('doc.json', f"{name}_original.json"),
                ('doc.md', f"{name}_original.md")
            ]
            
            for source_name, target_name in files_to_move:
                source_file = source_dir / source_name
                # Truncate filename if too long
                target_name_safe = truncate_filename(target_name)
                target_file = state_folder / target_name_safe
                
                if source_file.exists():
                    try:
                        # Copy file (keeping original for safety)
                        shutil.copy2(source_file, target_file)
                        # print(f"  ✓ {source_name} -> {state}/{target_name_safe[:50]}")
                    except Exception as e:
                        print(f"  ⚠️  Error copying {source_name}: {str(e)[:100]}")
    
    print("\n" + "="*70)
    print(f"✅ Organization complete!")
    print(f"📂 Output directory: {target_base}")
    print(f"📊 Total states: {len(state_files)}")
    print(f"📄 Total files processed: {len(translated_files)}")
    
    # Print summary by state
    print("\n📊 SUMMARY BY STATE:")
    print("="*70)
    for state, files in sorted(state_files.items()):
        print(f"  {state:<25} {len(files):>3} files")
    
    return target_base

if __name__ == '__main__':
    organize_translated_files()
