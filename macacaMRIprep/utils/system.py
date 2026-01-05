"""
System utilities for macacaMRIprep.

This module provides system-level utilities for command execution.
"""

import os
import subprocess
import logging
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Union
from .logger import get_logger

# Get logger for this module
logger = get_logger(__name__)

# Global command log file path (set by pipeline/workflow)
_cmd_log_file: Optional[Path] = None

# Global job/step context for command logging
_cmd_log_context: Optional[Dict[str, str]] = None

def set_cmd_log_file(cmd_log_file: Optional[Path]) -> None:
    """Set the global command log file path for command logging.
    
    Args:
        cmd_log_file: Path to command log file, or None to disable command logging
    """
    global _cmd_log_file
    _cmd_log_file = cmd_log_file

def get_cmd_log_file() -> Optional[Path]:
    """Get the global command log file path.
    
    Returns:
        Path to command log file, or None if not set
    """
    return _cmd_log_file

def set_cmd_log_context(job_id: Optional[str] = None, step_name: Optional[str] = None, 
                        subject_id: Optional[str] = None, session_id: Optional[str] = None,
                        task: Optional[str] = None, run: Optional[str] = None) -> None:
    """Set the global job/step context for command logging.
    
    This context will be included in all command log entries to identify which
    job and step executed each command.
    
    Args:
        job_id: Job identifier (e.g., "sub-001_ses-01")
        step_name: Step/process name (e.g., "ANAT_REGISTRATION")
        subject_id: Subject ID (e.g., "001")
        session_id: Session ID (e.g., "01")
        task: Task name (for functional data)
        run: Run number (for functional data)
    """
    global _cmd_log_context
    context = {}
    if job_id:
        context['job_id'] = job_id
    if step_name:
        context['step'] = step_name
    if subject_id:
        context['subject'] = subject_id
    if session_id:
        context['session'] = session_id
    if task:
        context['task'] = task
    if run:
        context['run'] = run
    _cmd_log_context = context if context else None

def get_cmd_log_context() -> Optional[Dict[str, str]]:
    """Get the current command log context.
    
    Returns:
        Dictionary with job/step context, or None if not set
    """
    return _cmd_log_context

# Global configuration for command log rotation
_cmd_log_max_size_mb: float = 20.0  # Default: 100 MB
_cmd_log_max_files: int = 5  # Keep up to 5 rotated files
_cmd_log_compress: bool = True  # Compress old log files

def set_cmd_log_rotation_config(max_size_mb: float = 100.0, max_files: int = 5, compress: bool = True) -> None:
    """Configure command log rotation settings.
    
    Args:
        max_size_mb: Maximum log file size in MB before rotation (default: 100.0)
        max_files: Maximum number of rotated log files to keep (default: 5)
        compress: Whether to compress old log files with gzip (default: True)
    """
    global _cmd_log_max_size_mb, _cmd_log_max_files, _cmd_log_compress
    _cmd_log_max_size_mb = max_size_mb
    _cmd_log_max_files = max_files
    _cmd_log_compress = compress

def _rotate_cmd_log_file(log_file: Path) -> Path:
    """Rotate command log file if it exceeds size limit.
    
    This function checks if the log file exceeds the size limit and rotates it
    if necessary. Old logs are numbered (commands.log.1, commands.log.2, etc.)
    and optionally compressed.
    
    Args:
        log_file: Path to the command log file
        
    Returns:
        Path to the current log file (may be rotated)
    """
    if not log_file.exists():
        return log_file
    
    max_size_bytes = _cmd_log_max_size_mb * 1024 * 1024
    current_size = log_file.stat().st_size
    
    # If file is under size limit, no rotation needed
    if current_size < max_size_bytes:
        return log_file
    
    logger.info(f"Command log file size ({current_size / 1024 / 1024:.1f} MB) exceeds limit ({_cmd_log_max_size_mb} MB). Rotating...")
    
    # Compress and remove the oldest log if we've reached max_files
    # First, find all existing rotated logs
    rotated_logs = []
    for i in range(1, _cmd_log_max_files + 1):
        rotated_path = log_file.parent / f"{log_file.name}.{i}"
        if rotated_path.exists():
            rotated_logs.append((i, rotated_path))
        # Also check for compressed versions
        compressed_path = log_file.parent / f"{log_file.name}.{i}.gz"
        if compressed_path.exists():
            rotated_logs.append((i, compressed_path))
    
    # Remove oldest if we've reached max_files
    if len(rotated_logs) >= _cmd_log_max_files:
        # Find the highest numbered log (oldest)
        oldest_num = max(i for i, _ in rotated_logs)
        oldest_path = log_file.parent / f"{log_file.name}.{oldest_num}"
        oldest_compressed = log_file.parent / f"{log_file.name}.{oldest_num}.gz"
        if oldest_compressed.exists():
            oldest_compressed.unlink()
            logger.debug(f"Removed oldest rotated log: {oldest_compressed}")
        elif oldest_path.exists():
            oldest_path.unlink()
            logger.debug(f"Removed oldest rotated log: {oldest_path}")
    
    # Shift existing rotated logs
    for i in range(_cmd_log_max_files - 1, 0, -1):
        old_path = log_file.parent / f"{log_file.name}.{i}"
        old_compressed = log_file.parent / f"{log_file.name}.{i}.gz"
        new_path = log_file.parent / f"{log_file.name}.{i + 1}"
        new_compressed = log_file.parent / f"{log_file.name}.{i + 1}.gz"
        
        # Move compressed files
        if old_compressed.exists():
            old_compressed.rename(new_compressed)
        # Move uncompressed files
        elif old_path.exists():
            if _cmd_log_compress:
                # Compress before moving
                try:
                    import gzip
                    with open(old_path, 'rb') as f_in:
                        with gzip.open(new_compressed, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    old_path.unlink()
                    logger.debug(f"Compressed and rotated: {old_path} -> {new_compressed}")
                except Exception as e:
                    logger.warning(f"Failed to compress {old_path}, moving uncompressed: {e}")
                    old_path.rename(new_path)
            else:
                old_path.rename(new_path)
    
    # Rotate current log file
    new_rotated = log_file.parent / f"{log_file.name}.1"
    if _cmd_log_compress:
        try:
            import gzip
            with open(log_file, 'rb') as f_in:
                with gzip.open(log_file.parent / f"{log_file.name}.1.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            log_file.unlink()
            logger.info(f"Rotated and compressed command log: {log_file.name} -> {log_file.name}.1.gz")
        except Exception as e:
            logger.warning(f"Failed to compress during rotation, keeping uncompressed: {e}")
            log_file.rename(new_rotated)
    else:
        log_file.rename(new_rotated)
        logger.info(f"Rotated command log: {log_file.name} -> {log_file.name}.1")
    
    # Create new log file with header
    try:
        from datetime import datetime
        with open(log_file, 'w') as f:
            f.write(f"# Command log file for macacaMRIprep (rotated)\n")
            f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Previous log rotated due to size limit ({_cmd_log_max_size_mb} MB)\n")
            f.write(f"#--------------------------------------------\n\n")
    except Exception as e:
        logger.warning(f"Failed to create new log file after rotation: {e}")
    
    return log_file

def init_cmd_log_file(output_dir: Optional[Union[str, Path]] = None,
                      job_id: Optional[str] = None,
                      step_name: Optional[str] = None,
                      subject_id: Optional[str] = None,
                      session_id: Optional[str] = None,
                      task: Optional[str] = None,
                      run: Optional[str] = None,
                      max_size_mb: Optional[float] = None,
                      max_files: Optional[int] = None,
                      compress: Optional[bool] = None) -> Optional[Path]:
    """Initialize command log file in output_dir/reports/commands.log.
    
    This function sets up automatic command logging to a file. If output_dir
    is provided, it creates the command log file at output_dir/reports/commands.log.
    If output_dir is None, it checks the OUTPUT_DIR environment variable.
    
    Log rotation is automatically enabled to prevent log files from growing too large.
    When the log file exceeds the size limit, it is rotated to commands.log.1,
    commands.log.2, etc., and optionally compressed.
    
    Args:
        output_dir: Optional output directory path. If None, reads from OUTPUT_DIR env var.
        job_id: Job identifier (e.g., "sub-001_ses-01")
        step_name: Step/process name (e.g., "ANAT_REGISTRATION")
        subject_id: Subject ID (e.g., "001")
        session_id: Session ID (e.g., "01")
        task: Task name (for functional data)
        run: Run number (for functional data)
        max_size_mb: Maximum log file size in MB before rotation (default: 100.0, can be set globally)
        max_files: Maximum number of rotated log files to keep (default: 5, can be set globally)
        compress: Whether to compress old log files (default: True, can be set globally)
        
    Returns:
        Path to command log file, or None if output_dir is not available
    """
    if output_dir is None:
        output_dir = os.environ.get('OUTPUT_DIR')
    
    if not output_dir:
        return None
    
    # Update rotation config if provided
    if max_size_mb is not None or max_files is not None or compress is not None:
        set_cmd_log_rotation_config(
            max_size_mb=max_size_mb if max_size_mb is not None else _cmd_log_max_size_mb,
            max_files=max_files if max_files is not None else _cmd_log_max_files,
            compress=compress if compress is not None else _cmd_log_compress
        )
    
    output_dir = Path(output_dir)
    reports_dir = output_dir / 'nextflow_reports'
    cmd_log_file = reports_dir / 'commands.log'
    
    # Create reports directory if it doesn't exist
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create reports directory {reports_dir}: {e}")
        return None
    
    # Check if rotation is needed before initializing
    if cmd_log_file.exists():
        cmd_log_file = _rotate_cmd_log_file(cmd_log_file)
    
    # Initialize command log file with header if it's new
    if not cmd_log_file.exists():
        try:
            from datetime import datetime
            with open(cmd_log_file, 'w') as f:
                f.write(f"# Command log file for macacaMRIprep\n")
                f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Output directory: {output_dir}\n")
                f.write(f"# Max size: {_cmd_log_max_size_mb} MB (auto-rotation enabled)\n")
                f.write(f"# Max rotated files: {_cmd_log_max_files}\n")
                f.write(f"# Compression: {'enabled' if _cmd_log_compress else 'disabled'}\n")
                f.write(f"#--------------------------------------------\n\n")
        except Exception as e:
            logger.warning(f"Failed to initialize command log file {cmd_log_file}: {e}")
            return None
    
    # Set the global command log file
    set_cmd_log_file(cmd_log_file)
    
    # Set job/step context if provided
    if job_id or step_name or subject_id or session_id or task or run:
        set_cmd_log_context(job_id=job_id, step_name=step_name, 
                           subject_id=subject_id, session_id=session_id,
                           task=task, run=run)
    
    logger.info(f"Command log file initialized: {cmd_log_file} (max size: {_cmd_log_max_size_mb} MB)")
    
    return cmd_log_file

def _get_numerical_thread_env_vars(threads: int, max_threads: int = 32, include_itk: bool = True) -> tuple[Dict[str, str], int]:
    """
    Get environment variables for numerical library threading.
    
    Core helper function that creates a dictionary of environment variables
    for controlling thread usage in numerical computing libraries.
    
    Args:
        threads: Number of threads to use (will be capped at max_threads)
        max_threads: Maximum allowed threads (default: 32)
        include_itk: If True, include ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS (default: True)
        
    Returns:
        Tuple of (environment variables dict, actual number of threads after capping)
    """
    num_threads = min(threads, max_threads)
    num_threads_str = str(num_threads)
    
    env_vars = {
        'OMP_NUM_THREADS': num_threads_str,
        'MKL_NUM_THREADS': num_threads_str,
        'NUMEXPR_NUM_THREADS': num_threads_str,
        'OPENBLAS_NUM_THREADS': num_threads_str,
    }
    
    if include_itk:
        env_vars['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = num_threads_str
    
    return env_vars, num_threads


def set_numerical_threads(
    threads: int, 
    max_threads: int = 32, 
    include_itk: bool = False,
    return_dict: bool = False
) -> int | Dict[str, str]:
    """
    Set environment variables to limit threading for numerical computing libraries.
    
    This function sets environment variables that control thread usage in:
    - OpenMP (OMP_NUM_THREADS) - used by many numerical libraries
    - Intel MKL (MKL_NUM_THREADS) - linear algebra library
    - NumExpr (NUMEXPR_NUM_THREADS) - numerical expression evaluator
    - OpenBLAS (OPENBLAS_NUM_THREADS) - linear algebra library
    - ITK (ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS, optional) - image processing
    
    This is critical because numerical operations can use all available CPU cores
    by default, making the system unresponsive. Setting these environment variables
    limits thread usage.
    
    Args:
        threads: Number of threads to use (will be capped at max_threads)
        max_threads: Maximum allowed threads to prevent excessive resource usage (default: 32)
        include_itk: If True, also set ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS (default: False)
        return_dict: If True, return dict for subprocess execution instead of setting os.environ (default: False)
        
    Returns:
        If return_dict=False: The actual number of threads set (after capping)
        If return_dict=True: Dictionary of environment variables (includes current os.environ)
        
    Examples:
        >>> set_numerical_threads(8)  # Sets os.environ, returns 8
        8
        >>> set_numerical_threads(100)  # Will be capped at 32
        32
        >>> set_numerical_threads(4, include_itk=True)  # Also sets ITK threads
        4
        >>> env = set_numerical_threads(8, include_itk=True, return_dict=True)  # Returns dict for subprocess
        >>> # env can be passed to subprocess.run(env=env)
    """
    env_vars, num_threads = _get_numerical_thread_env_vars(threads, max_threads, include_itk)
    
    if return_dict:
        # Return dict for subprocess execution (includes current environment)
        env = os.environ.copy()
        env.update(env_vars)
        return env
    else:
        # Set os.environ directly for in-process use
        for key, value in env_vars.items():
            os.environ[key] = value
        logger.debug(f"Set numerical threads to {num_threads} (requested {threads})")
        return num_threads


def check_dependency(command: str, step_logger: Optional[logging.Logger] = None) -> bool:
    """Check if a command/dependency is available on the system.
    
    Args:
        command: Command to check (e.g., '3dTshift', 'fsl', 'antsRegistration')
        step_logger: Optional step-specific logger
        
    Returns:
        True if command is available, False otherwise
    """
    cmd_logger = step_logger if step_logger else logger
    
    # Check if command is available using shutil.which
    if shutil.which(command):
        cmd_logger.debug(f"System: dependency check passed - {command} is available")
        return True
    
    # Try a simple command execution as fallback
    try:
        result = subprocess.run(
            [command, '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )
        available = result.returncode in [0, 1]  # Some commands return 1 for --help
        if available:
            cmd_logger.debug(f"System: dependency check passed - {command} is available")
        else:
            cmd_logger.debug(f"System: dependency check failed - {command} not available")
        return available
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        cmd_logger.debug(f"System: dependency check failed - {command} not available")
        return False

def run_command(
    command: List[str],
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    shell: bool = False,
    check: bool = True,
    step_logger: Optional[logging.Logger] = None,
    cmd_log_file: Optional[Path] = None
) -> Tuple[int, str, str]:
    """Run a command and return its output.
    
    Args:
        command: List of command and arguments
        cwd: Optional working directory
        env: Optional environment variables
        check: If True, raise CalledProcessError on non-zero exit
        step_logger: Optional step-specific logger for command logging
        cmd_log_file: Optional command log file path (overrides global setting)
        
    Returns:
        Tuple of (returncode, stdout, stderr)
        
    Raises:
        subprocess.CalledProcessError: If check=True and command fails
    """
    # Use step logger if provided, otherwise use module logger
    cmd_logger = step_logger if step_logger else logger
    
    # Log the exact command being executed
    command_str = ' '.join(command)
    cmd_logger.info(f"System: executing command - {command_str}")
    
    # Write command to command log file if enabled
    active_cmd_log_file = cmd_log_file or _cmd_log_file
    if active_cmd_log_file:
        try:
            active_cmd_log_file = Path(active_cmd_log_file)
            active_cmd_log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if rotation is needed before writing
            if active_cmd_log_file.exists():
                active_cmd_log_file = _rotate_cmd_log_file(active_cmd_log_file)
            
            with open(active_cmd_log_file, "a") as f:
                timestamp = datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y")
                f.write(f"\n#--------------------------------------------\n")
                
                # Build context string
                context_parts = []
                if _cmd_log_context:
                    if _cmd_log_context.get('step'):
                        context_parts.append(f"step={_cmd_log_context['step']}")
                    if _cmd_log_context.get('subject'):
                        sub = _cmd_log_context['subject']
                        ses = _cmd_log_context.get('session')
                        if ses:
                            context_parts.append(f"sub-{sub}_ses-{ses}")
                        else:
                            context_parts.append(f"sub-{sub}")
                    elif _cmd_log_context.get('job_id'):
                        context_parts.append(_cmd_log_context['job_id'])
                    if _cmd_log_context.get('task'):
                        context_parts.append(f"task-{_cmd_log_context['task']}")
                    if _cmd_log_context.get('run'):
                        context_parts.append(f"run-{_cmd_log_context['run']}")
                
                # Write header with context
                if context_parts:
                    context_str = " | ".join(context_parts)
                    f.write(f"#@# {command[0]} {timestamp} | {context_str}\n")
                else:
                    f.write(f"#@# {command[0]} {timestamp}\n")
                
                if cwd:
                    f.write(f"cd {cwd}\n")
                f.write(f"{command_str}\n")
        except Exception as e:
            # Don't fail command execution if log file write fails
            cmd_logger.warning(f"Failed to write to command log file {active_cmd_log_file}: {e}")
    
    # Log additional execution context
    if cwd:
        cmd_logger.info(f"System: working directory - {cwd}")
    # if env:
    #     # Only log non-standard environment variables (avoid logging entire environment)
    #     cmd_logger.debug(f"System: environment variables - {env}")
    
    # Record start time
    start_time = time.time()
    
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            shell=shell,
            check=check,
            capture_output=True,
            text=True
        )
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Log successful execution
        cmd_logger.info(f"System: command completed - exit code {result.returncode}, duration {execution_time:.2f}s")
        
        # Log stdout/stderr if present (but truncate if very long)
        if result.stdout:
            stdout_preview = result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout
            cmd_logger.debug(f"System: stdout - {stdout_preview}")
        if result.stderr:
            stderr_preview = result.stderr[:500] + "..." if len(result.stderr) > 500 else result.stderr
            cmd_logger.debug(f"System: stderr - {stderr_preview}")
            
        return result.returncode, result.stdout, result.stderr
        
    except subprocess.CalledProcessError as e:
        # Calculate execution time even for failed commands
        execution_time = time.time() - start_time
        
        # Log command failure with detailed information
        cmd_logger.error(f"System: command failed - {command_str}")
        cmd_logger.error(f"System: exit code - {e.returncode}")
        cmd_logger.error(f"System: duration - {execution_time:.2f}s")
        if cwd:
            cmd_logger.error(f"System: working directory - {cwd}")
        
        # Log error output
        if hasattr(e, 'stderr') and e.stderr:
            cmd_logger.error(f"System: stderr - {e.stderr}")
        if hasattr(e, 'stdout') and e.stdout:
            cmd_logger.error(f"System: stdout - {e.stdout}")
            
        raise 