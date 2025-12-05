"""
Centralized logging for macacaMRIprep.

This module provides a centralized logging system for the package.
Usage:
    1. Call setup_logging() once at the start of your program for main application logging
    2. Use setup_workflow_logging() for workflow-specific logging
    3. Use get_logger(__name__) in each module to get a logger
"""

import os
import logging
import sys
from pathlib import Path
from typing import Optional, Union, Any

# Create the central logger with default configuration
_LOGGER = logging.getLogger("macacaMRIprep")
_LOGGER.setLevel(logging.WARNING)  # Default to WARNING level
_LOGGER.addHandler(logging.StreamHandler())  # Default to console output


def normalize_verbose(value: Any, default: int = 1) -> int:
    """Normalize any verbose value to integer 0, 1, or 2.
    
    This function ensures consistent verbose handling throughout the codebase.
    All verbose values are normalized to integers: 0 (quiet), 1 (normal), or 2 (verbose).
    
    Args:
        value: Verbose value of any type (int, bool, str, None, etc.)
        default: Default value to use if normalization fails (default: 1)
        
    Returns:
        Integer verbose level: 0, 1, or 2
        
    Examples:
        >>> normalize_verbose(2)
        2
        >>> normalize_verbose(True)
        2
        >>> normalize_verbose(False)
        0
        >>> normalize_verbose("1")
        1
        >>> normalize_verbose("INFO")
        1
        >>> normalize_verbose("DEBUG")
        2
        >>> normalize_verbose(None)
        1
    """
    # Handle None
    if value is None:
        return default
    
    # Handle integers - clamp to 0-2 range
    if isinstance(value, int):
        return max(0, min(2, value))
    
    # Handle booleans
    if isinstance(value, bool):
        return 2 if value else 0
    
    # Handle strings
    if isinstance(value, str):
        # Try to convert numeric strings
        try:
            int_value = int(value)
            return max(0, min(2, int_value))
        except ValueError:
            # Map log level strings to verbose levels
            log_level_upper = value.upper()
            if log_level_upper in ("DEBUG", "VERBOSE"):
                return 2
            elif log_level_upper in ("INFO", "NORMAL"):
                return 1
            elif log_level_upper in ("WARNING", "WARN", "ERROR", "CRITICAL", "QUIET"):
                return 0
            else:
                # Unknown string, return default
                return default
    
    # For any other type, return default
    return default

def verbose_to_log_level(verbose: int) -> str:
    """Convert verbose integer (0-2) to Python logging level string.
    
    Args:
        verbose: Verbose level (0=quiet, 1=normal, 2=verbose)
        
    Returns:
        Logging level string: "ERROR", "INFO", or "DEBUG"
        
    Examples:
        >>> verbose_to_log_level(0)
        'ERROR'
        >>> verbose_to_log_level(1)
        'INFO'
        >>> verbose_to_log_level(2)
        'DEBUG'
    """
    # Clamp to valid range
    verbose = max(0, min(2, int(verbose)))
    
    if verbose == 0:
        return "ERROR"  # Quiet mode - only show errors
    elif verbose == 1:
        return "INFO"   # Normal mode - standard information
    else:  # verbose == 2
        return "DEBUG"  # Verbose mode - show everything

def setup_logging(
    log_file: Optional[str] = None,
    level: Union[str, int] = logging.INFO,
    name: str = "macacaMRIprep",
    format_str: str = '%(asctime)s | %(levelname)-8s | %(message)s'
) -> None:
    """Set up main application logging configuration.
    
    This function should be called once at the start of your program.
    After calling this, use get_logger() to get logger instances.
    
    Args:
        log_file: Optional path to main application log file. If not provided, logs to console only.
        level: Logging level (string or int). If string, must be one of:
            'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        name: Name of the logger (default: "macacaMRIprep")
        format_str: Format string for log messages
    """
    global _LOGGER
    
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper())
    
    # Create formatters (datefmt removes milliseconds from timestamp)
    datefmt = '%Y-%m-%d %H:%M:%S'
    console_formatter = logging.Formatter(format_str, datefmt=datefmt)
    file_formatter = logging.Formatter(format_str, datefmt=datefmt)
    
    # Create handlers
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    
    handlers = [console_handler]
    
    # Add file handler if log_file is provided
    if log_file:
        try:
            # Create log directory if it doesn't exist
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level)
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Failed to setup file logging to {log_file}: {e}", file=sys.stderr)
    
    # Configure the central logger
    _LOGGER.setLevel(level)
    _LOGGER.handlers = []  # Clear existing handlers
    for handler in handlers:
        _LOGGER.addHandler(handler)

def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance.
    
    Use this function to get a logger in any module.
    Example: logger = get_logger(__name__)
    
    Args:
        name: Optional name for the logger. If provided, returns a child logger
              of the central logger with the given name.
              
    Returns:
        Logger instance.
    """
    if name:
        return _LOGGER.getChild(name)
    return _LOGGER

def setup_step_logging(
    logs_dir: Union[str, Path],
    step_name: str,
    level: Union[str, int] = logging.DEBUG,
    format_str: str = '%(asctime)s | %(levelname)-8s | %(message)s'
) -> logging.Logger:
    """Set up step-specific logging.
    
    This creates a separate logger for step-specific logging that puts logs
    directly in the main logs directory. GUARANTEES step log file creation.
    
    Args:
        logs_dir: Main logs directory where step log files should be stored
        step_name: Name for the step logger
        level: Logging level
        format_str: Format string for log messages
        
    Returns:
        Step-specific logger instance
        
    Raises:
        RuntimeError: If step log file cannot be created
    """
    logs_dir = Path(logs_dir)
    
    # Ensure logs directory exists
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Failed to create logs directory {logs_dir}: {e}")
    
    # Create step-specific logger
    step_logger = logging.getLogger(f"macacaMRIprep.step.{step_name}")
    step_logger.setLevel(level)
    
    # Don't propagate to parent logger to avoid duplicate messages
    # Set this BEFORE adding handlers to ensure no propagation happens
    step_logger.propagate = False
    
    # Clear any existing handlers to avoid duplicates
    step_logger.handlers.clear()
    
    # Create formatters (datefmt removes milliseconds from timestamp)
    datefmt = '%Y-%m-%d %H:%M:%S'
    console_formatter = logging.Formatter(format_str, datefmt=datefmt)
    file_formatter = logging.Formatter(format_str, datefmt=datefmt)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    step_logger.addHandler(console_handler)
    
    # Create file handler for step-specific log (directly in logs_dir)
    log_file = logs_dir / f"{step_name}.log"
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        step_logger.addHandler(file_handler)
        
        # Log initialization to confirm logging is working
        step_logger.info(f"Step logging initialized: {log_file}")
        step_logger.info(f"Step name: {step_name}")
        step_logger.info(f"Logging level: {logging.getLevelName(level)}")
        
    except Exception as e:
        # If we can't create the step log file, this is a critical error
        error_msg = f"CRITICAL: Failed to create step log file {log_file}: {e}"
        print(error_msg, file=sys.stderr)
        raise RuntimeError(error_msg)
    
    return step_logger

def setup_workflow_logging(
    workflow_dir: Union[str, Path],
    workflow_name: str,
    level: Union[str, int] = logging.INFO,
    format_str: str = '%(asctime)s | %(levelname)-8s | %(message)s'
) -> logging.Logger:
    """Set up workflow-specific logging.
    
    This creates a workflow.log file in the specified directory and returns a logger
    that writes to both the file and console.
    
    Args:
        workflow_dir: Directory where workflow.log should be created
        workflow_name: Name of the workflow for the logger
        level: Logging level
        format_str: Format string for log messages
        
    Returns:
        Workflow logger instance
        
    Raises:
        RuntimeError: If workflow.log file cannot be created
    """
    workflow_dir = Path(workflow_dir)
    
    # Ensure workflow directory exists
    try:
        workflow_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Failed to create workflow directory {workflow_dir}: {e}")
    
    # Create workflow-specific logger
    workflow_logger = logging.getLogger(f"macacaMRIprep.{workflow_name}")
    workflow_logger.setLevel(level)
    
    # Don't propagate to parent logger to avoid duplicate messages
    # Set this BEFORE adding handlers to ensure no propagation happens
    workflow_logger.propagate = False
    
    # Clear any existing handlers to avoid duplicates
    workflow_logger.handlers.clear()
    
    # Create formatters (datefmt removes milliseconds from timestamp)
    datefmt = '%Y-%m-%d %H:%M:%S'
    console_formatter = logging.Formatter(format_str, datefmt=datefmt)
    file_formatter = logging.Formatter(format_str, datefmt=datefmt)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    workflow_logger.addHandler(console_handler)
    
    # Create file handler for workflow.log
    log_file = workflow_dir / "workflow.log"
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        workflow_logger.addHandler(file_handler)
        
        # Log initialization to confirm logging is working
        workflow_logger.info(f"Workflow logging initialized: {log_file}")
        workflow_logger.info(f"Workflow name: {workflow_name}")
        workflow_logger.info(f"Logging level: {logging.getLevelName(level)}")
        
    except Exception as e:
        # If we can't create the workflow log file, this is a critical error
        error_msg = f"CRITICAL: Failed to create workflow log file {log_file}: {e}"
        print(error_msg, file=sys.stderr)
        raise RuntimeError(error_msg)
    
    return workflow_logger

def ensure_workflow_log_exists(workflow_dir: Union[str, Path]) -> bool:
    """Ensure that workflow.log exists in the given directory.
    
    This is a utility function to verify that workflow logging is properly set up.
    
    Args:
        workflow_dir: Directory where workflow.log should exist
        
    Returns:
        True if workflow.log exists and is writable, False otherwise
    """
    workflow_dir = Path(workflow_dir)
    log_file = workflow_dir / "workflow.log"
    
    if not log_file.exists():
        return False
    
    # Check if file is writable and has some content
    try:
        with open(log_file, 'a') as f:
            pass
        # Check if file has content (at least some logging was written)
        file_size = log_file.stat().st_size
        if file_size > 0:
            return True
        return False
    except Exception:
        return False

def log_workflow_start(workflow_logger: logging.Logger, workflow_name: str, config: dict) -> None:
    """Log workflow start information.
    
    Args:
        workflow_logger: The workflow logger instance
        workflow_name: Name of the workflow
        config: Workflow configuration
    """
    workflow_logger.info("=" * 80)
    workflow_logger.info(f"Workflow: starting {workflow_name}")
    workflow_logger.info("=" * 80)
    workflow_logger.info(f"Config: {len(config)} parameters loaded")
    workflow_logger.info("=" * 80)

def log_workflow_end(workflow_logger: logging.Logger, workflow_name: str, success: bool, duration: float = None) -> None:
    """Log workflow end information.
    
    Args:
        workflow_logger: The workflow logger instance
        workflow_name: Name of the workflow
        success: Whether the workflow completed successfully
        duration: Workflow duration in seconds (optional)
    """
    workflow_logger.info("=" * 80)
    if success:
        workflow_logger.info(f"Workflow: ✓ {workflow_name} completed successfully")
    else:
        workflow_logger.error(f"Workflow: ✗ {workflow_name} failed")
    
    if duration is not None:
        workflow_logger.info(f"Duration: {duration:.2f} seconds")
    
    workflow_logger.info("=" * 80)

def log_step_start(step_logger: logging.Logger, step_name: str, inputs: dict) -> None:
    """Log step start information.
    
    Args:
        step_logger: The step logger instance
        step_name: Name of the step
        inputs: Step input parameters
    """
    step_logger.info("-" * 60)
    step_logger.info(f"Step: starting {step_name}")
    step_logger.info("-" * 60)
    step_logger.info(f"Inputs: {len(inputs)} parameters")
    step_logger.info("-" * 60)

def log_step_end(step_logger: logging.Logger, step_name: str, success: bool, outputs: dict = None, duration: float = None) -> None:
    """Log step end information.
    
    Args:
        step_logger: The step logger instance
        step_name: Name of the step
        success: Whether the step completed successfully
        outputs: Step output files (optional)
        duration: Step duration in seconds (optional)
    """
    step_logger.info("-" * 60)
    if success:
        step_logger.info(f"Step: {step_name} completed successfully")
        if outputs:
            step_logger.info(f"Outputs: {len(outputs)} files generated")
    else:
        step_logger.error(f"Step: {step_name} failed")
    
    if duration is not None:
        step_logger.info(f"Duration: {duration:.2f} seconds")
    
    step_logger.info("-" * 60) 