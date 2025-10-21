"""
Batch convert all doc.md files to doc.json format with parallel processing.
Uses the ultra-fast converter optimized for large base64 images.
"""
import sys
from pathlib import Path
import json
from multiprocessing import Pool, cpu_count
from functools import partial
from .md_to_json_converter_ultra import UltraFastMarkdownToJsonConverter


def convert_single_file(md_file_path: Path, worklist_path: str) -> tuple:
    """
    Convert a single markdown file to JSON.
    Returns (doc_id, success, error_message)
    """
    doc_id = md_file_path.parent.name
    json_file = md_file_path.parent / "doc.json"
    
    try:
        converter = UltraFastMarkdownToJsonConverter()
        converter.convert_and_save(str(md_file_path), str(json_file), doc_id, worklist_path)
        return (doc_id, True, None)
    except Exception as e:
        return (doc_id, False, str(e))


def batch_convert(artifacts_dir: str = "artifacts", worklist_path: str = "worklist.parquet", 
                 num_workers: int = None):
    """
    Batch convert all doc.md files to doc.json in parallel.
    
    Args:
        artifacts_dir: Path to artifacts directory
        worklist_path: Path to worklist.parquet
        num_workers: Number of parallel workers (default: all CPU cores)
    """
    # Find all doc.md files
    artifacts_path = Path(artifacts_dir)
    md_files = list(artifacts_path.glob("*/doc.md"))
    
    if not md_files:
        print("No doc.md files found in artifacts directory")
        return
    
    # Filter out files that already have doc.json
    files_to_convert = []
    for md_file in md_files:
        json_file = md_file.parent / "doc.json"
        if not json_file.exists():
            files_to_convert.append(md_file)
    
    if not files_to_convert:
        print("All doc.md files already have corresponding doc.json files")
        return
    
    print(f"Found {len(files_to_convert)} files to convert (out of {len(md_files)} total)")
    
    # Set number of workers
    if num_workers is None:
        num_workers = cpu_count()
    
    print(f"Using {num_workers} parallel workers...")
    
    # Create partial function with worklist_path
    convert_func = partial(convert_single_file, worklist_path=worklist_path)
    
    # Process in parallel
    success_count = 0
    error_count = 0
    
    with Pool(num_workers) as pool:
        results = pool.map(convert_func, files_to_convert)
    
    # Count results
    for doc_id, success, error_msg in results:
        if success:
            success_count += 1
            print(f"Converted artifacts/{doc_id}/doc.md -> artifacts/{doc_id}/doc.json")
        else:
            error_count += 1
            print(f"ERROR converting {doc_id}: {error_msg}")
    
    print(f"\nConversion complete: {success_count} successful, {error_count} failed")


def main():
    """CLI entry point."""
    artifacts_dir = sys.argv[1] if len(sys.argv) > 1 else "artifacts"
    worklist_path = sys.argv[2] if len(sys.argv) > 2 else "worklist.parquet"
    num_workers = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    batch_convert(artifacts_dir, worklist_path, num_workers)


if __name__ == "__main__":
    main()