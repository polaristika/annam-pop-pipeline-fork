#!/usr/bin/env python3
"""
Phase 2 Runner: Process digital_indic PDFs using direct_doc_generator

This script processes the 63 high-confidence digital_indic files from 
worklist_digital_indic.parquet using the proven PDF→MD→JSON pipeline.
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# Import pipeline components
from src.extract.direct_doc_generator import generate_doc_md_direct
from src.structure.md_to_json_converter_ultra import UltraFastMarkdownToJsonConverter


def process_single_pdf(row, converter):
    """Process a single PDF through the complete pipeline."""
    doc_id = row.doc_id
    pdf_path = row.file_path
    state = row.state
    # Extract name from file path
    name = Path(pdf_path).stem
    
    print(f"\n{'='*80}")
    print(f"[{doc_id}] Starting pipeline...")
    print(f"  PDF: {pdf_path}")
    print(f"  State: {state}")
    print(f"  Name: {name}")
    print(f"{'='*80}")
    
    # Setup output directory
    art_dir = Path("artifacts") / doc_id
    art_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # STEP 1: PDF → doc.md (with VLM and base64 images)
        print(f"\n[STEP 1] PDF → doc.md")
        start_time = datetime.now()
        
        md_path = generate_doc_md_direct(pdf_path, art_dir, doc_id)
        
        step1_duration = (datetime.now() - start_time).total_seconds()
        print(f"[STEP 1] ✓ Completed in {step1_duration:.1f}s")
        
        # STEP 2: doc.md → doc.json
        print(f"\n[STEP 2] doc.md → doc.json")
        start_time = datetime.now()
        
        metadata = {
            "State": state,
            "Name": name
        }
        
        json_data = converter.convert_md_to_json(str(md_path), doc_id, metadata)
        
        json_path = art_dir / 'doc.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        step2_duration = (datetime.now() - start_time).total_seconds()
        print(f"[STEP 2] ✓ Completed in {step2_duration:.1f}s")
        
        # Validation
        print(f"\n[VALIDATION]")
        md_size = md_path.stat().st_size / 1024 / 1024
        json_size = json_path.stat().st_size / 1024 / 1024
        num_blocks = len(json_data['content'])
        num_images = sum(1 for b in json_data['content'] if b.get('type') == 'image')
        
        print(f"  doc.md size: {md_size:.2f} MB")
        print(f"  doc.json size: {json_size:.2f} MB")
        print(f"  Content blocks: {num_blocks}")
        print(f"  Images: {num_images}")
        
        return {
            'doc_id': doc_id,
            'status': 'success',
            'md_size_mb': md_size,
            'json_size_mb': json_size,
            'num_blocks': num_blocks,
            'num_images': num_images,
            'step1_seconds': step1_duration,
            'step2_seconds': step2_duration,
            'error': None
        }
        
    except Exception as e:
        print(f"\n[ERROR] {doc_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'doc_id': doc_id,
            'status': 'failed',
            'error': str(e)
        }


def main():
    """Main Phase 2 processing loop."""
    print("="*80)
    print("PHASE 2: Digital Indic PDF Processing")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load Phase 2 worklist
    print("\n[LOADING] worklist_digital_indic.parquet...")
    worklist = pd.read_parquet('worklist_digital_indic.parquet')
    print(f"[LOADED] {len(worklist)} files to process")
    
    # Check for already processed files
    already_done = []
    for _, row in worklist.iterrows():
        doc_id = row.doc_id
        json_path = Path("artifacts") / doc_id / "doc.json"
        if json_path.exists():
            already_done.append(doc_id)
    
    if already_done:
        print(f"\n[SKIP] {len(already_done)} files already processed")
        print(f"  Examples: {', '.join(already_done[:5])}")
        worklist = worklist[~worklist['doc_id'].isin(already_done)]
        print(f"[REMAINING] {len(worklist)} files to process")
    
    if len(worklist) == 0:
        print("\n[COMPLETE] All files already processed!")
        return
    
    # Initialize converter
    converter = UltraFastMarkdownToJsonConverter()
    
    # Process all PDFs
    results = []
    start_time = datetime.now()
    
    print(f"\n[PROCESSING] Starting pipeline for {len(worklist)} files...")
    print("="*80)
    
    for idx, row in enumerate(worklist.itertuples(), 1):
        print(f"\n\n{'#'*80}")
        print(f"FILE {idx}/{len(worklist)}")
        print(f"{'#'*80}")
        
        result = process_single_pdf(row, converter)
        results.append(result)
        
        # Progress summary
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = sum(1 for r in results if r['status'] == 'failed')
        
        print(f"\n[PROGRESS] {idx}/{len(worklist)} complete | Success: {success_count} | Failed: {failed_count}")
    
    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n\n" + "="*80)
    print("PHASE 2 COMPLETE")
    print("="*80)
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {duration/60:.1f} minutes ({duration:.0f} seconds)")
    
    success_results = [r for r in results if r['status'] == 'success']
    failed_results = [r for r in results if r['status'] == 'failed']
    
    print(f"\nSuccessful: {len(success_results)}/{len(results)}")
    print(f"Failed: {len(failed_results)}/{len(results)}")
    
    if success_results:
        avg_step1 = sum(r['step1_seconds'] for r in success_results) / len(success_results)
        avg_step2 = sum(r['step2_seconds'] for r in success_results) / len(success_results)
        avg_total = avg_step1 + avg_step2
        
        print(f"\nAverage processing time:")
        print(f"  Step 1 (PDF→MD): {avg_step1:.1f}s")
        print(f"  Step 2 (MD→JSON): {avg_step2:.1f}s")
        print(f"  Total per file: {avg_total:.1f}s")
        
        total_images = sum(r['num_images'] for r in success_results)
        print(f"\nTotal images processed: {total_images}")
    
    if failed_results:
        print(f"\n[FAILED FILES]")
        for r in failed_results:
            print(f"  {r['doc_id']}: {r['error']}")
    
    # Save results
    results_df = pd.DataFrame(results)
    results_path = f"phase2_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\n[SAVED] Results to {results_path}")
    
    # Update worklist status
    print(f"\n[UPDATING] worklist_digital_indic.parquet status...")
    worklist_all = pd.read_parquet('worklist_digital_indic.parquet')
    success_ids = [r['doc_id'] for r in success_results]
    worklist_all.loc[worklist_all['doc_id'].isin(success_ids), 'status'] = 'done'
    worklist_all.to_parquet('worklist_digital_indic.parquet')
    print(f"[UPDATED] {len(success_ids)} files marked as 'done'")
    
    print("\n" + "="*80)
    print("Phase 2 processing complete!")
    print("="*80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Processing stopped by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[FATAL ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
