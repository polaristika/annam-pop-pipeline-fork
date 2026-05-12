"""
Base command class for POP CLI
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pop_cli_commands.core.config import Config


class BaseCommand(ABC):
    """Base class for all CLI commands."""
    
    def __init__(self, config: Config, args: Any):
        self.config = config
        self.args = args
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """Setup command-specific logger."""
        logger = logging.getLogger(f"pop_cli.{self.__class__.__name__}")
        
        if not logger.handlers:
            # Create logs directory if it doesn't exist
            log_dir = Path(self.config.get('paths.logs', 'logs'))
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # File handler
            log_file = log_dir / 'pop_cli.log'
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            
            # Console handler
            console_handler = logging.StreamHandler()
            if hasattr(self.args, 'verbose') and self.args.verbose:
                console_handler.setLevel(logging.DEBUG)
            elif hasattr(self.args, 'quiet') and self.args.quiet:
                console_handler.setLevel(logging.ERROR)
            else:
                console_handler.setLevel(logging.INFO)
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            logger.setLevel(logging.DEBUG)
        
        return logger
    
    @staticmethod
    @abstractmethod
    def add_arguments(parser):
        """Add command-specific arguments to parser."""
        pass
    
    @abstractmethod
    def execute(self) -> bool:
        """Execute the command. Return True for success, False for failure."""
        pass