"""
FreeSurfer recon-all command wrappers.

Provides Python interfaces to recon-all stages.
"""

from pathlib import Path
from typing import Optional, Sequence
import logging

from .base import run_recon_all, FreeSurferError

logger = logging.getLogger(__name__)


def recon_all_tessellate(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all tessellation stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-tessellate", "-smooth1"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_inflate1(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all inflation stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-inflate1"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_qsphere(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all qsphere stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-qsphere"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_fix(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all topology fix stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-fix"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_autodetgwstats(
    subject: str,
    hemi: str,
    no_remesh: bool = False,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all autodetgwstats stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    no_remesh : bool
        Skip remeshing
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    if no_remesh:
        flags.append("-no-remesh")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-autodetgwstats"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_white_preaparc(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all white-preaparc stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-white-preaparc"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_cortex_label(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all cortex-label stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-cortex-label"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_smooth2_inflate2_curvHK(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all smooth2, inflate2, and curvHK stages.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-smooth2", "-inflate2", "-curvHK"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_sphere(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all sphere stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-sphere"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_jacobian_white_avgcurv(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all jacobian_white and avgcurv stages.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-jacobian_white", "-avgcurv"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_curvstats(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all curvstats stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-curvstats"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_cortribbon(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all cortribbon stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-cortribbon"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_pctsurfcon(
    subject: str,
    hemi: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all pctsurfcon stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        hemi=hemi,
        steps=["-pctsurfcon"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_hyporelabel(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all hyporelabel stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-hyporelabel"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_apas2aseg(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all apas2aseg stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-apas2aseg"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_aparc2aseg(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all aparc2aseg stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-aparc2aseg"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_wmparc(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all wmparc stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-wmparc"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_parcstats(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all parcstats stage.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-parcstats"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


def recon_all_normalization2_maskbfs_fill(
    subject: str,
    hires: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
) -> None:
    """
    Run recon-all normalization2, maskbfs, and fill stages.

    Parameters
    ----------
    subject : str
        Subject ID
    hires : bool
        High-resolution mode
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    """
    flags = []
    if hires:
        flags.append("-hires")
    
    run_recon_all(
        subject=subject,
        steps=["-normalization2", "-maskbfs", "-fill"],
        flags=flags,
        threads=threads,
        log_file=log_file,
        subjects_dir=subjects_dir,
    )


__all__ = [
    "recon_all_tessellate",
    "recon_all_inflate1",
    "recon_all_qsphere",
    "recon_all_fix",
    "recon_all_autodetgwstats",
    "recon_all_white_preaparc",
    "recon_all_cortex_label",
    "recon_all_smooth2_inflate2_curvHK",
    "recon_all_sphere",
    "recon_all_jacobian_white_avgcurv",
    "recon_all_curvstats",
    "recon_all_cortribbon",
    "recon_all_pctsurfcon",
    "recon_all_hyporelabel",
    "recon_all_apas2aseg",
    "recon_all_aparc2aseg",
    "recon_all_wmparc",
    "recon_all_parcstats",
    "recon_all_normalization2_maskbfs_fill",
]

