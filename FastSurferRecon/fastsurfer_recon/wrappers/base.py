"""
Base utilities for FreeSurfer command wrappers.

Provides subprocess execution with logging, error handling,
and environment management.
"""

import subprocess
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Sequence, Any

logger = logging.getLogger(__name__)

# Global cmd log file path (set by pipeline)
_cmd_log_file: Optional[Path] = None


def set_cmd_log_file(cmd_log_file: Optional[Path]) -> None:
    """Set the global cmd log file path for command logging."""
    global _cmd_log_file
    _cmd_log_file = cmd_log_file


def get_cmd_log_file() -> Optional[Path]:
    """Get the global cmd log file path."""
    return _cmd_log_file


class FreeSurferError(Exception):
    """
    Exception raised when a FreeSurfer command fails.
    
    Attributes
    ----------
    cmd : str, optional
        The command that failed
    returncode : int, optional
        The exit code of the failed command
    """
    
    def __init__(self, message: str, cmd: Optional[str] = None, returncode: Optional[int] = None):
        self.cmd = cmd
        self.returncode = returncode
        super().__init__(message)


def get_fs_home() -> Path:
    """
    Get FreeSurfer home directory from environment.
    
    Returns
    -------
    Path
        Path to FREESURFER_HOME
        
    Raises
    ------
    FreeSurferError
        If FREESURFER_HOME is not set or doesn't exist
    """
    fs_home = os.environ.get("FREESURFER_HOME")
    if not fs_home:
        raise FreeSurferError(
            "FREESURFER_HOME environment variable not set. "
            "Please source FreeSurfer's SetUpFreeSurfer.sh"
        )
    
    fs_path = Path(fs_home)
    if not fs_path.exists():
        raise FreeSurferError(f"FREESURFER_HOME does not exist: {fs_path}")
    
    return fs_path


def find_command(cmd: str) -> str:
    """
    Find a command, checking if it's available.
    
    Parameters
    ----------
    cmd : str
        Command name
        
    Returns
    -------
    str
        Full path to command or just the command name if in PATH
        
    Raises
    ------
    FreeSurferError
        If command is not found
    """
    path = shutil.which(cmd)
    if path is None:
        raise FreeSurferError(f"Command not found: {cmd}")
    return path


def to_relative_path(path: Path, subject_dir: Path) -> Path:
    """
    Convert absolute path to relative path from subject_dir if under it.
    
    Parameters
    ----------
    path : Path
        Path to convert (can be absolute or relative)
    subject_dir : Path
        Subject directory (e.g., /path/to/subject)
        
    Returns
    -------
    Path
        Relative path from subject_dir if path is under it, otherwise original path
    """
    if path.is_absolute():
        try:
            return path.relative_to(subject_dir)
        except ValueError:
            # Path is not under subject_dir, keep absolute
            return path
    return path


def run_fs_command(
    cmd: Sequence[str | Path],
    log_file: Optional[Path] = None,
    cmd_log_file: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """
    Run a FreeSurfer command.
    
    Parameters
    ----------
    cmd : sequence of str or Path
        Command and arguments
    log_file : Path, optional
        File to append output to
    cmd_log_file : Path, optional
        File to log command (fastsurfer_recon.cmd format). Logs command with timestamp.
    env : dict, optional
        Additional environment variables (merged with os.environ)
    cwd : Path, optional
        Working directory (overridden by subject_dir if provided)
    subject_dir : Path, optional
        Subject directory. If provided, uses subject_dir as working directory.
        This enables recon-all style logging with cd commands. Paths should already
        be converted to relative from subject_dir by wrapper functions.
    check : bool, default=True
        Raise exception on non-zero exit code
    capture_output : bool, default=True
        Capture stdout and stderr
    timeout : float, optional
        Timeout in seconds
        
    Returns
    -------
    subprocess.CompletedProcess
        Completed process information
        
    Raises
    ------
    FreeSurferError
        If command fails and check=True
    """
    # Convert all arguments to strings
    cmd_list = [str(c) for c in cmd]
    cmd_str = " ".join(cmd_list)
    
    # Resolve subject_dir if provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
    
    # Merge environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    
    # Ensure FREESURFER_HOME is set
    if "FREESURFER_HOME" not in run_env:
        raise FreeSurferError(
            "FREESURFER_HOME not set. Cannot run FreeSurfer commands."
        )
    
    logger.debug(f"Running: {cmd_str}")
    
    # Log command to cmd log file (fastsurfer_recon.cmd format)
    # Use provided cmd_log_file or global one
    active_cmd_log_file = cmd_log_file or _cmd_log_file
    if active_cmd_log_file:
        from datetime import datetime  # Import here to avoid circular dependency
        active_cmd_log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(active_cmd_log_file, "a") as f:
            timestamp = datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y")
            f.write(f"\n#--------------------------------------------\n")
            f.write(f"#@# {cmd_list[0]} {timestamp}\n")
            # Log cd command if using subject_dir (recon-all style)
            if subject_dir:
                f.write(f"cd {subject_dir}\n")
            f.write(f"{' '.join(cmd_list)}\n")
    
    try:
        result = subprocess.run(
            cmd_list,
            env=run_env,
            cwd=subject_dir if subject_dir else cwd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise FreeSurferError(
            f"Command timed out after {timeout}s: {cmd_str}",
            cmd=cmd_str,
        ) from e
    except FileNotFoundError as e:
        raise FreeSurferError(
            f"Command not found: {cmd_list[0]}",
            cmd=cmd_str,
        ) from e
    
    # Log output
    if log_file and capture_output:
        with open(log_file, "a") as f:
            f.write(f"\n$ {cmd_str}\n")
            if result.stdout:
                f.write(result.stdout)
            if result.stderr:
                f.write(f"[stderr]\n{result.stderr}")
            f.write(f"[exit code: {result.returncode}]\n")
    
    # Check for errors
    if check and result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise FreeSurferError(
            f"Command failed with exit code {result.returncode}: {cmd_str}\n{error_msg}",
            cmd=cmd_str,
            returncode=result.returncode,
        )
    
    return result


def run_recon_all(
    subject: str,
    hemi: Optional[str] = None,
    steps: Optional[Sequence[str]] = None,
    flags: Optional[Sequence[str]] = None,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """
    Run recon-all with specified steps.
    
    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str, optional
        Hemisphere ('lh' or 'rh')
    steps : sequence of str, optional
        recon-all steps to run (e.g., ['-inflate1', '-qsphere'])
    flags : sequence of str, optional
        Additional flags (e.g., ['-hires', '-no-isrunning'])
    threads : int, default=1
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    **kwargs
        Additional arguments to run_fs_command
        
    Returns
    -------
    subprocess.CompletedProcess
    """
    cmd = ["recon-all", "-s", subject]
    
    if hemi:
        cmd.extend(["-hemi", hemi])
    
    if steps:
        cmd.extend(steps)
    
    if flags:
        cmd.extend(flags)
    
    # Threading
    if threads > 1:
        cmd.extend(["-threads", str(threads), "-itkthreads", str(threads)])
    
    # Standard flags
    cmd.extend(["-no-isrunning", "-umask", "022"])
    
    # Set SUBJECTS_DIR in environment
    env = kwargs.pop("env", {})
    if subjects_dir:
        # Always use provided subjects_dir, overriding any in env
        env["SUBJECTS_DIR"] = str(subjects_dir)
    elif "SUBJECTS_DIR" not in env:
        # Try to get from environment if not provided and not in env
        env["SUBJECTS_DIR"] = os.environ.get("SUBJECTS_DIR", "")
    
    return run_fs_command(cmd, log_file=log_file, env=env, **kwargs)

