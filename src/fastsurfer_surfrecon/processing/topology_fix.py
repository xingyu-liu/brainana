"""
Topology fix utilities.

Provides:
- Euler number check via mris_euler_number
- pymeshfix-based mesh repair (closes boundary edges, fixes orientation).
"""

import logging
import re
import subprocess
from pathlib import Path

import nibabel.freesurfer as fs
import numpy as np

# pymeshfix is a declared core dependency (see pyproject.toml). It is imported
# unguarded and at module scope on purpose: a missing core dependency is a
# corrupt environment, and must fail loudly at import time rather than degrade
# into a warning three hours into a run. See the module policy in
# fastsurfer_surfrecon/processing/__init__.py.
#
# The low-level PyTMesh API is used rather than the pymeshfix.MeshFix wrapper:
# MeshFix.__init__ probes find_spec("pyvista.core"), which *raises*
# ModuleNotFoundError when pyvista is absent, and pyvista is only a
# `pymeshfix[extras]` dependency that nothing installs for us. PyTMesh reaches
# the same C++ routines with no pyvista involvement at all.
from pymeshfix import _meshfix

from .surface_fix import signed_volume, validate_surface

logger = logging.getLogger(__name__)


def get_euler_number(surface_path: Path) -> int:
    """
    Get Euler number of a surface by running mris_euler_number.

    Euler number = 2 means topologically correct sphere (genus 0, no holes).

    This is a reporting helper for parity with recon-all logs. It is
    deliberately *not* used as control flow: :func:`validate_surface` computes
    the Euler characteristic in-process along with closedness and orientation,
    with no subprocess, no output parsing, and no way to silently report
    "unknown".

    Parameters
    ----------
    surface_path : Path
        Path to FreeSurfer surface file.

    Returns
    -------
    int
        Euler number (V - E + F).

    Raises
    ------
    RuntimeError
        If mris_euler_number is missing, times out, exits non-zero, or emits
        output this function cannot parse. Each of these previously returned
        None, which callers could not distinguish from a healthy surface.
    """
    try:
        result = subprocess.run(
            ["mris_euler_number", str(surface_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"mris_euler_number not found; is FREESURFER_HOME on PATH? ({e})"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"mris_euler_number timed out after 60s on {surface_path}"
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"mris_euler_number failed on {surface_path} "
            f"(exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )

    # Parse line like: "euler # = v-e+f = 2g-2: 10288 - 30858 + 20572 = 2 --> 0 holes"
    match = re.search(r"=\s*(-?\d+)\s*-->", result.stdout)
    if not match:
        raise RuntimeError(
            f"Could not parse mris_euler_number output for {surface_path}: "
            f"{result.stdout.strip()[:500]!r}"
        )
    return int(match.group(1))


def repair_surface_pymeshfix(input_path: Path, output_path: Path) -> dict:
    """
    Repair surface with pymeshfix: close holes, fix non-manifold geometry.

    Good for fixing boundary edges and orientation defects left by
    mris_fix_topology.

    Drives pymeshfix's low-level ``PyTMesh`` API rather than
    ``MeshFix(...).repair(joincomp=True, remove_smallest_components=False)``.
    The call sequence below is exactly what that wrapper executes, so the
    geometry is identical by construction, but it does not touch pyvista (see
    the module-level import note) and it honours the quiet flag, which the
    ``clean_from_arrays`` convenience function does not.

    Parameters
    ----------
    input_path : Path
        Input FreeSurfer surface file.
    output_path : Path
        Output FreeSurfer surface file (may be same as input_path; use temp file internally if needed).

    Returns
    -------
    dict
        The :func:`validate_surface` report for the *written* surface. Callers
        must inspect it: a repair that runs without raising has not necessarily
        produced a closed, oriented, genus-0 mesh, and the previous ``True``
        return value could not express the difference.

    Raises
    ------
    Exception
        Errors are not swallowed. A corrupt input, a pymeshfix API change, or
        an out-of-memory condition propagates to the caller, because none of
        those mean "this particular mesh was unrepairable".
    """
    vertices, faces, metadata = fs.read_geometry(input_path, read_metadata=True)

    # Equivalent to MeshFix.repair(joincomp=True, remove_smallest_components=False):
    # fill_small_boundaries -> join_closest_components -> clean.
    # remove_smallest_components is deliberately not called; discarding
    # components would silently drop cortex.
    tin = _meshfix.PyTMesh()
    tin.set_quiet(True)
    tin.load_array(
        np.ascontiguousarray(vertices, dtype=np.float64),
        np.ascontiguousarray(faces, dtype=np.int32),
    )
    tin.fill_small_boundaries(0, True)
    tin.join_closest_components()
    tin.clean()
    v_repaired, f_repaired = tin.return_arrays()

    if len(v_repaired) == 0 or len(f_repaired) == 0:
        raise RuntimeError(
            f"pymeshfix returned an empty mesh for {input_path} "
            f"(V={len(v_repaired)}, F={len(f_repaired)})"
        )

    # pymeshfix makes the winding consistent, but not necessarily outward: on a
    # non-oriented input it can return a mesh that is entirely inside-out. That
    # passes every topology check (closed, oriented, Euler 2) while inverting
    # anything that samples along the normal -- observed in a real subject whose
    # gray/white intensity means came out swapped, silently. Normalise the sign
    # here so the repair never changes the surface's orientation convention.
    if signed_volume(v_repaired, f_repaired) < 0:
        logger.warning(
            "pymeshfix returned an inside-out mesh for %s; flipping face winding",
            input_path,
        )
        f_repaired = f_repaired[:, ::-1].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # volume_info carries the surfaceRAS header; losing it silently shifts the
    # surface relative to the volume.
    fs.write_geometry(output_path, v_repaired, f_repaired, volume_info=metadata)

    return validate_surface(output_path)
