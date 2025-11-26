"""
Surface fixing utilities.

Provides functions for:
- Fixing surface headers from marching cubes
- Fixing surface orientation (triangle normals)
- Surface validation

Based on original rewrite_mc_surface.py and rewrite_oriented_surface.py from FastSurfer.
"""

# Copyright 2019-2024 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
import shutil
import logging
import os
import re

import nibabel as nib
import nibabel.freesurfer.io as fs
import lapy
from lapy import TriaMesh

logger = logging.getLogger(__name__)


def fix_mc_surface_header(
    surface_path: Path,
    pretess_path: Path,
    output_path: Path | None = None,
) -> None:
    """
    Fix surface header from marching cubes.

    Marching cubes doesn't properly set the volume info in the surface
    header. This function fixes that by reading the info from the
    pretessellated volume. This ensures vertex locs are set to surfaceRAS.

    Parameters
    ----------
    surface_path : Path
        Input surface file
    pretess_path : Path
        Pretessellated volume file (e.g., filled-pretess127.mgz)
    output_path : Path, optional
        Output file. If None, overwrites input.
    """
    if output_path is None:
        output_path = surface_path

    logger.info(f"Loading surface: {surface_path}")
    vertices, faces, metadata = fs.read_geometry(surface_path, read_metadata=True)

    # Fix header if filename is missing (matching original rewrite_mc_surface.py exactly)
    # When filename and volume are set correctly, FreeSurfer interprets vertices as surfaceRAS
    # IMPORTANT: Only modify if filename is missing, to avoid changing file format unnecessarily
    pretess_str = str(pretess_path)
    current_filename = metadata.get("filename", "") if metadata else ""
    
    needs_fix = False
    if not current_filename:
        logger.info(f"Filename missing in metadata, fixing header from pretess volume")
        needs_fix = True
        vol = nib.load(pretess_path)
        if metadata is None:
            metadata = {}
        metadata["filename"] = pretess_str
        metadata["volume"] = vol.header.get_data_shape()
    else:
        logger.debug(f"Surface already has filename in metadata: {current_filename}")
    
    # Only write if we actually made changes (to preserve original file format)
    if needs_fix:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fs.write_geometry(output_path, vertices, faces, volume_info=metadata)
        logger.info(f"Fixed and saved: {output_path}")
    else:
        logger.debug(f"No changes needed, file already has correct metadata")


def fix_surface_orientation(
    surface_path: Path,
    backup_path: Path | None = None,
) -> bool:
    """
    Fix surface triangle orientation.

    Ensures all triangle normals point consistently outward.
    If the surface is already properly oriented, does nothing.

    Parameters
    ----------
    surface_path : Path
        Surface file to fix (will be overwritten)
    backup_path : Path, optional
        If provided and surface needs fixing, save backup here

    Returns
    -------
    bool
        True if surface was fixed, False if already OK
    """
    # Ensure getpass works (needed by nibabel)
    try:
        import getpass
        getpass.getuser()
    except Exception:
        os.environ.setdefault("USERNAME", "UNKNOWN")

    logger.info(f"Checking surface orientation: {surface_path}")
    mesh = TriaMesh.read_fssurf(str(surface_path))
    fsinfo = mesh.fsinfo

    if not mesh.is_oriented():
        logger.warning("Surface is not properly oriented, fixing...")
        
        if backup_path is not None:
            logger.info(f"Creating backup: {backup_path}")
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(surface_path, backup_path)

        mesh.orient_()

        # Fix for lapy <= 1.0.1 bug
        from packaging.version import Version
        if Version(lapy.__version__) <= Version("1.0.1"):
            mesh.fsinfo = fsinfo

        mesh.write_fssurf(str(surface_path))
        logger.info(f"Fixed and saved: {surface_path}")
        return True
    else:
        logger.info("Surface orientation is OK")
        return False


def verify_surface_ras(surface_path: Path) -> bool:
    """
    Verify that surface has correct vertex locs (surfaceRAS).

    Parameters
    ----------
    surface_path : Path
        Surface file to check

    Returns
    -------
    bool
        True if vertex locs is surfaceRAS

    Raises
    ------
    ValueError
        If vertex locs is not surfaceRAS
    """
    from subprocess import run, PIPE

    result = run(
        ["mris_info", str(surface_path)],
        capture_output=True,
        text=True,
    )

    # Check for surfaceRAS with flexible whitespace (mris_info uses variable spacing)
    if re.search(r"vertex\s+locs\s*:\s*surfaceRAS", result.stdout):
        logger.debug(f"Surface {surface_path} has correct vertex locs")
        return True
    else:
        raise ValueError(
            f"Surface {surface_path} has incorrect vertex locs. "
            "Expected 'surfaceRAS'."
        )


def validate_surface(surface_path: Path) -> dict:
    """
    Validate a surface file.

    Checks:
    - File exists and is readable
    - Surface is properly oriented
    - Basic mesh properties

    Parameters
    ----------
    surface_path : Path
        Surface file to validate

    Returns
    -------
    dict
        Validation results with keys:
        - exists: bool
        - readable: bool
        - n_vertices: int
        - n_faces: int
        - is_closed: bool
        - is_oriented: bool
        - euler: int (Euler characteristic)
    """
    result = {
        "exists": surface_path.exists(),
        "readable": False,
        "n_vertices": 0,
        "n_faces": 0,
        "is_closed": False,
        "is_oriented": False,
        "euler": None,
    }

    if not result["exists"]:
        return result

    try:
        vertices, faces = fs.read_geometry(surface_path)[:2]
        result["readable"] = True
        result["n_vertices"] = len(vertices)
        result["n_faces"] = len(faces)

        mesh = TriaMesh(vertices, faces)
        result["is_closed"] = mesh.is_closed()
        result["is_oriented"] = mesh.is_oriented()
        result["euler"] = mesh.euler()

    except Exception as e:
        logger.error(f"Error validating surface: {e}")

    return result


__all__ = [
    "fix_mc_surface_header",
    "fix_surface_orientation",
    "verify_surface_ras",
    "validate_surface",
]

