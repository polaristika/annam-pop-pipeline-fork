#!/usr/bin/env python3
"""
Fix translated JSON files - remove extra pipe characters from table_raw content
"""

import json
from pathlib import Path

def clean_table_content(content):
    """Remove excessive pipes from table content"""
    if not content:
        return content
    
    # Check if it's a separator line (only |, -, and whitespace)
    if content.strip().replace('|', '').replace('-', '').replace(' ', '').strip() == '':
        return content  # Keep separators as-is
    
    cleaned = content
    
    # Remove excessive pipes at the start (pattern: "| | | | |")
    count = 0
    while cleaned.startswith('| | | | | | | | | | | | | | | | |'):
        cleaned = cleaned[len('| | | | | | | | | | | | | | | | |'):]
        count += 1
        if count > 5:  # Safety limit
            break
    
    # Try shorter pattern if that didn't work
    count = 0
    while cleaned.startswith('| | | | |'):
        cleaned = cleaned[len('| | | | |'):]
        count += 1
        if count > 5:
            break
    
    # Remove excessive pipes at the end
    count = 0
    while cleaned.endswith('| | | | | | | | | | | | | | | | |'):
        cleaned = cleaned[:-len('| | | | | | | | | | | | | | | | |')]
        count += 1
        if count > 5:
            break
    
    count = 0
    while cleaned.endswith('| | | | |'):
        cleaned = cleaned[:-len('| | | | |')]
        count += 1
        if count > 5:
            break
    
    # Remove excessive pipes in the MIDDLE (column separator)
    # Pattern: "text.| | | | | | | | | | | | | | | | | |More text"
    # Replace with: "text | More text"
    if '| | | | | | | | | | | | | | | | | |' in cleaned:
        cleaned = cleaned.replace('| | | | | | | | | | | | | | | | | |', ' | ')
    
    # Also handle shorter patterns in the middle
    # But be careful not to replace legitimate single pipes
    # Only replace if there are 5+ consecutive pipe-space pairs
    import re
    # Match 5 or more consecutive "| " patterns
    cleaned = re.sub(r'(\| ){5,}', '| ', cleaned)
    
    return cleaned.strip()


def fix_translated_json(json_path):
    """Fix a single translated JSON file"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        fixed = False
        for block in data.get('content', []):
            if block.get('type') == 'table_raw':
                original_content = block.get('content', '')
                cleaned_content = clean_table_content(original_content)
                
                if cleaned_content != original_content:
                    block['content'] = cleaned_content
                    fixed = True
        
        if fixed:
            # Save fixed version
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        
        return False
        
    except Exception as e:
        print(f"Error fixing {json_path}: {e}")
        return False


def main():
    """Fix all translated JSON files"""
    base_dir = Path('/home/aic_u1/pop_scraping/artifacts/Extracted_Digital_Indic_POP_Data')
    
    translated_files = list(base_dir.glob('*/doc_translated.json'))
    
    print(f"{'='*80}")
    print(f"FIXING TRANSLATED JSON FILES - TABLE PIPE CLEANUP")
    print(f"{'='*80}")
    print(f"\nFound {len(translated_files)} translated files\n")
    
    fixed_count = 0
    unchanged_count = 0
    error_count = 0
    
    for idx, json_path in enumerate(translated_files, 1):
        doc_id = json_path.parent.name
        print(f"[{idx}/{len(translated_files)}] {doc_id[:60]}...", end=' ')
        
        try:
            if fix_translated_json(json_path):
                print("✓ Fixed")
                fixed_count += 1
            else:
                print("- No changes needed")
                unchanged_count += 1
        except Exception as e:
            print(f"✗ Error: {str(e)[:40]}")
            error_count += 1
    
    print(f"\n{'='*80}")
    print(f"SUMMARY:")
    print(f"  ✓ Fixed:       {fixed_count}/{len(translated_files)} files")
    print(f"  - Unchanged:   {unchanged_count}/{len(translated_files)} files")
    print(f"  ✗ Errors:      {error_count}/{len(translated_files)} files")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()