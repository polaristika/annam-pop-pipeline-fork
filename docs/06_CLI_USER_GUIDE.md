# CLI User Guide - Complete Command Reference

**Last Updated:** October 21, 2025  
**CLI Version:** 2.0  
**Status:** Production Ready ✅

---

## Table of Contents
1. [Getting Started](#getting-started)
2. [Command Overview](#command-overview)
3. [inventory Command](#inventory-command)
4. [list Command](#list-command)
5. [process Command](#process-command)
6. [batch Command](#batch-command)
7. [status Command](#status-command)
8. [config Command](#config-command)
9. [cleanup Command](#cleanup-command)
10. [Common Workflows](#common-workflows)
11. [Configuration](#configuration)
12. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

1. **Python 3.8+** installed
2. **Virtual environment** activated
3. **Dependencies** installed

### Setup (One-time)

```bash
# 1. Navigate to project directory
cd /home/aic_u1/aic_u1/pop_scraping

# 2. Activate virtual environment
source venv/bin/activate

# 3. Verify installation
python pop_cli.py --help
```

### Quick Test

```bash
# Test CLI is working
python pop_cli.py --version

# Get help
python pop_cli.py --help
```

---

## Command Overview

The CLI provides **7 main commands**:

| Command | Purpose | Complexity |
|---------|---------|------------|
| `inventory` | Scan and classify PDFs | Low |
| `list` | Browse and filter PDFs | Low |
| `process` | Process few PDFs | Medium |
| `batch` | Process many PDFs | High |
| `status` | Check processing status | Low |
| `config` | Manage configuration | Low |
| `cleanup` | Clean up files | Medium |

### Global Options

Available for all commands:

```bash
python pop_cli.py <command> [options]

Global Options:
  --config PATH    Use custom configuration file
  --verbose, -v    Enable verbose output
  --quiet, -q      Suppress output except errors
  --help, -h       Show help message
```

---

## inventory Command

### Purpose
Scan PDFs, classify them, and maintain inventory database.

### Usage

```bash
python pop_cli.py inventory [--scan] [--update] [--show] [--export FORMAT]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--scan` | Full scan of all PDFs | - |
| `--update` | Incremental update | - |
| `--show` | Display inventory summary | - |
| `--export FORMAT` | Export inventory (csv, json, xlsx) | - |
| `--filter-phase N` | Filter by phase | All |
| `--filter-state STATE` | Filter by state | All |

### Examples

#### 1. Initial Scan (First Time)
```bash
# Scan all PDFs in data/raw/POP Bank/
python pop_cli.py inventory --scan

# Output:
# Scanning PDFs...
# Found 565 PDFs across 26 states
# 
# Classification Results:
#   Digital English: 498 (88.1%)
#   Scanned English: 42 (7.4%)
#   Digital Indic: 2 (0.4%)
#   Scanned Indic: 3 (0.5%)
#   Errors: 20 (3.5%)
#
# Inventory saved to: pdf_inventory.csv
```

#### 2. Show Inventory
```bash
# Display summary
python pop_cli.py inventory --show

# Output:
# PDF Inventory Summary
# =====================
# Total PDFs: 565
# 
# By Classification:
#   digital_en: 498 (88.1%)
#   scanned_en: 42 (7.4%)
#   digital_indic: 2 (0.4%)
#   scanned_indic: 3 (0.5%)
#   error: 20 (3.5%)
#
# By State (Top 5):
#   Maharashtra: 169 (29.9%)
#   Rajasthan: 127 (22.5%)
#   Andhra Pradesh: 40 (7.1%)
#   Punjab: 28 (5.0%)
#   Tamil Nadu: 24 (4.2%)
```

#### 3. Filter and Show
```bash
# Show only Phase 1 PDFs
python pop_cli.py inventory --show --filter-phase 1

# Show Maharashtra PDFs
python pop_cli.py inventory --show --filter-state Maharashtra
```

#### 4. Export
```bash
# Export to CSV
python pop_cli.py inventory --export csv

# Export to Excel
python pop_cli.py inventory --export xlsx

# Export filtered
python pop_cli.py inventory --show --filter-phase 1 --export phase1.csv
```

#### 5. Update Inventory
```bash
# Incremental update (faster)
# Checks for new PDFs only
python pop_cli.py inventory --update
```

### When to Use

- **First time:** Run `--scan` to build inventory
- **After adding PDFs:** Run `--update` to add new files
- **Before processing:** Run `--show` to see what's available
- **For analysis:** Export to CSV/Excel for external analysis

---

## list Command

### Purpose
Browse, filter, and export PDF lists for processing.

### Usage

```bash
python pop_cli.py list [options]
```

### Options

| Option | Description | Example |
|--------|-------------|---------|
| `--phase N` | Filter by phase (1 or 2) | `--phase 1` |
| `--state STATE` | Filter by state name | `--state Maharashtra` |
| `--limit N` | Limit number of results | `--limit 20` |
| `--min-confidence N` | Minimum confidence score | `--min-confidence 0.7` |
| `--sort FIELD` | Sort by field | `--sort confidence` |
| `--reverse` | Reverse sort order | `--reverse` |
| `--export FILE` | Export to file | `--export list.csv` |
| `--format FORMAT` | Output format (table, csv, json) | `--format json` |

### Examples

#### 1. List Phase 1 Candidates
```bash
# Show first 20 Phase 1 PDFs
python pop_cli.py list --phase 1 --limit 20

# Output:
# Phase 1 Candidates (Digital English)
# =====================================
# 
# File                              State         Confidence  Pages
# --------------------------------  ------------  ----------  -----
# Rice_POP.pdf                      Bihar         0.95        45
# Wheat_Cultivation.pdf             Rajasthan     0.92        38
# Sugarcane_Guide.pdf               Maharashtra   0.89        52
# ...
#
# Total: 152 PDFs (showing 20)
```

#### 2. Filter by State
```bash
# List Maharashtra PDFs
python pop_cli.py list --state Maharashtra

# List Maharashtra Phase 1 PDFs only
python pop_cli.py list --state Maharashtra --phase 1
```

#### 3. High Confidence PDFs
```bash
# Show PDFs with >90% confidence
python pop_cli.py list --min-confidence 0.9 --limit 10

# Sort by confidence (highest first)
python pop_cli.py list --sort confidence --reverse --limit 20
```

#### 4. Export Lists
```bash
# Export all Phase 1 PDFs to CSV
python pop_cli.py list --phase 1 --export phase1_all.csv

# Export Maharashtra Phase 2 PDFs
python pop_cli.py list --phase 2 --state Maharashtra --export mh_phase2.csv

# Export as JSON
python pop_cli.py list --phase 1 --format json --export phase1.json
```

#### 5. Detailed View
```bash
# Show all fields
python pop_cli.py list --phase 1 --limit 5 --format table

# JSON format for programmatic use
python pop_cli.py list --phase 1 --format json | jq '.[]'
```

### When to Use

- **Before processing:** Preview PDFs you're about to process
- **Selection:** Filter PDFs by criteria before batch processing
- **Analysis:** Export lists for external tools
- **Verification:** Check classification results

---

## process Command

### Purpose
Process single PDF or small batches (recommended: <10 PDFs).

### Usage

```bash
python pop_cli.py process --phase N [options]
```

### Options

| Option | Description | Required |
|--------|-------------|----------|
| `--phase N` | Phase number (1 or 2) | ✅ Yes |
| `--count N` | Number of PDFs to process | No (default: 1) |
| `--state STATE` | Process only this state | No |
| `--pdf FILE` | Process specific PDF | No |
| `--dry-run` | Preview without processing | No |
| `--parallel N` | Number of parallel workers | No (default: 4) |

### Examples

#### 1. Process Single PDF
```bash
# Process 1 Phase 1 PDF
python pop_cli.py process --phase 1

# Process 1 Phase 2 PDF
python pop_cli.py process --phase 2
```

#### 2. Process Multiple PDFs
```bash
# Process 5 Phase 1 PDFs
python pop_cli.py process --phase 1 --count 5

# Process 10 Phase 2 PDFs
python pop_cli.py process --phase 2 --count 10
```

#### 3. Process by State
```bash
# Process 5 Maharashtra Phase 1 PDFs
python pop_cli.py process --phase 1 --state Maharashtra --count 5
```

#### 4. Process Specific PDF
```bash
# Process specific file
python pop_cli.py process --phase 1 --pdf "data/raw/POP Bank/Bihar/Rice_POP.pdf"
```

#### 5. Dry Run (Preview)
```bash
# See what would be processed (doesn't actually process)
python pop_cli.py process --phase 1 --count 5 --dry-run

# Output:
# DRY RUN - No PDFs will be processed
# 
# Would process:
#   1. data/raw/POP Bank/Bihar/Rice_POP.pdf
#   2. data/raw/POP Bank/Maharashtra/Wheat.pdf
#   3. data/raw/POP Bank/Rajasthan/Cotton.pdf
#   4. data/raw/POP Bank/Punjab/Sugarcane.pdf
#   5. data/raw/POP Bank/Bihar/Maize.pdf
```

#### 6. Parallel Processing
```bash
# Use 8 workers for faster processing
python pop_cli.py process --phase 1 --count 20 --parallel 8
```

### Output Structure

```
Processing started...
[1/5] Processing Rice_POP.pdf (Bihar)... ✓ Done (45s)
[2/5] Processing Wheat.pdf (Maharashtra)... ✓ Done (38s)
[3/5] Processing Cotton.pdf (Rajasthan)... ✓ Done (52s)
[4/5] Processing Sugarcane.pdf (Punjab)... ✗ Failed (OCR error)
[5/5] Processing Maize.pdf (Bihar)... ✓ Done (41s)

Summary:
  Successful: 4/5 (80%)
  Failed: 1/5 (20%)
  Total Time: 3m 36s
  Average: 43s per PDF

Artifacts saved to: artifacts/phase1_english/
```

### When to Use

- **Testing:** Process few PDFs to test pipeline
- **Quick jobs:** Process specific PDFs or states
- **Development:** Test changes on small batches
- **Verification:** Process samples before large batch

---

## batch Command

### Purpose
Process large batches of PDFs (recommended: >10 PDFs).

### Usage

```bash
python pop_cli.py batch --phase N [options]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--phase N` | Phase number (1 or 2) | Required |
| `--all` | Process all PDFs in phase | False |
| `--state STATE` | Process only this state | All |
| `--limit N` | Maximum PDFs to process | No limit |
| `--parallel N` | Number of parallel workers | 4 |
| `--dry-run` | Preview without processing | False |
| `--resume` | Resume from last failure | False |
| `--skip-existing` | Skip already processed | True |

### Examples

#### 1. Process All Phase 1 PDFs
```bash
# Process all 152 Phase 1 PDFs
python pop_cli.py batch --phase 1 --all

# Expected output:
# Starting batch processing...
# Phase: 1 (Digital English)
# Total PDFs: 152
# Parallel workers: 4
#
# Progress: [████████████████████████████] 152/152 (100%)
# 
# Summary:
#   Successful: 152/152 (100%)
#   Failed: 0
#   Total Time: 1h 54m
#   Average: 45s per PDF
```

#### 2. Process by State
```bash
# Process all Maharashtra Phase 1 PDFs
python pop_cli.py batch --phase 1 --state Maharashtra --all

# Process first 50 Maharashtra PDFs
python pop_cli.py batch --phase 1 --state Maharashtra --limit 50
```

#### 3. Parallel Processing
```bash
# Use 8 workers (faster on multi-core machines)
python pop_cli.py batch --phase 1 --all --parallel 8

# Use 1 worker (sequential, easier debugging)
python pop_cli.py batch --phase 1 --all --parallel 1
```

#### 4. Dry Run
```bash
# Preview what would be processed
python pop_cli.py batch --phase 1 --all --dry-run

# Output shows: total count, estimated time, PDFs to process
```

#### 5. Resume After Failure
```bash
# If batch processing was interrupted
python pop_cli.py batch --phase 1 --all --resume

# Skips already processed PDFs, continues from where it stopped
```

#### 6. Force Reprocessing
```bash
# Reprocess even if already done
python pop_cli.py batch --phase 1 --all --skip-existing=false
```

### Progress Tracking

```
Batch Processing Progress
=========================
Phase: 1 (Digital English)
Total: 152 PDFs
Workers: 4

Progress: [███████░░░░░░░░░░░░░░░░░░░] 45/152 (29.6%)

Currently processing:
  Worker 1: Rice_POP.pdf [████████░░] 80%
  Worker 2: Wheat.pdf [██████░░░░] 60%
  Worker 3: Cotton.pdf [███░░░░░░░] 30%
  Worker 4: Maize.pdf [█░░░░░░░░░] 10%

Stats:
  Completed: 41
  Processing: 4
  Pending: 107
  Failed: 0
  Elapsed: 28m 15s
  Remaining: ~1h 2m
  Speed: 1.45 PDFs/min
```

### When to Use

- **Production:** Process entire phases
- **Large states:** Process all PDFs from major states
- **Automation:** Scheduled or automated runs
- **Performance:** Parallel processing for speed

---

## status Command

### Purpose
Monitor processing status and statistics.

### Usage

```bash
python pop_cli.py status [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--summary` | Overall summary |
| `--phase N` | Phase-specific status |
| `--detailed` | Detailed statistics |
| `--recent N` | Show N most recent |
| `--failed` | Show failed PDFs |
| `--export FILE` | Export status report |

### Examples

#### 1. Overall Summary
```bash
python pop_cli.py status --summary

# Output:
# Processing Status Summary
# =========================
#
# Phase 1 (Digital English):
#   Total: 152 PDFs
#   Processed: 152 (100%)
#   Failed: 0 (0%)
#   Status: ✅ Complete
#
# Phase 2 (Digital Indic):
#   Total: 63 PDFs
#   Processed: 63 (100%)
#   Failed: 0 (0%)
#   Status: ✅ Complete
#
# Overall:
#   Total PDFs: 565
#   Processed: 215 (38.1%)
#   Remaining: 350 (61.9%)
```

#### 2. Phase-Specific Status
```bash
# Phase 1 details
python pop_cli.py status --phase 1

# Phase 2 details
python pop_cli.py status --phase 2
```

#### 3. Detailed Statistics
```bash
python pop_cli.py status --detailed

# Shows:
# - Processing times (min, max, avg)
# - Success rates by state
# - File sizes
# - Error breakdown
# - Performance metrics
```

#### 4. Recent Activity
```bash
# Show 10 most recently processed
python pop_cli.py status --recent 10

# Output:
# Recent Processing Activity
# ==========================
#
# 2025-10-21 10:30:15  Rice_POP.pdf         Phase 1  ✓ Success  45s
# 2025-10-21 10:29:28  Wheat.pdf            Phase 1  ✓ Success  38s
# 2025-10-21 10:28:45  Cotton.pdf           Phase 1  ✓ Success  52s
# ...
```

#### 5. Failed PDFs
```bash
python pop_cli.py status --failed

# Shows all failed PDFs with error reasons
```

#### 6. Export Status
```bash
# Export complete status report
python pop_cli.py status --detailed --export status_report.csv
```

### Status Fields

| Field | Description |
|-------|-------------|
| Status | pending, processing, complete, failed |
| Phase | 1, 2, 3, 4, 5, or 6 |
| Progress | Percentage complete |
| Success Rate | Successful / Total |
| Avg Time | Average processing time |
| Last Processed | Most recent completion |

---

## config Command

### Purpose
Manage CLI configuration.

### Usage

```bash
python pop_cli.py config [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--show` | Display current configuration |
| `--create-default` | Create default config file |
| `--validate` | Validate configuration |
| `--edit` | Open config in editor |
| `--output FILE` | Custom config file location |

### Examples

#### 1. Show Configuration
```bash
python pop_cli.py config --show

# Output:
# Current Configuration
# =====================
#
# Paths:
#   data_root: data/raw/POP Bank
#   inventory_csv: pdf_inventory.csv
#   artifacts_dir: artifacts
#
# Phase 1:
#   lang_guess: en
#   lang_conf_min: 0.5
#   digital_guess: true
#
# Phase 2:
#   lang_guess: indic
#   lang_conf_min: 0.3
#   digital_guess: true
```

#### 2. Create Default Config
```bash
# Create config/pop_cli.yaml
python pop_cli.py config --create-default

# Create in custom location
python pop_cli.py config --create-default --output my_config.yaml
```

#### 3. Validate Configuration
```bash
python pop_cli.py config --validate

# Output:
# ✓ Configuration file found
# ✓ All paths exist
# ✓ Phase 1 criteria valid
# ✓ Phase 2 criteria valid
# ✅ Configuration is valid
```

### Configuration File

**Location:** `config/pop_cli.yaml`

```yaml
# PDF Processing CLI Configuration

paths:
  data_root: "data/raw/POP Bank"
  inventory_csv: "pdf_inventory.csv"
  artifacts_dir: "artifacts"
  logs_dir: "logs"

phase1:
  criteria:
    lang_guess: "en"
    lang_conf_min: 0.5
    digital_guess: true
    garbled_detected: false
  output_dir: "artifacts/phase1_english"

phase2:
  criteria:
    lang_guess: "indic"
    lang_conf_min: 0.3
    digital_guess: true
  output_dir: "artifacts/phase2_indic"
  translation:
    target_lang: "en"
    batch_size: 50

processing:
  parallel_workers: 4
  timeout_seconds: 300
  retry_attempts: 3

logging:
  level: "INFO"
  file: "logs/pop_cli.log"
```

---

## cleanup Command

### Purpose
Clean up temporary files, logs, and artifacts.

### Usage

```bash
python pop_cli.py cleanup [options]
```

### Options

| Option | Description |
|--------|-------------|
| `--target TYPE` | What to clean (temp, logs, artifacts, all) |
| `--older-than N` | Days threshold for file age |
| `--dry-run` | Preview without deleting |
| `--force` | Skip confirmation prompt |

### Examples

#### 1. Dry Run (Preview)
```bash
# See what would be cleaned
python pop_cli.py cleanup --target temp --dry-run

# Output:
# DRY RUN - No files will be deleted
#
# Would delete:
#   temp/img_001.jpg (2.1 MB)
#   temp/img_002.png (1.8 MB)
#   temp/ocr_cache.pkl (15.3 MB)
#   ...
#
# Total: 24 files (52.3 MB)
```

#### 2. Clean Temporary Files
```bash
# Clean temp files
python pop_cli.py cleanup --target temp

# With confirmation:
# Clean 24 temporary files (52.3 MB)? [y/N]: y
# ✓ Cleaned 24 files (52.3 MB)
```

#### 3. Clean Old Logs
```bash
# Clean logs older than 30 days
python pop_cli.py cleanup --target logs --older-than 30

# Clean all logs
python pop_cli.py cleanup --target logs --force
```

#### 4. Clean Artifacts
```bash
# ⚠️  WARNING: This deletes processed outputs!

# Preview first
python pop_cli.py cleanup --target artifacts --dry-run

# Clean (with confirmation)
python pop_cli.py cleanup --target artifacts
```

#### 5. Clean Everything
```bash
# Clean all temporary files and logs
python pop_cli.py cleanup --target all --older-than 7 --dry-run

# Execute
python pop_cli.py cleanup --target all --older-than 7
```

### Cleanup Targets

| Target | Description | Safe? |
|--------|-------------|-------|
| `temp` | Temporary processing files | ✅ Yes |
| `logs` | Log files | ✅ Yes |
| `cache` | OCR/model caches | ✅ Yes |
| `artifacts` | Processed outputs | ⚠️  Be careful |
| `all` | All above | ⚠️  Use with caution |

---

## Common Workflows

### Workflow 1: First Time Setup

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Create configuration
python pop_cli.py config --create-default
python pop_cli.py config --validate

# 3. Scan PDFs
python pop_cli.py inventory --scan

# 4. Review inventory
python pop_cli.py inventory --show

# 5. Test with sample
python pop_cli.py process --phase 1 --count 1
```

### Workflow 2: Process Phase 1

```bash
# 1. Check Phase 1 candidates
python pop_cli.py list --phase 1 --limit 10

# 2. Test with 5 PDFs
python pop_cli.py process --phase 1 --count 5

# 3. Review results
python pop_cli.py status --phase 1

# 4. Process all
python pop_cli.py batch --phase 1 --all

# 5. Verify completion
python pop_cli.py status --phase 1 --detailed
```

### Workflow 3: Process Phase 2

```bash
# 1. List Indic PDFs
python pop_cli.py list --phase 2

# 2. Test with 2 PDFs
python pop_cli.py process --phase 2 --count 2

# 3. Check results
python pop_cli.py status --phase 2

# 4. Process specific state
python pop_cli.py batch --phase 2 --state Maharashtra --all

# 5. Process remaining
python pop_cli.py batch --phase 2 --all
```

### Workflow 4: Resume After Interruption

```bash
# 1. Check what was completed
python pop_cli.py status --phase 1 --detailed

# 2. Resume processing
python pop_cli.py batch --phase 1 --all --resume

# 3. Clean temp files
python pop_cli.py cleanup --target temp
```

### Workflow 5: Export and Analysis

```bash
# 1. Export inventory
python pop_cli.py inventory --export inventory_full.csv

# 2. Export Phase 1 list
python pop_cli.py list --phase 1 --export phase1_list.csv

# 3. Export status report
python pop_cli.py status --detailed --export status.csv

# 4. Analyze in Excel/Python
# (Use exported CSV files)
```

---

## Configuration

### Environment Variables

```bash
# Set custom configuration file
export POP_CLI_CONFIG="my_config.yaml"

# Set log level
export POP_CLI_LOG_LEVEL="DEBUG"

# Set number of workers
export POP_CLI_WORKERS="8"
```

### Configuration Precedence

1. **Command-line arguments** (highest priority)
2. **Environment variables**
3. **Configuration file** (`config/pop_cli.yaml`)
4. **Default values** (lowest priority)

---

## Troubleshooting

### Common Issues

#### Issue 1: "Inventory not found"
```bash
# Error: ❌ Inventory file not found: pdf_inventory.csv

# Solution: Run inventory scan
python pop_cli.py inventory --scan
```

#### Issue 2: "No PDFs found for phase"
```bash
# Error: ❌ No PDFs found for Phase 1

# Solution: Check classification
python pop_cli.py inventory --show
python pop_cli.py list --phase 1
```

#### Issue 3: Processing fails
```bash
# Check status
python pop_cli.py status --failed

# Review logs
tail -f logs/pop_cli.log

# Retry failed PDFs
python pop_cli.py process --phase 1 --count 1
```

#### Issue 4: Out of memory
```bash
# Reduce parallel workers
python pop_cli.py batch --phase 1 --all --parallel 2

# Or process sequentially
python pop_cli.py batch --phase 1 --all --parallel 1
```

#### Issue 5: Configuration issues
```bash
# Validate config
python pop_cli.py config --validate

# Reset to defaults
python pop_cli.py config --create-default --force
```

### Getting Help

#### Command Help
```bash
# General help
python pop_cli.py --help

# Command-specific help
python pop_cli.py inventory --help
python pop_cli.py process --help
python pop_cli.py batch --help
```

#### Verbose Mode
```bash
# Enable verbose output
python pop_cli.py process --phase 1 --count 5 --verbose

# Shows detailed logs and progress
```

#### Log Files
```bash
# View main log
tail -f logs/pop_cli.log

# View phase-specific logs
tail -f logs/phase1/processing.log
```

---

## Best Practices

### 1. Always Test First
```bash
# Don't: Immediate batch processing
python pop_cli.py batch --phase 1 --all

# Do: Test with small batch first
python pop_cli.py process --phase 1 --count 5
# Then: Process all
python pop_cli.py batch --phase 1 --all
```

### 2. Use Dry Run
```bash
# Preview before executing
python pop_cli.py batch --phase 1 --all --dry-run
python pop_cli.py cleanup --target all --dry-run
```

### 3. Monitor Progress
```bash
# Check status regularly
watch -n 60 'python pop_cli.py status --summary'

# Or in another terminal
python pop_cli.py status --phase 1 --detailed
```

### 4. Clean Up Regularly
```bash
# Clean temp files after processing
python pop_cli.py cleanup --target temp

# Clean old logs monthly
python pop_cli.py cleanup --target logs --older-than 30
```

### 5. Backup Configuration
```bash
# Backup config before changes
cp config/pop_cli.yaml config/pop_cli.yaml.backup

# Backup inventory
cp pdf_inventory.csv pdf_inventory.backup.csv
```

---

## Quick Reference Card

```bash
# SETUP
python pop_cli.py config --create-default
python pop_cli.py inventory --scan

# BROWSE
python pop_cli.py inventory --show
python pop_cli.py list --phase 1 --limit 20

# PROCESS
python pop_cli.py process --phase 1 --count 5        # Test
python pop_cli.py batch --phase 1 --all             # Full

# MONITOR
python pop_cli.py status --summary                   # Overview
python pop_cli.py status --phase 1 --detailed       # Details

# CLEANUP
python pop_cli.py cleanup --target temp              # Safe
python pop_cli.py cleanup --target logs --older-than 30

# HELP
python pop_cli.py --help
python pop_cli.py <command> --help
```

---

## Conclusion

You now have complete control over the PDF processing pipeline through a user-friendly CLI!

**Next Steps:**
1. ✅ Scan your PDFs: `python pop_cli.py inventory --scan`
2. ✅ Test processing: `python pop_cli.py process --phase 1 --count 5`
3. ✅ Process all: `python pop_cli.py batch --phase 1 --all`
4. ✅ Monitor status: `python pop_cli.py status --summary`

**Happy Processing! 🚀**
