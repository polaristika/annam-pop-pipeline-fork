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
        formatted_texts = []
        for text in texts:
            # Ensure text is a str
            if not isinstance(text, str):
                text = str(text)

            t = text.strip()

            # If the text already looks like "SRC TGT rest..." and has >=3 parts, keep it
            parts = t.split(" ", 2)
            if len(parts) == 3:
                src_tag = parts[0]
                # quick heuristic: if src_tag contains angle brackets like <2mr> or <mr>,
                # normalize to two-letter code and map to indic_lang
                if src_tag.startswith("<") and src_tag.endswith(">"):
                    inner = src_tag[1:-1]
                    # drop any leading digits like '2' used by some tokenizers
                    if len(inner) > 2 and inner[0].isdigit():
                        inner = inner.lstrip('0123456789')
                    two_letter = inner[-2:]
                    mapped = lang_map.get(two_letter, indic_lang)
                    formatted_texts.append(f"{mapped} {target_lang} {parts[2]}")
                    continue

                # if src_tag already matches one of our mapped values, keep it
                if src_tag in lang_map.values() or src_tag == indic_lang:
                    formatted_texts.append(t)
                    continue

                # if src_tag looks like a two-letter code (mr, ta, etc.), map it
                if len(src_tag) == 2 and src_tag.isalpha():
                    mapped = lang_map.get(src_tag, indic_lang)
                    formatted_texts.append(f"{mapped} {target_lang} {parts[2]}")
                    continue

            # For any other case, produce a safe, explicit formatted string
            formatted_texts.append(f"{indic_lang} {target_lang} {t}")
        
        translations = []
        for i in range(0, len(formatted_texts), batch_size):
            batch = formatted_texts[i:i+batch_size]
            
            # Tokenize (defensive: tokenizer from remote code may assert on unexpected formats)
            try:
                inputs = self.tokenizer(
                    batch,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512
                ).to(self.model.device)
            except (AssertionError, ValueError, Exception) as tok_err:
                print(f"    [WARNING] Tokenizer failed on batch with error: {tok_err}. Retrying with safe formatting...")
                # Rebuild a safe batch with explicit indic_lang target_lang prefix
                safe_batch = [f"{indic_lang} {target_lang} {('' if not isinstance(t, str) else t)}" for t in batch]
                try:
                    inputs = self.tokenizer(
                        safe_batch,
                        return_tensors="pt",
                        padding=True,
                        truncation=True,
                        max_length=512
                    ).to(self.model.device)
                    batch = safe_batch
                except (AssertionError, ValueError, Exception) as tok_err2:
                    print(f"    [ERROR] Safe-batch tokenization also failed: {tok_err2}. Falling back to item-wise tokenization.")
                    # Item-wise attempt: tokenize each item separately to isolate failures
                    inputs_list = []
                    for j, item in enumerate(batch):
                        safe_item = f"{indic_lang} {target_lang} {item}"
                        try:
                            single = self.tokenizer(
                                safe_item,
                                return_tensors="pt",
                                padding=True,
                                truncation=True,
                                max_length=512
                            )
                            inputs_list.append((j, single))
                        except Exception as e_item:
                            print(f"      [ERROR] Tokenizer failed for item {j}: {e_item}. Will skip this item.")
                            inputs_list.append((j, None))
                    # Create a combined inputs dict where possible; we'll process per-item later
                    # Use inputs_list sentinel to indicate per-item processing in generation stage
                    inputs = inputs_list
            
            # Translate
            with torch.no_grad():
                # If inputs is a list, we failed batch tokenization earlier and must process item-wise
                if isinstance(inputs, list):
                    # inputs is a list of tuples (index_in_batch, tokenized_or_None)
                    generated_texts = [None] * len(inputs)
                    for j, tokenized in inputs:
                        if tokenized is None:
                            generated_texts[j] = ""
                            continue
                        tokenized = {k: v.to(self.model.device) for k, v in tokenized.items()}
                        try:
                            out = self.model.generate(
                                **tokenized,
                                max_new_tokens=max_new_tokens,
                                num_beams=1,
                                use_cache=False,
                                early_stopping=True
                            )
                        except Exception as e_item_gen:
                            print(f"      [ERROR] Generation failed for item {j}: {e_item_gen}. Skipping.")
                            generated_texts[j] = ""
                            continue
                        dec = self.tokenizer.batch_decode(out, skip_special_tokens=True)
                        generated_texts[j] = dec[0] if dec else ""
                    # Append in-order translations for this batch
                    translations.extend(generated_texts)
                    continue

                try:
                    generated = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        num_beams=4,
                        early_stopping=True
                    )
                except Exception as e:
                    # Some model implementations (or device/dispatched setups) can
                    # raise internal errors related to past_key_values during
                    # beam search. Fall back to a safer generation mode (no
                    # caching / single-beam) and retry once.
                    print(f"    [WARNING] Primary generate failed: {e}; retrying with use_cache=False and num_beams=1")
                    try:
                        generated = self.model.generate(
                            **inputs,
                            max_new_tokens=max_new_tokens,
                            num_beams=1,
                            use_cache=False,
                            early_stopping=True
                        )
                    except Exception as e2:
                        print(f"    [ERROR] Fallback generate also failed: {e2}")
                        raise
            
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
