#!/usr/bin/env python3
"""
Phase 2 Artifacts Translation Pipeline

Translates doc.md and doc.json files from Indic languages to English using IndicTrans2.
Creates translated versions: doc_translated.md and doc_translated.json
"""

import os
import sys
import json
import torch
import pandas as pd
from pathlib import Path
from datetime import datetime
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from tqdm import tqdm


class IndicTrans2Translator:
    """IndicTrans2 translation wrapper"""
    
    def __init__(self, model_name="ai4bharat/indictrans2-indic-en-1B"):
        """Initialize IndicTrans2 model"""
        print(f"[INIT] Loading IndicTrans2 model: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True
        )
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        print(f"[INIT] Model loaded on device: {self.model.device}")
    
    def translate_batch(self, texts, source_lang="mr", batch_size=16, max_new_tokens=256):
        """
        Translate a batch of texts from source language to English.
        
        Args:
            texts: List of strings to translate
            source_lang: Source language code (mr=Marathi, ta=Tamil, te=Telugu, etc.)
            batch_size: Batch size for translation
            max_new_tokens: Maximum new tokens to generate
            
        Returns:
            List of translated strings
        """
        if not texts:
            return []
        
        # Map language codes to IndicTrans2 format (with script)
        lang_map = {
            'mr': 'mar_Deva',  # Marathi
            'hi': 'hin_Deva',  # Hindi
            'ta': 'tam_Taml',  # Tamil
            'te': 'tel_Telu',  # Telugu
            'bn': 'ben_Beng',  # Bengali
            'gu': 'guj_Gujr',  # Gujarati
            'kn': 'kan_Knda',  # Kannada
            'ml': 'mal_Mlym',  # Malayalam
            'or': 'ory_Orya',  # Oriya
            'pa': 'pan_Guru',  # Punjabi
        }
        
        indic_lang = lang_map.get(source_lang, 'mar_Deva')  # Default to Marathi
        target_lang = "eng_Latn"  # English
        
        # Format texts with language tags: "SRC_LANG TGT_LANG text"
        formatted_texts = [f"{indic_lang} {target_lang} {text}" for text in texts]
        
        translations = []
        for i in range(0, len(formatted_texts), batch_size):
            batch = formatted_texts[i:i+batch_size]
            
            # Tokenize
            inputs = self.tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            ).to(self.model.device)
            
            # Translate
            with torch.no_grad():
                generated = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    num_beams=4,
                    early_stopping=True
                )
            
            # Decode
            batch_translations = self.tokenizer.batch_decode(
                generated,
                skip_special_tokens=True
            )
            translations.extend(batch_translations)
        
        return translations


def detect_language_from_state(state):
    """Map state to most likely language"""
    state_lang_map = {
        'Maharashtra': 'mr',  # Marathi
        'Tamilnadu': 'ta',     # Tamil
        'Telangana': 'te',     # Telugu
        'Karnataka': 'kn',     # Kannada
        'Gujarat': 'gu',       # Gujarati
        'West Bengal': 'bn',   # Bengali
        'Punjab': 'pa',        # Punjabi
        'Odisha': 'or',        # Odia
        'Kerala': 'ml',        # Malayalam
    }
    return state_lang_map.get(state, 'mr')  # Default to Marathi


def translate_json_content(json_data, translator, source_lang):
    """
    Translate text content in JSON structure.
    
    Args:
        json_data: dict with 'content' array
        translator: IndicTrans2Translator instance
        source_lang: Source language code
        
    Returns:
        Translated JSON structure
    """
    translated_data = json_data.copy()
    
    # Collect all text blocks to translate
    text_blocks = []
    text_indices = []
    
    for idx, block in enumerate(json_data['content']):
        if block.get('type') in ['heading', 'text', 'table_raw']:
            content = block.get('content', '')
            if content and isinstance(content, str) and len(content.strip()) > 0:
                text_blocks.append(content)
                text_indices.append(idx)
    
    if not text_blocks:
        return translated_data
    
    # Translate in batches
    print(f"    Translating {len(text_blocks)} text blocks...")
    translations = translator.translate_batch(text_blocks, source_lang=source_lang)
    
    # Replace with translations
    for idx, translation in zip(text_indices, translations):
        translated_data['content'][idx]['content'] = translation
        # Add original as metadata
        translated_data['content'][idx]['original_content'] = json_data['content'][idx]['content']
        translated_data['content'][idx]['translated'] = True
    
    # Update metadata
    translated_data['metadata']['translation_info'] = {
        'source_language': source_lang,
        'target_language': 'en',
        'model': 'ai4bharat/indictrans2-indic-en-1B',
        'translated_at': datetime.now().isoformat(),
        'blocks_translated': len(text_blocks)
    }
    
    return translated_data


def translate_markdown_content(md_content, json_data_translated):
    """
    Create translated markdown from translated JSON.
    Keeps image sections unchanged.
    
    Args:
        md_content: Original markdown string
        json_data_translated: Translated JSON structure
        
    Returns:
        Translated markdown string
    """
    # Build translated markdown from JSON
    md_lines = []
    
    md_lines.append("# Translated Document (Indic → English)")
    md_lines.append("")
    md_lines.append(f"**Translation Model:** IndicTrans2 (ai4bharat/indictrans2-indic-en-1B)")
    md_lines.append(f"**Translated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    
    for block in json_data_translated['content']:
        block_type = block.get('type')
        
        if block_type == 'heading':
            level = block.get('level', 1)
            content = block.get('content', '')
            md_lines.append(f"{'#' * level} {content}")
            md_lines.append("")
            
        elif block_type == 'text':
            content = block.get('content', '')
            md_lines.append(content)
            md_lines.append("")
            
        elif block_type == 'table_raw':
            content = block.get('content', '')
            md_lines.append(content)
            md_lines.append("")
            
        elif block_type == 'image':
            # Keep images unchanged with description
            description = block.get('description', '')
            base64_data = block.get('base64', '')
            
            md_lines.append("<!-- image -->")
            md_lines.append("")
            md_lines.append(f"**Image Description:** {description}")
            md_lines.append("")
            
            if base64_data:
                md_lines.append("<details><summary>Base64 Image Data</summary>")
                md_lines.append("")
                md_lines.append("```")
                md_lines.append(base64_data)
                md_lines.append("```")
                md_lines.append("</details>")
                md_lines.append("")
        
        elif block_type == 'separator':
            md_lines.append("---")
            md_lines.append("")
    
    return '\n'.join(md_lines)


def translate_artifact(artifact_dir, translator, inv_row):
    """
    Translate a single artifact directory.
    
    Args:
        artifact_dir: Path to artifact directory
        translator: IndicTrans2Translator instance
        inv_row: Inventory row with language info
        
    Returns:
        dict with translation results
    """
    doc_id = artifact_dir.name
    json_path = artifact_dir / 'doc.json'
    md_path = artifact_dir / 'doc.md'
    
    if not json_path.exists() or not md_path.exists():
        return {'doc_id': doc_id, 'status': 'missing_files', 'error': 'doc.json or doc.md not found'}
    
    try:
        # Detect source language
        state = inv_row['state'] if inv_row is not None else 'Maharashtra'
        source_lang = detect_language_from_state(state)
        
        print(f"  [{doc_id}] Source language: {source_lang} (State: {state})")
        
        # Load JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Load MD
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Translate JSON
        start_time = datetime.now()
        json_translated = translate_json_content(json_data, translator, source_lang)
        translation_time = (datetime.now() - start_time).total_seconds()
        
        # Create translated markdown
        md_translated = translate_markdown_content(md_content, json_translated)
        
        # Save translated files
        json_translated_path = artifact_dir / 'doc_translated.json'
        md_translated_path = artifact_dir / 'doc_translated.md'
        
        with open(json_translated_path, 'w', encoding='utf-8') as f:
            json.dump(json_translated, f, indent=2, ensure_ascii=False)
        
        with open(md_translated_path, 'w', encoding='utf-8') as f:
            f.write(md_translated)
        
        # Calculate sizes
        json_size = json_translated_path.stat().st_size / 1024 / 1024
        md_size = md_translated_path.stat().st_size / 1024 / 1024
        
        blocks_translated = json_translated['metadata']['translation_info']['blocks_translated']
        
        print(f"  [{doc_id}] ✓ Translated {blocks_translated} blocks in {translation_time:.1f}s")
        print(f"  [{doc_id}] ✓ Created doc_translated.json ({json_size:.2f} MB)")
        print(f"  [{doc_id}] ✓ Created doc_translated.md ({md_size:.2f} MB)")
        
        return {
            'doc_id': doc_id,
            'status': 'success',
            'source_lang': source_lang,
            'state': state,
            'blocks_translated': blocks_translated,
            'translation_seconds': translation_time,
            'json_size_mb': json_size,
            'md_size_mb': md_size,
            'error': None
        }
        
    except Exception as e:
        print(f"  [{doc_id}] ✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'doc_id': doc_id,
            'status': 'failed',
            'error': str(e)
        }


def main():
    """Main translation pipeline"""
    print("="*80)
    print("PHASE 2 ARTIFACTS TRANSLATION PIPELINE")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Paths
    artifacts_dir = Path('artifacts/Extracted_Digital_Indic_POP_Data')
    
    if not artifacts_dir.exists():
        print(f"[ERROR] Directory not found: {artifacts_dir}")
        sys.exit(1)
    
    # Load inventory for language info
    print("[LOADING] pdf_inventory.csv...")
    inv = pd.read_csv('pdf_inventory.csv')
    
    # Load Phase 2 worklist
    print("[LOADING] worklist_digital_indic.parquet...")
    worklist = pd.read_parquet('worklist_digital_indic.parquet')
    
    # Get all artifact directories
    artifact_dirs = sorted([d for d in artifacts_dir.iterdir() if d.is_dir()])
    print(f"[FOUND] {len(artifact_dirs)} artifact directories to translate")
    
    # Check for already translated
    already_translated = []
    for dir_path in artifact_dirs:
        if (dir_path / 'doc_translated.json').exists():
            already_translated.append(dir_path.name)
    
    if already_translated:
        print(f"\n[SKIP] {len(already_translated)} already translated")
        artifact_dirs = [d for d in artifact_dirs if d.name not in already_translated]
        print(f"[REMAINING] {len(artifact_dirs)} to translate")
    
    if len(artifact_dirs) == 0:
        print("\n[COMPLETE] All files already translated!")
        return
    
    # Initialize translator
    print("\n[INIT] Initializing IndicTrans2 translator...")
    translator = IndicTrans2Translator()
    
    # Translate all artifacts
    results = []
    start_time = datetime.now()
    
    print(f"\n[PROCESSING] Translating {len(artifact_dirs)} artifacts...")
    print("="*80)
    
    for idx, artifact_dir in enumerate(artifact_dirs, 1):
        print(f"\n[{idx}/{len(artifact_dirs)}] {artifact_dir.name}")
        
        # Get inventory row for language detection
        doc_path = worklist[worklist['doc_id'] == artifact_dir.name]['file_path'].iloc[0] if \
                   len(worklist[worklist['doc_id'] == artifact_dir.name]) > 0 else None
        
        inv_row = None
        if doc_path:
            matching = inv[inv['file_path'] == doc_path]
            if len(matching) > 0:
                inv_row = matching.iloc[0]
        
        # Translate
        result = translate_artifact(artifact_dir, translator, inv_row)
        results.append(result)
    
    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n\n" + "="*80)
    print("TRANSLATION COMPLETE")
    print("="*80)
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {duration/60:.1f} minutes ({duration:.0f} seconds)")
    
    success_results = [r for r in results if r['status'] == 'success']
    failed_results = [r for r in results if r['status'] != 'success']
    
    print(f"\nSuccessful: {len(success_results)}/{len(results)}")
    print(f"Failed: {len(failed_results)}/{len(results)}")
    
    if success_results:
        total_blocks = sum(r['blocks_translated'] for r in success_results)
        avg_time = sum(r['translation_seconds'] for r in success_results) / len(success_results)
        
        print(f"\nTranslation statistics:")
        print(f"  Total text blocks translated: {total_blocks}")
        print(f"  Average time per artifact: {avg_time:.1f}s")
        
        # Language breakdown
        print(f"\nBy language:")
        lang_counts = {}
        for r in success_results:
            lang = r['source_lang']
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        for lang, count in sorted(lang_counts.items()):
            print(f"  {lang}: {count} artifacts")
    
    if failed_results:
        print(f"\n[FAILED ARTIFACTS]")
        for r in failed_results:
            print(f"  {r['doc_id']}: {r.get('error', 'Unknown error')}")
    
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
