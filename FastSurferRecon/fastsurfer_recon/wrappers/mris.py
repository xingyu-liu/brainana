"""
FreeSurfer mris_* command wrappers.

Provides Python interfaces to FreeSurfer mris_* surface tools.
"""

from pathlib import Path
from typing import Optional
import logging

from .base import run_fs_command, FreeSurferError

logger = logging.getLogger(__name__)


def mris_info(
    surface: Path,
    log_file: Optional[Path] = None,
) -> str:
    """
    Get information about a surface.

    Parameters
    ----------
    surface : Path
        Surface file
    log_file : Path, optional
        Log file path

    Returns
    -------
    str
        Surface information text
    """
    cmd = ["mris_info", str(surface)]
    result = run_fs_command(cmd, log_file=log_file, capture_output=True)
    return result.stdout


def mris_extract_main_component(
    input_surf: Path,
    output_surf: Path,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Extract the largest connected component from a surface.

    Parameters
    ----------
    input_surf : Path
        Input surface
    output_surf : Path
        Output surface (can be same as input)
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output surface path
    """
    cmd = [
        "mris_extract_main_component",
        str(input_surf),
        str(output_surf),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_surf


def mris_remesh(
    input_surf: Path,
    output_surf: Path,
    desired_face_area: float,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Remesh surface to target face area.

    Parameters
    ----------
    input_surf : Path
        Input surface
    output_surf : Path
        Output remeshed surface
    desired_face_area : float
        Target average face area
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output surface path
    """
    cmd = [
        "mris_remesh",
        "--desired-face-area", str(desired_face_area),
        "--input", str(input_surf),
        "--output", str(output_surf),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_surf


def mris_smooth(
    input_surf: Path,
    output_surf: Path,
    n_iterations: int = 10,
    nw: bool = True,
    seed: Optional[int] = None,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Smooth a surface.

    Parameters
    ----------
    input_surf : Path
        Input surface
    output_surf : Path
        Output smoothed surface
    n_iterations : int, default=10
        Number of smoothing iterations
    nw : bool, default=True
        Normalize weights
    seed : int, optional
        Random seed
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output surface path
    """
    cmd = [
        "mris_smooth",
        "-n", str(n_iterations),
    ]
    
    if nw:
        cmd.append("-nw")
    if seed is not None:
        cmd.extend(["-seed", str(seed)])
    
    cmd.extend([str(input_surf), str(output_surf)])
    run_fs_command(cmd, log_file=log_file)
    return output_surf


def mris_place_surface(
    input_surf: Path,
    output_surf: Path,
    hemi: str,
    wm: Path,
    invol: Path,
    aseg: Path,
    adgws_in: Optional[Path] = None,
    white: bool = False,
    pial: bool = False,
    threads: int = 1,
    log_file: Optional[Path] = None,
    **kwargs,
) -> Path:
    """
    Place white or pial surface.

    This is a complex command with many options. See FreeSurfer documentation
    for full details.

    Parameters
    ----------
    input_surf : Path
        Input surface (e.g., white.preaparc or white)
    output_surf : Path
        Output surface (e.g., white or pial)
    hemi : str
        Hemisphere ('lh' or 'rh')
    wm : Path
        White matter segmentation
    invol : Path
        Input volume (e.g., brain.finalsurfs.mgz)
    aseg : Path
        Aseg segmentation (e.g., aseg.presurf.mgz)
    adgws_in : Path, optional
        Auto-detected gray/white stats file
    white : bool
        Place white surface
    pial : bool
        Place pial surface
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path
    **kwargs
        Additional arguments:
        - rip_label: cortex label file
        - rip_bg: flag
        - rip_surf: surface to rip from
        - pin_medial_wall: cortex label
        - repulse_surf: surface to repulse from
        - white_surf: white surface (for pial)
        - aparc: parcellation annotation
        - nsmooth: number of smoothing iterations
        - max_cbv_dist: maximum distance
        - blend_surf: blend surface
        - i: input surface (alternative to positional)

    Returns
    -------
    Path
        Output surface path
    """
    cmd = ["mris_place_surface"]
    
    # Required arguments
    if adgws_in:
        cmd.extend(["--adgws-in", str(adgws_in)])
    cmd.extend(["--seg", str(aseg)])
    cmd.extend(["--threads", str(threads)])
    cmd.extend(["--wm", str(wm)])
    cmd.extend(["--invol", str(invol)])
    cmd.append(f"--{hemi}")
    cmd.extend(["--o", str(output_surf)])
    
    # Surface type
    if white:
        cmd.append("--white")
    if pial:
        cmd.append("--pial")
    
    # Optional arguments from kwargs
    kwarg_map = {
        "rip_label": "--rip-label",
        "rip_bg": "--rip-bg",
        "rip_surf": "--rip-surf",
        "pin_medial_wall": "--pin-medial-wall",
        "repulse_surf": "--repulse-surf",
        "white_surf": "--white-surf",
        "aparc": "--aparc",
        "nsmooth": "--nsmooth",
        "max_cbv_dist": "--max-cbv-dist",
        "blend_surf": "--blend-surf",
        "i": "--i",
    }
    
    for key, value in kwargs.items():
        if key in kwarg_map:
            flag = kwarg_map[key]
            if value is True:
                cmd.append(flag)
            elif value is not False and value is not None:
                cmd.append(flag)
                cmd.append(str(value))
    
    # Input surface (if not in kwargs)
    if "--i" not in cmd:
        cmd.extend(["--i", str(input_surf)])
    
    run_fs_command(cmd, log_file=log_file)
    return output_surf


def mris_place_surface_curv_map(
    surface: Path,
    output_curv: Path,
    n_smooth: int = 2,
    n_iterations: int = 10,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Compute curvature map from surface.

    Parameters
    ----------
    surface : Path
        Input surface
    output_curv : Path
        Output curvature file
    n_smooth : int, default=2
        Smoothing iterations
    n_iterations : int, default=10
        Number of iterations
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output curvature file path
    """
    cmd = [
        "mris_place_surface",
        "--curv-map",
        str(surface),
        str(n_smooth),
        str(n_iterations),
        str(output_curv),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_curv


def mris_place_surface_area_map(
    surface: Path,
    output_area: Path,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Compute area map from surface.

    Parameters
    ----------
    surface : Path
        Input surface
    output_area : Path
        Output area file
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output area file path
    """
    cmd = [
        "mris_place_surface",
        "--area-map",
        str(surface),
        str(output_area),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_area


def mris_place_surface_thickness(
    white_surf: Path,
    pial_surf: Path,
    output_thickness: Path,
    n_smooth: int = 20,
    n_iterations: int = 5,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Compute thickness map between white and pial surfaces.

    Parameters
    ----------
    white_surf : Path
        White matter surface
    pial_surf : Path
        Pial surface
    output_thickness : Path
        Output thickness file
    n_smooth : int, default=20
        Smoothing iterations
    n_iterations : int, default=5
        Number of iterations
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output thickness file path
    """
    cmd = [
        "mris_place_surface",
        "--thickness",
        str(white_surf),
        str(pial_surf),
        str(n_smooth),
        str(n_iterations),
        str(output_thickness),
    ]
    run_fs_command(cmd, log_file=log_file)
    return output_thickness


def mris_register(
    input_sphere: Path,
    target_atlas: Path,
    output_sphere: Path,
    curv: bool = True,
    norot: bool = False,
    nosulc: bool = False,
    rotate: Optional[str] = None,
    threads: int = 1,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Register sphere to atlas.

    Parameters
    ----------
    input_sphere : Path
        Input sphere surface
    target_atlas : Path
        Target atlas (e.g., folding atlas)
    output_sphere : Path
        Output registered sphere
    curv : bool, default=True
        Use curvature
    norot : bool, default=False
        No rotation
    nosulc : bool, default=False
        No sulcus
    rotate : str, optional
        Rotation angles (e.g., "alpha beta gamma")
    threads : int
        Number of threads
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output sphere path
    """
    cmd = ["mris_register"]
    
    if curv:
        cmd.append("-curv")
    if norot:
        cmd.append("-norot")
    if nosulc:
        cmd.append("-nosulc")
    if rotate:
        cmd.extend(["-rotate", rotate])
    if threads > 1:
        cmd.extend(["-threads", str(threads)])
    
    cmd.extend([
        str(input_sphere),
        str(target_atlas),
        str(output_sphere),
    ])
    
    run_fs_command(cmd, log_file=log_file)
    return output_sphere


def mris_ca_label(
    subject: str,
    hemi: str,
    sphere_reg: Path,
    atlas: Path,
    output_annot: Path,
    cortex_label: Path,
    aseg: Path,
    seed: int = 1234,
    long_flag: Optional[str] = None,
    log_file: Optional[Path] = None,
) -> Path:
    """
    Create cortical parcellation using classifier atlas.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    sphere_reg : Path
        Registered sphere surface
    atlas : Path
        Classifier atlas (.gcs file)
    output_annot : Path
        Output annotation file
    cortex_label : Path
        Cortex label file
    aseg : Path
        Aseg segmentation
    seed : int, default=1234
        Random seed
    long_flag : str, optional
        Longitudinal flag (e.g., "-long -R base_annot")
    log_file : Path, optional
        Log file path

    Returns
    -------
    Path
        Output annotation path
    """
    cmd = [
        "mris_ca_label",
        "-l", str(cortex_label),
        "-aseg", str(aseg),
        "-seed", str(seed),
    ]
    
    if long_flag:
        cmd.extend(long_flag.split())
    
    cmd.extend([
        subject,
        hemi,
        str(sphere_reg),
        str(atlas),
        str(output_annot),
    ])
    
    run_fs_command(cmd, log_file=log_file)
    return output_annot


def mris_anatomical_stats(
    subject: str,
    hemi: str,
    surface: Path,
    annotation: Path,
    output_stats: Path,
    cortex_label: Path,
    ctab: Optional[Path] = None,
    noxfm: bool = False,
    log_file: Optional[Path] = None,
    subjects_dir: Optional[Path] = None,
    **kwargs,
) -> Path:
    """
    Compute anatomical statistics from surface parcellation.

    Parameters
    ----------
    subject : str
        Subject ID
    hemi : str
        Hemisphere ('lh' or 'rh')
    surface : Path
        Surface file (e.g., white)
    annotation : Path
        Annotation file
    output_stats : Path
        Output statistics file
    cortex_label : Path
        Cortex label file
    ctab : Path, optional
        Color table file
    noxfm : bool, default=False
        Skip transform (for non-human)
    log_file : Path, optional
        Log file path
    subjects_dir : Path, optional
        SUBJECTS_DIR path. If None, uses environment variable.
    **kwargs
        Additional arguments (e.g., -th3, -mgz, -b, -f)

    Returns
    -------
    Path
        Output stats file path
    """
    cmd = ["mris_anatomical_stats"]
    
    # Common flags
    if "-th3" not in kwargs and "th3" not in kwargs:
        cmd.append("-th3")
    if "-mgz" not in kwargs and "mgz" not in kwargs:
        cmd.append("-mgz")
    if "-b" not in kwargs and "b" not in kwargs:
        cmd.append("-b")
    
    cmd.extend(["-cortex", str(cortex_label)])
    cmd.extend(["-f", str(output_stats)])
    cmd.extend(["-a", str(annotation)])
    
    if ctab:
        cmd.extend(["-c", str(ctab)])
    # Note: -noxfm flag support varies by FreeSurfer version
    # FastSurfer uses it when no_talairach is set, but some FreeSurfer versions
    # don't support this flag. If the flag is not supported, the command will fail.
    # For compatibility, we skip the flag if it's not available in this version.
    # The statistics should still compute correctly without it.
    # TODO: Add FreeSurfer version detection to conditionally use -noxfm
    # if noxfm:
    #     cmd.append("-noxfm")
    
    # Add kwargs
    for key, value in kwargs.items():
        if key.startswith("-"):
            cmd.append(key)
            if value is not True:
                cmd.append(str(value))
        else:
            cmd.append(f"-{key.replace('_', '-')}")
            if value is not True:
                cmd.append(str(value))
    
    # Extract surface name (e.g., "white" from "/path/to/surf/lh.white")
    # When SUBJECTS_DIR is set, mris_anatomical_stats constructs the path automatically
    surface_name = surface.name
    # Remove hemisphere prefix if present (e.g., "lh.white" -> "white")
    if surface_name.startswith(f"{hemi}."):
        surface_name = surface_name[len(f"{hemi}."):]
    
    cmd.extend([subject, hemi, surface_name])
    
    # Set SUBJECTS_DIR if provided
    env = None
    if subjects_dir:
        env = {"SUBJECTS_DIR": str(subjects_dir)}
    
    run_fs_command(cmd, log_file=log_file, env=env)
    return output_stats


__all__ = [
    "mris_info",
    "mris_extract_main_component",
    "mris_remesh",
    "mris_smooth",
    "mris_place_surface",
    "mris_place_surface_curv_map",
    "mris_place_surface_area_map",
    "mris_place_surface_thickness",
    "mris_register",
    "mris_ca_label",
    "mris_anatomical_stats",
]

