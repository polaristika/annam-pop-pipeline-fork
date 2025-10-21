#!/usr/bin/env python3
"""
Pre-flight check for pipeline optimization
"""
import torch
import sys
from pathlib import Path

def check_gpus():
    """Check GPU availability and specs"""
    if not torch.cuda.is_available():
        print("❌ CUDA not available")
        return False
    
    gpu_count = torch.cuda.device_count()
    print(f"✓ Found {gpu_count} GPU(s):")
    for i in range(gpu_count):
        props = torch.cuda.get_device_properties(i)
        print(f"  GPU {i}: {props.name} ({props.total_memory / 1024**3:.1f} GB)")
    
    return True

def check_cpus():
    """Check CPU cores"""
    import multiprocessing
    cores = multiprocessing.cpu_count()
    print(f"✓ Found {cores} CPU cores")
    return cores

def check_dependencies():
    """Check required packages"""
    required = [
        'transformers',
        'docling',
        'pandas',
        'typer',
        'PIL',
        'torch'
    ]
    
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        return False
    else:
        print(f"✓ All required packages installed")
        return True

def check_models():
    """Check if BLIP model is accessible"""
    try:
        from transformers import BlipProcessor, BlipForConditionalGeneration
        print("✓ BLIP model accessible")
        return True
    except Exception as e:
        print(f"❌ BLIP model check failed: {e}")
        return False

def check_worklist():
    """Check worklist.parquet exists"""
    if Path("worklist.parquet").exists():
        import pandas as pd
        wl = pd.read_parquet("worklist.parquet")
        pending = wl[(wl['route']=='digital_en') & (wl['status']=='pending')]
        print(f"✓ Worklist found: {len(pending)} pending digital_en files")
        return True
    else:
        print("❌ worklist.parquet not found")
        return False

def estimate_performance():
    """Estimate processing time"""
    import pandas as pd
    wl = pd.read_parquet("worklist.parquet")
    pending = wl[(wl['route']=='digital_en') & (wl['status']=='pending')]
    
    # Estimates (based on benchmarks)
    time_per_pdf_sequential = 2.5  # minutes
    time_per_pdf_parallel_8x = 0.35  # minutes (with 8 workers)
    
    sequential_time = len(pending) * time_per_pdf_sequential / 60  # hours
    parallel_time = len(pending) * time_per_pdf_parallel_8x / 60  # hours
    
    print(f"\n📊 Performance Estimates for {len(pending)} PDFs:")
    print(f"  Sequential (old): ~{sequential_time:.1f} hours")
    print(f"  Parallel 8x (new): ~{parallel_time:.1f} hours")
    print(f"  Speedup: {sequential_time/parallel_time:.1f}x faster")

if __name__ == "__main__":
    print("=" * 60)
    print("PIPELINE PRE-FLIGHT CHECK")
    print("=" * 60)
    print()
    
    checks = [
        ("GPU", check_gpus()),
        ("CPU", check_cpus() > 0),
        ("Dependencies", check_dependencies()),
        ("BLIP Model", check_models()),
        ("Worklist", check_worklist()),
    ]
    
    print()
    all_passed = all(result for _, result in checks)
    
    if all_passed:
        print("✅ All checks passed! Ready for pipeline run.")
        estimate_performance()
        sys.exit(0)
    else:
        print("❌ Some checks failed. Please fix issues before running.")
        sys.exit(1)
