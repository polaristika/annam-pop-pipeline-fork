"""
Centralized logging utility for the pop_scraping pipeline.
Provides file and console logging with timestamps and structured formatting.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime

# Global logger instance
_logger = None

def setup_logger(name: str = "pop_scraping", log_dir: str = "logs", level: int = logging.INFO):
    """
    Setup centralized logger with file and console handlers.
    
    Args:
        name: Logger name
        log_dir: Directory to store log files
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    global _logger
    
    if _logger is not None:
        return _logger
    
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '[%(levelname)s] %(message)s'
    )
    
    # File handler - main log
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    main_log = log_path / f"pipeline_{timestamp}.log"
    file_handler = logging.FileHandler(main_log, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    _logger = logger
    logger.info(f"Logger initialized. Logging to: {main_log}")
    
    return logger


def get_logger():
    """Get or create the global logger instance."""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger


def log_pipeline_start(bucket: str, total_files: int, workers: int):
    """Log pipeline start information."""
    logger = get_logger()
    logger.info("="*80)
    logger.info("PIPELINE EXECUTION STARTED")
    logger.info("="*80)
    logger.info(f"Bucket: {bucket}")
    logger.info(f"Total files: {total_files}")
    logger.info(f"Parallel workers: {workers}")
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("-"*80)


def log_pipeline_complete(success_count: int, failed_count: int, duration_seconds: float):
    """Log pipeline completion information."""
    logger = get_logger()
    logger.info("-"*80)
    logger.info("PIPELINE EXECUTION COMPLETED")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Total duration: {duration_seconds:.2f} seconds ({duration_seconds/60:.2f} minutes)")
    logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)


def log_step_start(step_name: str, file_count: int):
    """Log step start."""
    logger = get_logger()
    logger.info(f"[{step_name}] Starting with {file_count} files...")


def log_step_complete(step_name: str, success: int, failed: int):
    """Log step completion."""
    logger = get_logger()
    logger.info(f"[{step_name}] Complete: {success} successful, {failed} failed")


def log_file_start(doc_id: str, filename: str):
    """Log individual file processing start."""
    logger = get_logger()
    logger.info(f"[{doc_id}] START: {filename}")


def log_file_success(doc_id: str, output_type: str):
    """Log individual file success."""
    logger = get_logger()
    logger.info(f"[{doc_id}] ✓ {output_type} generated")


def log_file_error(doc_id: str, error_msg: str):
    """Log individual file error."""
    logger = get_logger()
    logger.error(f"[{doc_id}] ✗ ERROR: {error_msg}")


def log_warning(doc_id: str, warning_msg: str):
    """Log warning."""
    logger = get_logger()
    logger.warning(f"[{doc_id}] WARNING: {warning_msg}")


def log_info(message: str):
    """Log general info message."""
    logger = get_logger()
    logger.info(message)
