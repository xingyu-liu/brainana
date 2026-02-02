"""
Topology fix utilities.

Provides:
- Euler number check via mris_euler_number
- pymeshfix-based mesh repair (closes boundary edges, fixes orientation).
"""

import re
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np


def get_euler_number(surface_path: Path) -> Optional[int]:
    """
    Get Euler number of a surface by running mris_euler_number.

    Euler number = 2 means topologically correct sphere (genus 0, no holes).

    Parameters
    ----------
    surface_path : Path
        Path to FreeSurfer surface file.

    Returns
    -------
    int or None
        Euler number (V - E + F), or None if command failed or output could not be parsed.
    """
    try:
        result = subprocess.run(
            ["mris_euler_number", str(surface_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        # Parse line like: "euler # = v-e+f = 2g-2: 10288 - 30858 + 20572 = 2 --> 0 holes"
        match = re.search(r"=\s*(-?\d+)\s*-->", result.stdout)
        if match:
            return int(match.group(1))
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        return None


def repair_surface_pymeshfix(input_path: Path, output_path: Path) -> bool:
    """
    Repair surface with pymeshfix: close holes, fix non-manifold geometry.

    Uses the same logic as scripts/surf_fix_topo.py (pymeshfix method).
    Good for fixing boundary edges and orientation defects left by mris_fix_topology.

    Parameters
    ----------
    input_path : Path
        Input FreeSurfer surface file.
    output_path : Path
        Output FreeSurfer surface file (may be same as input_path; use temp file internally if needed).

    Returns
    -------
    bool
        True if repair succeeded, False otherwise.
    """
    try:
        import nibabel.freesurfer as fs
        import pymeshfix
    except ImportError:
        return False

    try:
        vertices, faces, metadata = fs.read_geometry(input_path, read_metadata=True)
        meshfix = pymeshfix.MeshFix(vertices, faces)
        meshfix.repair(
            joincomp=True,
            remove_smallest_components=False,
        )
        v_repaired = np.asarray(meshfix.points)
        f_repaired = np.asarray(meshfix.faces)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fs.write_geometry(output_path, v_repaired, f_repaired, volume_info=metadata)
        return True
    except Exception:
        return False
