"""
Centralized logging for nhp_mri_prep.

This module provides a centralized logging system for the package.
Usage:
    1. Call setup_logging() once at the start of your program for main application logging
    2. Use setup_workflow_logging() for workflow-specific logging
    3. Use get_logger(__name__) in each module to get a logger
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Union, Any

# Standard console/file format for brainana (no milliseconds in timestamps).
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# In-repo sibling packages that ship their own loggers. When brainana sets up
# logging we silence their stray handlers so notebook/IPython output isn't
# duplicated or formatted with milliseconds. Keep this list in sync if the
# bundled packages are renamed or new ones are added.
_SIBLING_LOGGER_PREFIXES = (
    "nhp_skullstrip_nn",
    "fastsurfer_nn",
    "fastsurfer_surfrecon",
)

# Central application logger; handlers are attached by setup_logging().
_LOGGER = logging.getLogger("nhp_mri_prep")
_LOGGER.setLevel(logging.WARNING)  # Default to WARNING level until setup_logging()


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
        return "INFO"  # Normal mode - standard information
    else:  # verbose == 2
        return "DEBUG"  # Verbose mode - show everything


def _quiet_sibling_package_loggers() -> None:
    """Remove stray handlers on sibling packages (avoids duplicate/ms lines in Jupyter)."""
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if not name or name == "nhp_mri_prep" or name.startswith("nhp_mri_prep."):
            continue
        if not any(name.startswith(prefix) for prefix in _SIBLING_LOGGER_PREFIXES):
            continue
        log = logging.getLogger(name)
        log.handlers.clear()
        log.propagate = False


def _build_handlers(
    level: Union[str, int],
    format_str: str,
    log_file: Optional[Union[str, Path]] = None,
    file_required: bool = False,
) -> list:
    """Build a console handler plus an optional file handler sharing one format.

    Centralizes the handler-creation boilerplate used by the ``setup_*``
    functions so the console/file formatters and level stay consistent.

    Args:
        level: Level applied to every handler (string name or int).
        format_str: Format string for log messages (timestamps use LOG_DATEFMT).
        log_file: If given, also create a FileHandler for this path. Parent
            directories are created as needed.
        file_required: If True, failing to create the file handler is fatal and
            raises RuntimeError. If False, the failure is reported to stderr and
            only the console handler is returned.

    Returns:
        List of handlers (console first, file second if it was created).

    Raises:
        RuntimeError: If ``file_required`` is True and the file handler cannot
            be created.
    """
    # A single Formatter instance is safe to share across handlers — formatters
    # are stateless. LOG_DATEFMT keeps timestamps free of milliseconds.
    formatter = logging.Formatter(format_str, datefmt=LOG_DATEFMT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    handlers = [console_handler]

    if log_file is not None:
        log_file = Path(log_file)
        try:
            # parent is "." for a bare filename, so this is always safe.
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            handlers.append(file_handler)
        except Exception as e:
            if file_required:
                error_msg = f"CRITICAL: Failed to create log file {log_file}: {e}"
                print(error_msg, file=sys.stderr)
                raise RuntimeError(error_msg)
            print(
                f"Warning: Failed to setup file logging to {log_file}: {e}",
                file=sys.stderr,
            )

    return handlers


def setup_logging(
    log_file: Optional[str] = None,
    level: Union[str, int] = logging.INFO,
    name: str = "nhp_mri_prep",
    format_str: str = LOG_FORMAT,
    quiet_root: bool = True,
) -> None:
    """Set up main application logging configuration.

    This function should be called once at the start of your program.
    After calling this, use get_logger() to get logger instances.

    Args:
        log_file: Optional path to main application log file. If not provided, logs to console only.
        level: Logging level (string or int). If string, must be one of:
            'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        name: Name of the logger (default: "nhp_mri_prep")
        format_str: Format string for log messages
        quiet_root: If True (default), remove handlers from the root logger so
            Jupyter/IPython or a prior ``basicConfig`` call cannot duplicate
            ``nhp_mri_prep`` log lines.
    """
    global _LOGGER

    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper())

    if quiet_root:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        _quiet_sibling_package_loggers()

    # File handler failure is non-fatal here: console logging still works.
    handlers = _build_handlers(level, format_str, log_file, file_required=False)

    # Configure the central logger (do not propagate to root — avoids duplicate lines
    # when the host app or Jupyter also configures root logging).
    _LOGGER.setLevel(level)
    _LOGGER.handlers = []  # Clear existing handlers
    _LOGGER.propagate = False
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
    format_str: str = LOG_FORMAT,
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
    step_logger = logging.getLogger(f"nhp_mri_prep.step.{step_name}")
    step_logger.setLevel(level)

    # Don't propagate to parent logger to avoid duplicate messages
    # Set this BEFORE adding handlers to ensure no propagation happens
    step_logger.propagate = False

    # Clear any existing handlers to avoid duplicates
    step_logger.handlers.clear()

    # File handler is mandatory for step logs: failure to create it is fatal.
    log_file = logs_dir / f"{step_name}.log"
    for handler in _build_handlers(level, format_str, log_file, file_required=True):
        step_logger.addHandler(handler)

    # Log initialization to confirm logging is working
    step_logger.info(f"Step logging initialized: {log_file}")
    step_logger.info(f"Step name: {step_name}")
    step_logger.info(f"Logging level: {logging.getLevelName(level)}")

    return step_logger


def setup_workflow_logging(
    workflow_dir: Union[str, Path],
    workflow_name: str,
    level: Union[str, int] = logging.INFO,
    format_str: str = LOG_FORMAT,
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
    workflow_logger = logging.getLogger(f"nhp_mri_prep.{workflow_name}")
    workflow_logger.setLevel(level)

    # Don't propagate to parent logger to avoid duplicate messages
    # Set this BEFORE adding handlers to ensure no propagation happens
    workflow_logger.propagate = False

    # Clear any existing handlers to avoid duplicates
    workflow_logger.handlers.clear()

    # File handler is mandatory for workflow logs: failure to create it is fatal.
    log_file = workflow_dir / "workflow.log"
    for handler in _build_handlers(level, format_str, log_file, file_required=True):
        workflow_logger.addHandler(handler)

    # Log initialization to confirm logging is working
    workflow_logger.info(f"Workflow logging initialized: {log_file}")
    workflow_logger.info(f"Workflow name: {workflow_name}")
    workflow_logger.info(f"Logging level: {logging.getLevelName(level)}")

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
        with open(log_file, "a"):
            pass
        # Check if file has content (at least some logging was written)
        file_size = log_file.stat().st_size
        if file_size > 0:
            return True
        return False
    except Exception:
        return False


def log_workflow_start(
    workflow_logger: logging.Logger, workflow_name: str, config: dict
) -> None:
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


def log_workflow_end(
    workflow_logger: logging.Logger,
    workflow_name: str,
    success: bool,
    duration: float = None,
) -> None:
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


def log_step_end(
    step_logger: logging.Logger,
    step_name: str,
    success: bool,
    outputs: dict = None,
    duration: float = None,
) -> None:
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
