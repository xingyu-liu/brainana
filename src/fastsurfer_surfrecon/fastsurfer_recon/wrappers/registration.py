"""
FreeSurfer registration command wrappers.

Provides Python interfaces to registration tools (talairach, lta_convert, etc.).
"""

from pathlib import Path
from typing import Optional
import logging

from .base import run_fs_command, FreeSurferError, get_fs_home

logger = logging.getLogger(__name__)


def talairach_avi(
    input_vol: Path,
    output_xfm: Path,
    atlas: str = "1.5T18yoSchwartzReactN32_as_orig",
    log_file: Optional[Path] = None,
) -> Path:
    """
    Compute Talairach registration using talairach_avi.

    Parameters
    ----------
    input_vol : Path
        Input volume (e.g., norm.mgz)
    output_xfm : Path
        Output transform file (e.g., talairach.auto.xfm)
    atlas : str, default="1.5T18yoSchwartzReactN32_as_orig"
        Atlas name (use "3T18yoSchwartzReactN32_as_orig" for 3T)
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output transform path
    """
    cmd = [
        "talairach_avi",
        "--i", str(input_vol),
        "--xfm", str(output_xfm),
        "--atlas", atlas,
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_xfm


def lta_convert(
    src_vol: Path,
    trg_vol: Path,
    input_xfm: Path,
    output_lta: Path,
    subject: str = "fsaverage",
    ltavox2vox: bool = True,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Convert transform between formats using lta_convert.

    Parameters
    ----------
    src_vol : Path
        Source volume
    trg_vol : Path
        Target volume
    input_xfm : Path
        Input transform (.xfm file)
    output_lta : Path
        Output LTA file
    subject : str, default="fsaverage"
        Subject name
    ltavox2vox : bool, default=True
        Use voxel-to-voxel LTA
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output LTA path
    """
    cmd = [
        "lta_convert",
        "--src", str(src_vol),
        "--trg", str(trg_vol),
        "--inxfm", str(input_xfm),
        "--outlta", str(output_lta),
        "--subject", subject,
    ]
    
    if ltavox2vox:
        cmd.append("--ltavox2vox")
    
    run_fs_command(cmd, log_file=log_file)
    return output_lta


def pctsurfcon(
    subject: str,
    hemi: Optional[str] = None,
    log_file: Optional[Path] = None,
) -> None:
    """
    Compute percent surface connectivity.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str, optional
        Hemisphere ('lh' or 'rh'). If None, processes both.
    log_file : Path, optional
        Log file path
    """
    cmd = ["pctsurfcon", "--s", subject]
    
    if hemi:
        cmd.append(f"--{hemi}-only")
    
    run_fs_command(cmd, log_file=log_file)


__all__ = [
    "talairach_avi",
    "lta_convert",
    "pctsurfcon",
]

