#!/usr/bin/env python3
"""
Copy translated Indic files to final destination
Only copies {name}.json files, not {name}_original.json files
"""

import shutil
from pathlib import Path

def copy_translated_files():
    """Copy only translated JSON files to final destination"""
    
    # Source directory
    source_dir = Path('/home/aic_u1/pop_scraping/artifacts/Extracted_Digital_Indic_POP_Data_Organized')
    
    # Target directory
    target_dir = Path('/home/aic_u1/pop_scraping/Extracted digital Indic POP data')
    target_dir.mkdir(exist_ok=True)
    
    print("📁 Creating 'Extracted digital Indic POP data' structure")
    print("="*70)
    
    # Process each state folder
    for state_folder in sorted(source_dir.iterdir()):
        if not state_folder.is_dir():
            continue
        
        state_name = state_folder.name
        print(f"\n📂 Processing: {state_name}")
        
        # Create state folder in target
        target_state_folder = target_dir / state_name
        target_state_folder.mkdir(exist_ok=True)
        
        # Find all JSON files (excluding _original.json)
        json_files = [f for f in state_folder.glob('*.json') if '_original' not in f.name]
        
        copied_count = 0
        for json_file in json_files:
            target_file = target_state_folder / json_file.name
            shutil.copy2(json_file, target_file)
            copied_count += 1
            print(f"   ✓ Copied: {json_file.name}")
        
        print(f"   Total: {copied_count} files copied")
    
    print("\n" + "="*70)
    print("✅ COPY COMPLETE!")
    print(f"📂 Destination: {target_dir}")
    
    # Summary
    print("\n📊 SUMMARY:")
    for state_folder in sorted(target_dir.iterdir()):
        if state_folder.is_dir():
            json_count = len(list(state_folder.glob('*.json')))
            print(f"   {state_folder.name}: {json_count} JSON files")

if __name__ == '__main__':
    copy_translated_files()
