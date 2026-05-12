#!/usr/bin/env python3
"""
Phase 2 Artifacts Translation Pipeline (Using Google Translate)

Simpler and more reliable translation using googletrans library.
Translates doc.md and doc.json files from Indic languages to English.
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from googletrans import Translator
from tqdm import tqdm
import time


def detect_language(text, max_chars=1000):
    """Detect language of text using googletrans"""
    translator = Translator()
    try:
        sample = text[:max_chars]
        detection = translator.detect(sample)
        return detection.lang
    except Exception as e:
        print(f"    Language detection error: {e}")
        return 'mr'  # Default to Marathi


def clean_table_pipes(text):
    """Remove excessive pipe characters added by translation"""
    if not text or '|' not in text:
        return text
    
    cleaned = text
    
    # Remove excessive pipes at the start
    count = 0
    while cleaned.startswith('| | | | | | | | | | | | | | | | |'):
        cleaned = cleaned[len('| | | | | | | | | | | | | | | | |'):]
        count += 1
        if count > 3:
            break
    
    count = 0
    while cleaned.startswith('| | | | |'):
        cleaned = cleaned[len('| | | | |'):]
        count += 1
        if count > 3:
            break
    
    # Remove excessive pipes at the end
    count = 0
    while cleaned.endswith('| | | | | | | | | | | | | | | | |'):
        cleaned = cleaned[:-len('| | | | | | | | | | | | | | | | |')]
        count += 1
        if count > 3:
            break
    
    count = 0
    while cleaned.endswith('| | | | |'):
        cleaned = cleaned[:-len('| | | | |')]
        count += 1
        if count > 3:
            break
    
    # Remove excessive pipes in the MIDDLE (column separator)
    # Pattern: "text.| | | | | | | | | | | | | | | | | |More text"
    # Replace with: "text | More text"
    if '| | | | | | | | | | | | | | | | | |' in cleaned:
        cleaned = cleaned.replace('| | | | | | | | | | | | | | | | | |', ' | ')
    
    # Also handle shorter patterns in the middle using regex
    # Match 5 or more consecutive "| " patterns and replace with single " | "
    import re
    cleaned = re.sub(r'(\| ){5,}', '| ', cleaned)
    
    return cleaned.strip()


def translate_batch(texts, source_lang='mr', dest_lang='en', batch_size=50):
    """
    Translate texts using Google Translate with rate limiting.
    
    Args:
        texts: List of strings to translate
        source_lang: Source language code ('mr', 'ta', 'te', etc.)
        dest_lang: Destination language code ('en')
        batch_size: Process in smaller batches to avoid rate limiting
        
    Returns:
        List of translated strings
    """
    translator = Translator()
    translations = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        
        for text in batch:
            try:
                # Translate with retry
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        result = translator.translate(
                            text,
                            src=source_lang,
                            dest=dest_lang
                        )
                        translations.append(result.text)
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            time.sleep(1)  # Wait before retry
                        else:
                            print(f"      Translation failed after {max_retries} attempts: {str(e)[:50]}")
                            translations.append(text)  # Keep original if translation fails
            except Exception as e:
                print(f"      Translation error: {str(e)[:50]}")
                translations.append(text)
        
        # Rate limiting
        if i + batch_size < len(texts):
            time.sleep(0.5)  # Small delay between batches
    
    return translations


def translate_json_content(json_data, source_lang='mr'):
    """Translate content blocks in JSON structure"""
    translated_data = json_data.copy()
    
    # Collect all text to translate
    text_blocks = []
    text_indices = []
    
    for idx, block in enumerate(json_data.get('content', [])):
        block_type = block.get('type')
        
        if block_type in ['heading', 'text']:
            content = block.get('content', '')
            if content and content.strip():
                text_blocks.append(content)
                text_indices.append(idx)
        elif block_type == 'table_raw':
            # Skip table separators (just dashes and pipes)
            content = block.get('content', '')
            if content and content.strip():
                # Check if it's a separator line (only |, -, and whitespace)
                if content.strip().replace('|', '').replace('-', '').replace(' ', '').strip() == '':
                    continue  # Don't translate separator lines
                # Translate table content
                text_blocks.append(content)
                text_indices.append(idx)
    
    if not text_blocks:
        return translated_data
    
    # Translate all text blocks
    translations = translate_batch(text_blocks, source_lang=source_lang)
    
    # Update content with translations
    for text_idx, content_idx in enumerate(text_indices):
        block = translated_data['content'][content_idx]
        translated_content = translations[text_idx]
        
        # Clean up extra pipes in table content
        if block.get('type') == 'table_raw':
            translated_content = clean_table_pipes(translated_content)
        
        block['content'] = translated_content
    
    return translated_data


def translate_md_content(md_content, source_lang='mr'):
    """Translate markdown content line by line"""
    lines = md_content.split('\n')
    translated_lines = []
    text_buffer = []
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines, images, code blocks
        if not stripped or stripped.startswith('```') or stripped.startswith('<details>') or \
           stripped.startswith('</details>') or stripped.startswith('**Image Description:**') or \
           stripped.startswith('<summary>') or stripped.startswith('</summary>'):
            # Translate buffered text if any
            if text_buffer:
                translations = translate_batch(text_buffer, source_lang=source_lang)
                translated_lines.extend(translations)
                text_buffer = []
            translated_lines.append(line)
        else:
            # Buffer text lines for translation
            text_buffer.append(line)
    
    # Translate remaining buffer
    if text_buffer:
        translations = translate_batch(text_buffer, source_lang=source_lang)
        translated_lines.extend(translations)
    
    return '\n'.join(translated_lines)


def translate_artifact(doc_id, artifact_dir, source_lang='mr'):
    """Translate a single artifact's doc.json and doc.md"""
    try:
        json_path = artifact_dir / 'doc.json'
        md_path = artifact_dir / 'doc.md'
        
        if not json_path.exists() or not md_path.exists():
            return {'doc_id': doc_id, 'status': 'failed', 'error': 'Files not found'}
        
        # Load JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Translate JSON
        json_translated = translate_json_content(json_data, source_lang=source_lang)
        
        # Save translated JSON
        json_out_path = artifact_dir / 'doc_translated.json'
        with open(json_out_path, 'w', encoding='utf-8') as f:
            json.dump(json_translated, f, indent=2, ensure_ascii=False)
        
        # Load markdown
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Translate markdown
        md_translated = translate_md_content(md_content, source_lang=source_lang)
        
        # Save translated markdown
        md_out_path = artifact_dir / 'doc_translated.md'
        with open(md_out_path, 'w', encoding='utf-8') as f:
            f.write(md_translated)
        
        return {
            'doc_id': doc_id,
            'status': 'success',
            'json_size_kb': json_out_path.stat().st_size / 1024,
            'md_size_kb': md_out_path.stat().st_size / 1024,
            'error': None
        }
        
    except Exception as e:
        return {
            'doc_id': doc_id,
            'status': 'failed',
            'error': str(e)
        }


def main():
    """Main translation pipeline"""
    print("="*80)
    print("PHASE 2 ARTIFACTS TRANSLATION PIPELINE (Google Translate)")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load inventory to get state info
    print("\n[LOADING] pdf_inventory.csv...")
    try:
        inventory = pd.read_csv('pdf_inventory.csv')
    except:
        inventory = pd.DataFrame()  # Empty if not found
    
    # Get all Phase 2 artifact directories
    artifacts_base = Path('artifacts/Extracted_Digital_Indic_POP_Data')
    if not artifacts_base.exists():
        print(f"[ERROR] Artifacts directory not found: {artifacts_base}")
        return
    
    artifact_dirs = [d for d in artifacts_base.iterdir() if d.is_dir()]
    print(f"[FOUND] {len(artifact_dirs)} artifact directories to translate")
    
    # Process all artifacts
    results = []
    start_time = datetime.now()
    
    print(f"\n[PROCESSING] Starting translation for {len(artifact_dirs)} documents...")
    print("="*80)
    
    for idx, artifact_dir in enumerate(artifact_dirs, 1):
        doc_id = artifact_dir.name
        
        print(f"\n[{idx}/{len(artifact_dirs)}] {doc_id}")
        
        # Check if already translated
        if (artifact_dir / 'doc_translated.json').exists():
            print(f"  [{doc_id}] Already translated, skipping...")
            results.append({'doc_id': doc_id, 'status': 'skipped', 'error': 'Already translated'})
            continue
        
        # Default to Marathi (most Phase 2 files are Maharashtra)
        state = 'Maharashtra'
        source_lang = 'mr'  # Marathi
        
        # Detect language from doc name if possible
        doc_lower = doc_id.lower()
        if 'tamil' in doc_lower or 'tamilnadu' in doc_lower:
            source_lang = 'ta'
            state = 'Tamil Nadu'
        elif 'telugu' in doc_lower or 'telangana' in doc_lower or 'andhra' in doc_lower:
            source_lang = 'te'
            state = 'Telangana/AP'
        elif 'medical plant' in doc_lower:
            source_lang = 'ta'  # Medical plant details is Tamil
            state = 'Tamil Nadu'
        
        print(f"  [{doc_id}] Source language: {source_lang} (Inferred state: {state})")
        
        # Translate
        print(f"    Translating content...")
        result = translate_artifact(doc_id, artifact_dir, source_lang=source_lang)
        results.append(result)
        
        if result['status'] == 'success':
            print(f"  [{doc_id}] ✓ SUCCESS")
            print(f"    - doc_translated.json: {result['json_size_kb']:.1f} KB")
            print(f"    - doc_translated.md: {result['md_size_kb']:.1f} KB")
        else:
            print(f"  [{doc_id}] ✗ ERROR: {result['error']}")
    
    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n\n" + "="*80)
    print("TRANSLATION COMPLETE")
    print("="*80)
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {duration/60:.1f} minutes ({duration:.0f} seconds)")
    
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    
    print(f"\nSuccessful: {success_count}/{len(results)}")
    print(f"Failed: {failed_count}/{len(results)}")
    print(f"Skipped: {skipped_count}/{len(results)}")
    
    if failed_count > 0:
        print(f"\n[FAILED ARTIFACTS]")
        for r in results:
            if r['status'] == 'failed':
                print(f"  {r['doc_id']}: {r['error']}")
    
    # Save results
    results_df = pd.DataFrame(results)
    results_path = f"phase2_translation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\n[SAVED] Results to {results_path}")
    
    print("\n" + "="*80)
    print("Translation pipeline complete!")
    print("="*80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Translation stopped by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[FATAL ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
