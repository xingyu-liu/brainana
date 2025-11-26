"""
FreeSurfer mri_* command wrappers.

Provides Python interfaces to FreeSurfer mri_* tools.
"""

from pathlib import Path
from typing import Optional
import logging

from .base import run_fs_command, FreeSurferError

logger = logging.getLogger(__name__)


def mri_convert(
    input_file: Path,
    output_file: Path,
    log_file: Optional[Path] = None,
    **kwargs,
) -> Path:
    """
    Convert image between formats using mri_convert.

    Parameters
    ----------
    input_file : Path
        Input image file
    output_file : Path
        Output image file
    log_file : Path, optional
        Log file path
    **kwargs
        Additional mri_convert arguments (e.g., --conform, --vox-size)

    Returns
    -------
    Path
        Output file path
    """
    cmd = ["mri_convert", str(input_file), str(output_file)]
    
    # Add optional arguments
    for key, value in kwargs.items():
        if value is True:
            cmd.append(f"--{key.replace('_', '-')}")
        elif value is not False and value is not None:
            cmd.append(f"--{key.replace('_', '-')}")
            cmd.append(str(value))
    
    run_fs_command(cmd, log_file=log_file)
    return output_file


def mri_pretess(
    input_vol: Path,
    label: int,
    norm: Path,
    output_vol: Path,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Pretessellate volume before marching cubes.

    Parameters
    ----------
    input_vol : Path
        Input volume (e.g., filled.mgz)
    label : int
        Label value (255 for lh, 127 for rh)
    norm : Path
        Normalized volume (e.g., brain.mgz)
    output_vol : Path
        Output pretessellated volume
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output file path
    """
    cmd = [
        "mri_pretess",
        str(input_vol),
        str(label),
        str(norm),
        str(output_vol),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_vol


def mri_mc(
    input_vol: Path,
    label: int,
    output_surf: Path,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Extract surface using marching cubes.

    Parameters
    ----------
    input_vol : Path
        Input volume (pretessellated)
    label : int
        Label value to extract (255 for lh, 127 for rh)
    output_surf : Path
        Output surface file
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output surface path
    """
    cmd = [
        "mri_mc",
        str(input_vol),
        str(label),
        str(output_surf),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_surf


def mri_mask(
    input_vol: Path,
    mask: Path,
    output_vol: Path,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Apply mask to volume.

    Parameters
    ----------
    input_vol : Path
        Input volume
    mask : Path
        Mask volume
    output_vol : Path
        Masked output volume
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output file path
    """
    cmd = [
        "mri_mask",
        str(input_vol),
        str(mask),
        str(output_vol),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_vol


def mri_normalize(
    input_vol: Path,
    output_vol: Path,
    aseg: Optional[Path] = None,
    log_file: Optional[Path] = None,
    **kwargs,
) -> Path:
    """
    Normalize volume intensity.

    Parameters
    ----------
    input_vol : Path
        Input volume (e.g., nu.mgz)
    output_vol : Path
        Output normalized volume (e.g., T1.mgz)
    aseg : Path, optional
        Aseg segmentation for better normalization
    log_file : Path, optional
        Log file path
    **kwargs
        Additional arguments (e.g., -g, -seed, -mprage)

    Returns
    -------
    Path
        Output file path
    """
    cmd = ["mri_normalize"]
    
    # Common flags
    if "-g" not in kwargs and "g" not in kwargs:
        cmd.extend(["-g", "1"])
    if "-seed" not in kwargs and "seed" not in kwargs:
        cmd.extend(["-seed", "1234"])
    if "-mprage" not in kwargs and "mprage" not in kwargs:
        cmd.append("-mprage")
    
    # Add optional aseg
    if aseg:
        cmd.extend(["-aseg", str(aseg)])
    
    # Add other kwargs
    for key, value in kwargs.items():
        if key.startswith("-"):
            cmd.append(key)
            if value is not True:
                cmd.append(str(value))
        else:
            cmd.append(f"-{key.replace('_', '-')}")
            if value is not True:
                cmd.append(str(value))
    
    cmd.extend([str(input_vol), str(output_vol)])
    run_fs_command(cmd, log_file=log_file)
    return output_vol


def mri_cc(
    aseg_no_cc: Path,
    output_aseg: Path,
    output_lta: Path,
    subject: str,
    log_file: Optional[Path] = None,
) -> tuple[Path, Path]:
    """
    Segment corpus callosum.

    Parameters
    ----------
    aseg_no_cc : Path
        Input aseg without CC (e.g., aseg.auto_noCCseg.mgz)
    output_aseg : Path
        Output aseg with CC (e.g., aseg.auto.mgz)
    output_lta : Path
        Output LTA transform (e.g., cc_up.lta)
    subject : str
        Subject ID
    log_file : Path, optional
        Log file path

    Returns
    -------
    tuple[Path, Path]
        (output_aseg, output_lta)
    """
    cmd = [
        "mri_cc",
        "-aseg", str(aseg_no_cc),
        "-o", str(output_aseg),
        "-lta", str(output_lta),
        subject,
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_aseg, output_lta


def mri_surf2volseg(
    output_vol: Path,
    input_aseg: Path,
    subject: str,
    lh_annot: Optional[Path] = None,
    rh_annot: Optional[Path] = None,
    lh_cortex_mask: Optional[Path] = None,
    rh_cortex_mask: Optional[Path] = None,
    lh_white: Optional[Path] = None,
    rh_white: Optional[Path] = None,
    lh_pial: Optional[Path] = None,
    rh_pial: Optional[Path] = None,
    label_cortex: bool = False,
    label_wm: bool = False,
    lh_annot_offset: int = 1000,
    rh_annot_offset: int = 2000,
    threads: int = 1,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Map surface labels to volume segmentation.

    Parameters
    ----------
    output_vol : Path
        Output volume segmentation
    input_aseg : Path
        Input aseg segmentation
    subject : str
        Subject ID
    lh_annot : Path, optional
        Left hemisphere annotation
    rh_annot : Path, optional
        Right hemisphere annotation
    lh_cortex_mask : Path, optional
        Left cortex label
    rh_cortex_mask : Path, optional
        Right cortex label
    lh_white : Path, optional
        Left white surface
    rh_white : Path, optional
        Right white surface
    lh_pial : Path, optional
        Left pial surface
    rh_pial : Path, optional
        Right pial surface
    label_cortex : bool
        Label cortex regions
    label_wm : bool
        Label white matter regions
    lh_annot_offset : int, default=1000
        Left hemisphere annotation label offset
    rh_annot_offset : int, default=2000
        Right hemisphere annotation label offset
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output volume path
    """
    cmd = [
        "mri_surf2volseg",
        "--o", str(output_vol),
        "--i", str(input_aseg),
        "--threads", str(threads),
    ]
    
    if label_cortex:
        cmd.append("--label-cortex")
    if label_wm:
        cmd.append("--label-wm")
    
    # Left hemisphere
    if lh_annot:
        cmd.extend(["--lh-annot", str(lh_annot), str(lh_annot_offset)])
    if lh_cortex_mask:
        cmd.extend(["--lh-cortex-mask", str(lh_cortex_mask)])
    if lh_white:
        cmd.extend(["--lh-white", str(lh_white)])
    if lh_pial:
        cmd.extend(["--lh-pial", str(lh_pial)])
    
    # Right hemisphere
    if rh_annot:
        cmd.extend(["--rh-annot", str(rh_annot), str(rh_annot_offset)])
    if rh_cortex_mask:
        cmd.extend(["--rh-cortex-mask", str(rh_cortex_mask)])
    if rh_white:
        cmd.extend(["--rh-white", str(rh_white)])
    if rh_pial:
        cmd.extend(["--rh-pial", str(rh_pial)])
    
    run_fs_command(cmd, log_file=log_file)
    return output_vol


def mri_add_xform_to_header(
    xform: Path,
    input_vol: Path,
    output_vol: Path,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Add transform to volume header.

    Parameters
    ----------
    xform : Path
        Transform file (e.g., talairach.xfm)
    input_vol : Path
        Input volume
    output_vol : Path
        Output volume with transform in header
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output file path
    """
    cmd = [
        "mri_add_xform_to_header",
        "-c", str(xform),
        str(input_vol),
        str(output_vol),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_vol


__all__ = [
    "mri_convert",
    "mri_pretess",
    "mri_mc",
    "mri_mask",
    "mri_normalize",
    "mri_cc",
    "mri_surf2volseg",
    "mri_add_xform_to_header",
]

