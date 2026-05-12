#!/usr/bin/env python3
import schedule
import time
import subprocess
import sys
import logging
from pathlib import Path

DIR = Path(__file__).parent
PYTHON = str(DIR / "venv" / "bin" / "python")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(DIR / "pipeline.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

def run_pipeline():
    logging.info("=== pipeline start ===")
    for script in ["new_create_document.py", "new_create_chunks.py"]:
        logging.info(f"running {script}")
        result = subprocess.run(
            [PYTHON, str(DIR / script)],
            cwd=DIR,
            capture_output=False,
        )
        if result.returncode != 0:
            logging.error(f"{script} exited with code {result.returncode} — aborting run")
            return
    logging.info("=== pipeline done ===")

schedule.every(10).minutes.do(run_pipeline)

logging.info("Scheduler started — running every 10 minutes. Ctrl+C to stop.")
run_pipeline()  # run immediately on start

while True:
    schedule.run_pending()
    time.sleep(30)
