"""
LTA (Linear Transform Array) file utilities.

Functions for reading and writing FreeSurfer LTA files.

Based on original lta.py from FastSurfer.
"""

# Copyright 2021 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Any
import getpass
from datetime import datetime

import numpy as np
import numpy.typing as npt


def write_lta(
    filename: str | Path,
    transform: npt.ArrayLike,
    src_filename: str,
    src_header: dict[str, Any],
    dst_filename: str,
    dst_header: dict[str, Any],
) -> None:
    """
    Write a linear transform to an LTA file.

    Parameters
    ----------
    filename : str or Path
        Output LTA file path
    transform : array-like, shape (4, 4)
        Linear transform matrix (RAS to RAS)
    src_filename : str
        Source volume filename
    src_header : dict
        Source volume header with keys: dims, delta, Mdc, Pxyz_c
    dst_filename : str
        Destination volume filename
    dst_header : dict
        Destination volume header with keys: dims, delta, Mdc, Pxyz_c

    Raises
    ------
    ValueError
        If required header fields are missing
    """
    filename = Path(filename)
    transform = np.asarray(transform)

    # Validate headers
    required_fields = ("dims", "delta", "Mdc", "Pxyz_c")
    for field in required_fields:
        if field not in src_header:
            raise ValueError(f"src_header missing required field: {field}")
        if field not in dst_header:
            raise ValueError(f"dst_header missing required field: {field}")

    # Extract source info
    src_dims = _format_array(src_header["dims"][0:3])
    src_vsize = _format_array(src_header["delta"][0:3])
    src_v2r = src_header["Mdc"]
    src_c = src_header["Pxyz_c"]

    # Extract destination info
    dst_dims = _format_array(dst_header["dims"][0:3])
    dst_vsize = _format_array(dst_header["delta"][0:3])
    dst_v2r = dst_header["Mdc"]
    dst_c = dst_header["Pxyz_c"]

    # Ensure parent directory exists
    filename.parent.mkdir(parents=True, exist_ok=True)

    with open(filename, "w") as f:
        # Header
        f.write(f"# transform file {filename}\n")
        f.write(f"# created by {getpass.getuser()} on {datetime.now().ctime()}\n\n")
        
        # Transform metadata
        f.write("type      = 1 # LINEAR_RAS_TO_RAS\n")
        f.write("nxforms   = 1\n")
        f.write("mean      = 0.0 0.0 0.0\n")
        f.write("sigma     = 1.0\n")
        
        # Transform matrix
        f.write("1 4 4\n")
        f.write(_format_matrix(transform))
        f.write("\n")
        
        # Source volume info
        f.write("src volume info\n")
        f.write("valid = 1  # volume info valid\n")
        f.write(f"filename = {src_filename}\n")
        f.write(f"volume = {src_dims}\n")
        f.write(f"voxelsize = {src_vsize}\n")
        f.write(f"xras   = {_format_array(src_v2r[0, :])}\n")
        f.write(f"yras   = {_format_array(src_v2r[1, :])}\n")
        f.write(f"zras   = {_format_array(src_v2r[2, :])}\n")
        f.write(f"cras   = {_format_array(src_c)}\n")
        
        # Destination volume info
        f.write("dst volume info\n")
        f.write("valid = 1  # volume info valid\n")
        f.write(f"filename = {dst_filename}\n")
        f.write(f"volume = {dst_dims}\n")
        f.write(f"voxelsize = {dst_vsize}\n")
        f.write(f"xras   = {_format_array(dst_v2r[0, :])}\n")
        f.write(f"yras   = {_format_array(dst_v2r[1, :])}\n")
        f.write(f"zras   = {_format_array(dst_v2r[2, :])}\n")
        f.write(f"cras   = {_format_array(dst_c)}\n")


def _format_array(arr: npt.ArrayLike) -> str:
    """Format an array as space-separated values."""
    return " ".join(str(x) for x in np.asarray(arr).ravel())


def _format_matrix(mat: npt.ArrayLike) -> str:
    """Format a matrix for LTA file."""
    mat = np.asarray(mat)
    lines = []
    for row in mat:
        lines.append(" ".join(f"{x:.15e}" for x in row))
    return "\n".join(lines)


def read_lta(filename: str | Path) -> dict[str, Any]:
    """
    Read an LTA file.

    Parameters
    ----------
    filename : str or Path
        LTA file path

    Returns
    -------
    dict
        Dictionary containing:
        - 'transform': 4x4 transform matrix
        - 'type': transform type
        - 'src': source volume info
        - 'dst': destination volume info
    """
    filename = Path(filename)
    
    result = {
        "transform": None,
        "type": None,
        "src": {},
        "dst": {},
    }
    
    with open(filename) as f:
        lines = f.readlines()
    
    i = 0
    current_section = None
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip comments and empty lines
        if not line or line.startswith("#"):
            i += 1
            continue
        
        # Parse type
        if line.startswith("type"):
            result["type"] = int(line.split("=")[1].split("#")[0].strip())
        
        # Parse transform matrix
        elif line.startswith("1 4 4"):
            # Next 4 lines are the matrix
            matrix_lines = []
            for j in range(4):
                i += 1
                matrix_lines.append([float(x) for x in lines[i].split()])
            result["transform"] = np.array(matrix_lines)
        
        # Parse volume info sections
        elif "src volume info" in line.lower():
            current_section = "src"
        elif "dst volume info" in line.lower():
            current_section = "dst"
        elif current_section and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.split("#")[0].strip()
            
            if key == "volume":
                result[current_section]["dims"] = np.array([int(x) for x in value.split()])
            elif key == "voxelsize":
                result[current_section]["delta"] = np.array([float(x) for x in value.split()])
            elif key in ("xras", "yras", "zras"):
                if "Mdc" not in result[current_section]:
                    result[current_section]["Mdc"] = []
                result[current_section]["Mdc"].append([float(x) for x in value.split()])
            elif key == "cras":
                result[current_section]["Pxyz_c"] = np.array([float(x) for x in value.split()])
            elif key == "filename":
                result[current_section]["filename"] = value
        
        i += 1
    
    # Convert Mdc to numpy array
    for section in ("src", "dst"):
        if "Mdc" in result[section]:
            result[section]["Mdc"] = np.array(result[section]["Mdc"])
    
    return result


# Backwards compatibility alias
writeLTA = write_lta


__all__ = [
    "write_lta",
    "read_lta",
    # Backwards compatibility
    "writeLTA",
]

