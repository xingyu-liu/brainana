"""
System utilities for macacaMRIprep.

This module provides system-level utilities for command execution.
"""

import subprocess
import logging
import time
import shutil
from typing import List, Optional, Tuple
from .logger import get_logger

# Get logger for this module
logger = get_logger(__name__)

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