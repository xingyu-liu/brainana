"""
System utilities for macacaMRIprep.

This module provides system-level utilities for command execution.
"""

import os
import subprocess
import logging
import time
import shutil
from typing import List, Optional, Tuple, Dict
from .logger import get_logger

# Get logger for this module
logger = get_logger(__name__)

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
    step_logger: Optional[logging.Logger] = None
) -> Tuple[int, str, str]:
    """Run a command and return its output.
    
    Args:
        command: List of command and arguments
        cwd: Optional working directory
        env: Optional environment variables
        check: If True, raise CalledProcessError on non-zero exit
        step_logger: Optional step-specific logger for command logging
        
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
    
    # Log additional execution context
    if cwd:
        cmd_logger.info(f"System: working directory - {cwd}")
    if env:
        # Only log non-standard environment variables (avoid logging entire environment)
        cmd_logger.debug(f"System: environment variables - {env}")
    
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