"""
FreeSurfer mri_* command wrappers.

Provides Python interfaces to FreeSurfer mri_* tools.
"""

from pathlib import Path
from typing import Optional
import logging

from .base import run_fs_command, to_relative_path

logger = logging.getLogger(__name__)


def mri_convert(
    input_file: Path,
    output_file: Path,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        input_file = to_relative_path(input_file, subject_dir)
        output_file = to_relative_path(output_file, subject_dir)
    
    cmd = ["mri_convert", str(input_file), str(output_file)]
    
    # Add optional arguments
    for key, value in kwargs.items():
        if value is True:
            cmd.append(f"--{key.replace('_', '-')}")
        elif value is not False and value is not None:
            cmd.append(f"--{key.replace('_', '-')}")
            cmd.append(str(value))
    
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_file


def mri_pretess(
    input_vol: Path,
    label: int,
    norm: Path,
    output_vol: Path,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        input_vol = to_relative_path(input_vol, subject_dir)
        norm = to_relative_path(norm, subject_dir)
        output_vol = to_relative_path(output_vol, subject_dir)
    
    cmd = [
        "mri_pretess",
        str(input_vol),
        str(label),
        str(norm),
        str(output_vol),
    ]
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_vol


def mri_mc(
    input_vol: Path,
    label: int,
    output_surf: Path,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        input_vol = to_relative_path(input_vol, subject_dir)
        output_surf = to_relative_path(output_surf, subject_dir)
    
    cmd = [
        "mri_mc",
        str(input_vol),
        str(label),
        str(output_surf),
    ]
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_surf


def mri_mask(
    input_vol: Path,
    mask: Path,
    output_vol: Path,
    threshold: Optional[float] = None,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    threshold : float, optional
        Threshold value for masking (e.g., -T 5)
    log_file : Path, optional
        Log file path
    subject_dir : Path, optional
        Subject directory. If provided, converts paths to relative from subject_dir.

    Returns
    -------
    Path
        Output file path
    """
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        input_vol = to_relative_path(input_vol, subject_dir)
        mask = to_relative_path(mask, subject_dir)
        output_vol = to_relative_path(output_vol, subject_dir)
    
    cmd = ["mri_mask"]
    
    if threshold is not None:
        cmd.extend(["-T", str(threshold)])
    
    cmd.extend([
        str(input_vol),
        str(mask),
        str(output_vol),
    ])
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_vol


def mri_normalize(
    input_vol: Path,
    output_vol: Path,
    aseg: Optional[Path] = None,
    mask: Optional[Path] = None,
    noconform: bool = False,
    seed: int = 1234,
    mprage: bool = True,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
    **kwargs,
) -> Path:
    """
    Normalize volume intensity.

    Parameters
    ----------
    input_vol : Path
        Input volume (e.g., nu.mgz or norm.mgz)
    output_vol : Path
        Output normalized volume (e.g., T1.mgz or brain.mgz)
    aseg : Path, optional
        Aseg segmentation for better normalization
    mask : Path, optional
        Mask volume (e.g., brainmask.mgz)
    noconform : bool, default=False
        Do not conform volume
    seed : int, default=1234
        Random seed
    mprage : bool, default=True
        Use MPRAGE normalization
    log_file : Path, optional
        Log file path
    subject_dir : Path, optional
        Subject directory. If provided, converts paths to relative from subject_dir.
    **kwargs
        Additional arguments (e.g., -g)

    Returns
    -------
    Path
        Output file path
    """
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        input_vol = to_relative_path(input_vol, subject_dir)
        output_vol = to_relative_path(output_vol, subject_dir)
        if aseg:
            aseg = to_relative_path(aseg, subject_dir)
        if mask:
            mask = to_relative_path(mask, subject_dir)
    
    cmd = ["mri_normalize"]
    
    # Common flags
    # Only add -g 1 if not explicitly disabled (g=0 means don't add it)
    g_value = None
    if "-g" not in kwargs:
        if "g" in kwargs:
            g_value = kwargs["g"]
        else:
            g_value = 1  # Default
    
    # Add -g flag only if g_value is not 0
    if g_value is not None and g_value != 0:
        cmd.extend(["-g", str(g_value)])
    
    cmd.extend(["-seed", str(seed)])
    if mprage:
        cmd.append("-mprage")
    if noconform:
        cmd.append("-noconform")
    
    # Add optional aseg
    if aseg:
        cmd.extend(["-aseg", str(aseg)])
    
    # Add optional mask
    if mask:
        cmd.extend(["-mask", str(mask)])
    
    # Add other kwargs (skip 'g' as it's already handled)
    for key, value in kwargs.items():
        if key == "g":  # Skip 'g' as it's already handled above
            continue
        if key.startswith("-"):
            cmd.append(key)
            if value is not True:
                cmd.append(str(value))
        else:
            cmd.append(f"-{key.replace('_', '-')}")
            if value is not True:
                cmd.append(str(value))
    
    cmd.extend([str(input_vol), str(output_vol)])
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_vol


def mri_cc(
    aseg_no_cc: Path,
    output_aseg: Path,
    output_lta: Path,
    subject: str,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        aseg_no_cc = to_relative_path(aseg_no_cc, subject_dir)
        output_aseg = to_relative_path(output_aseg, subject_dir)
        output_lta = to_relative_path(output_lta, subject_dir)
    
    cmd = [
        "mri_cc",
        "-aseg", str(aseg_no_cc),
        "-o", str(output_aseg),
        "-lta", str(output_lta),
        subject,
    ]
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_aseg, output_lta


def mri_surf2volseg(
    output_vol: Path,
    input_aseg: Path,
    lh_annot: Optional[Path] = None,
    rh_annot: Optional[Path] = None,
    lh_cortex_mask: Optional[Path] = None,
    rh_cortex_mask: Optional[Path] = None,
    lh_white: Optional[Path] = None,
    rh_white: Optional[Path] = None,
    lh_pial: Optional[Path] = None,
    rh_pial: Optional[Path] = None,
    ribbon: Optional[Path] = None,
    label_cortex: bool = False,
    label_wm: bool = False,
    lh_annot_offset: int = 1000,
    rh_annot_offset: int = 2000,
    threads: int = 1,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    ribbon : Path, optional
        Ribbon volume for fixing presurf aseg (--fix-presurf-with-ribbon)
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
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        output_vol = to_relative_path(output_vol, subject_dir)
        input_aseg = to_relative_path(input_aseg, subject_dir)
        if ribbon:
            ribbon = to_relative_path(ribbon, subject_dir)
        if lh_annot:
            lh_annot = to_relative_path(lh_annot, subject_dir)
        if rh_annot:
            rh_annot = to_relative_path(rh_annot, subject_dir)
        if lh_cortex_mask:
            lh_cortex_mask = to_relative_path(lh_cortex_mask, subject_dir)
        if rh_cortex_mask:
            rh_cortex_mask = to_relative_path(rh_cortex_mask, subject_dir)
        if lh_white:
            lh_white = to_relative_path(lh_white, subject_dir)
        if rh_white:
            rh_white = to_relative_path(rh_white, subject_dir)
        if lh_pial:
            lh_pial = to_relative_path(lh_pial, subject_dir)
        if rh_pial:
            rh_pial = to_relative_path(rh_pial, subject_dir)
    
    cmd = [
        "mri_surf2volseg",
        "--o", str(output_vol),
        "--i", str(input_aseg),
        "--threads", str(threads),
    ]
    
    if ribbon:
        cmd.extend(["--fix-presurf-with-ribbon", str(ribbon)])
    
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
    
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_vol


def mri_add_xform_to_header(
    xform: Path,
    input_vol: Path,
    output_vol: Path,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
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
    # Convert paths to relative if subject_dir provided
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        xform = to_relative_path(xform, subject_dir)
        input_vol = to_relative_path(input_vol, subject_dir)
        output_vol = to_relative_path(output_vol, subject_dir)
    
    cmd = [
        "mri_add_xform_to_header",
        "-c", str(xform),
        str(input_vol),
        str(output_vol),
    ]
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
    return output_vol


def mri_fill(
    wm_vol: Path,
    output_vol: Path,
    aseg: Path,
    cut_log: Optional[Path] = None,
    ctab: Optional[Path] = None,
    log_file: Optional[Path] = None,
    subject_dir: Optional[Path] = None,
) -> Path:
    """
    Fill white matter volume.

    Parameters
    ----------
    wm_vol : Path
        Input white matter volume (e.g., wm.mgz)
    output_vol : Path
        Output filled volume (e.g., filled.mgz)
    aseg : Path
        Aseg segmentation (e.g., aseg.presurf.mgz)
    cut_log : Path, optional
        Cut log file (e.g., ../scripts/ponscc.cut.log)
    ctab : Path, optional
        Color table file (e.g., SubCorticalMassLUT.txt).
        If None, uses FreeSurfer's default SubCorticalMassLUT.txt
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output file path
    """
    from .base import get_fs_home
    
    # Convert paths to relative if subject_dir provided
    # Note: ctab might be outside subject_dir (FreeSurfer home), so only convert if under subject_dir
    if subject_dir:
        subject_dir = Path(subject_dir).resolve()
        wm_vol = to_relative_path(wm_vol, subject_dir)
        output_vol = to_relative_path(output_vol, subject_dir)
        aseg = to_relative_path(aseg, subject_dir)
        if cut_log:
            cut_log = to_relative_path(cut_log, subject_dir)
        # Only convert ctab if it's under subject_dir (user-provided), not FreeSurfer home
        if ctab:
            ctab = to_relative_path(ctab, subject_dir)
    
    cmd = ["mri_fill"]
    
    # Add cut log if provided
    if cut_log:
        cmd.extend(["-a", str(cut_log)])
    
    # Add segmentation
    cmd.extend(["-segmentation", str(aseg)])
    
    # Add color table (default to FreeSurfer's SubCorticalMassLUT.txt if not provided)
    if ctab:
        cmd.extend(["-ctab", str(ctab)])
    else:
        # Use FreeSurfer's default SubCorticalMassLUT.txt
        fs_home = get_fs_home()
        default_ctab = fs_home / "SubCorticalMassLUT.txt"
        if default_ctab.exists():
            cmd.extend(["-ctab", str(default_ctab)])
        else:
            logger.warning(
                f"SubCorticalMassLUT.txt not found at {default_ctab}. "
                "mri_fill may fail without -ctab parameter."
            )
    
    cmd.extend([str(wm_vol), str(output_vol)])
    run_fs_command(cmd, log_file=log_file, subject_dir=subject_dir)
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
    "mri_fill",
]

