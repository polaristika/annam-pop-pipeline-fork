#!/usr/bin/env python3
"""
POP CLI - PDF Processing Pipeline Command Line Interface
Comprehensive CLI for PDF ingestion, classification, and processing
"""

import argparse
import sys
from pathlib import Path

# Add local modules to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "code" / "src"))

from pop_cli_commands.core.config import load_config
from pop_cli_commands.commands.inventory import InventoryCommand
from pop_cli_commands.commands.process import ProcessCommand
from pop_cli_commands.commands.batch import BatchCommand
from pop_cli_commands.commands.list import ListCommand
from pop_cli_commands.commands.status import StatusCommand
from pop_cli_commands.commands.config import ConfigCommand
from pop_cli_commands.commands.cleanup import CleanupCommand
from pop_cli_commands.commands.process_file import add_parser as add_process_file_parser


def create_parser():
    """Create the main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog='pop-cli',
        description='PDF Processing Pipeline CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pop-cli inventory --scan                  # Scan and classify all PDFs
  pop-cli list --phase 1 --limit 10         # List first 10 Phase 1 candidates  
  pop-cli process-file path/to/file.pdf     # Process single PDF directly
  pop-cli process --phase 1 --count 5       # Process 5 English PDFs
  pop-cli batch --phase 2 --all             # Process all Indic PDFs
  pop-cli status --summary                  # Show processing summary
  pop-cli config --show                     # Show current configuration
  pop-cli cleanup --logs                    # Clean up old log files

For more help on any command, use:
  pop-cli <command> --help
        """
    )
    
    # Global options
    parser.add_argument('--config', '-c', 
                       help='Configuration file path')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('--quiet', '-q', action='store_true', 
                       help='Suppress output except errors')
    
    # Create subcommand parsers
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Inventory command - PDF scanning and classification
    inventory_parser = subparsers.add_parser('inventory', 
                                           help='Scan and classify PDFs')
    InventoryCommand.add_arguments(inventory_parser)
    
    # Process command - Process individual files or small batches
    process_parser = subparsers.add_parser('process',
                                         help='Process PDFs (single/small batch)')
    ProcessCommand.add_arguments(process_parser)
    
    # Batch command - Large scale processing
    batch_parser = subparsers.add_parser('batch',
                                       help='Batch process many PDFs')
    BatchCommand.add_arguments(batch_parser)
    
    # List command - Show available PDFs and status
    list_parser = subparsers.add_parser('list',
                                      help='List PDFs and their status')
    ListCommand.add_arguments(list_parser)
    
    # Status command - Show processing status and statistics
    status_parser = subparsers.add_parser('status',
                                        help='Show processing status')
    StatusCommand.add_arguments(status_parser)
    
    # Config command - Manage configuration
    config_parser = subparsers.add_parser('config',
                                        help='Manage configuration')
    ConfigCommand.add_arguments(config_parser)
    
    # Cleanup command - Clean up files and reset state
    cleanup_parser = subparsers.add_parser('cleanup',
                                         help='Clean up files and logs')
    CleanupCommand.add_arguments(cleanup_parser)
    
    # Process-file command - Direct PDF processing
    add_process_file_parser(subparsers)
    
    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle no command provided
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)
    
    # Route to appropriate command
    # Some commands use func attribute (process-file), others use command classes
    if hasattr(args, 'func'):
        try:
            args.func(args)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
            sys.exit(130)
        except Exception as e:
            if args.verbose:
                import traceback
                traceback.print_exc()
            else:
                print(f"Error: {e}")
            sys.exit(1)
    else:
        # Classic command class pattern
        commands = {
            'inventory': InventoryCommand,
            'process': ProcessCommand,
            'batch': BatchCommand,
            'list': ListCommand,
            'status': StatusCommand,
            'config': ConfigCommand,
            'cleanup': CleanupCommand
        }
        
        command_class = commands.get(args.command)
        if not command_class:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
        
        try:
            command = command_class(config, args)
            result = command.execute()
            sys.exit(0 if result else 1)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
            sys.exit(130)
        except Exception as e:
            if args.verbose:
                import traceback
                traceback.print_exc()
            else:
                print(f"Error: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()