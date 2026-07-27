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

import numpy as np
import nibabel as nib
import nibabel.freesurfer.io as fs
import lapy
from lapy import TriaMesh

logger = logging.getLogger(__name__)


def signed_volume(vertices, faces) -> float:
    """Signed volume enclosed by a closed triangle mesh.

    Positive means the face winding puts normals on the outside; negative
    means the surface is inside-out. Consistency of winding (lapy's
    ``is_oriented()``) does not imply the sign is right -- a mesh can be
    perfectly consistent and entirely inverted, which is invisible to every
    topology check but silently inverts anything that samples along normals.
    """
    v1 = vertices[faces[:, 0]]
    v2 = vertices[faces[:, 1]]
    v3 = vertices[faces[:, 2]]
    return float(np.sum(np.einsum("ij,ij->i", v1, np.cross(v2 - v1, v3 - v1))) / 6.0)


class SurfaceInvariantError(RuntimeError):
    """
    A surface failed a topology invariant it was required to satisfy.

    Carries the full :func:`validate_surface` report so the message names the
    actual mesh state rather than just the assertion that failed. Raised at the
    stage boundary that produced the bad mesh, so the traceback points at the
    step responsible instead of at whatever consumes it several steps later.
    """

    def __init__(
        self,
        surface_path: Path,
        info: dict,
        violations: list[str],
        context: str = "",
    ) -> None:
        self.surface_path = surface_path
        self.info = info
        self.violations = violations
        self.context = context
        where = f" [{context}]" if context else ""
        super().__init__(
            f"Surface invariant violated{where}: {surface_path}\n"
            f"  violations: {'; '.join(violations)}\n"
            f"  actual:     V={info.get('n_vertices')} F={info.get('n_faces')} "
            f"closed={info.get('is_closed')} oriented={info.get('is_oriented')} "
            f"outward={info.get('is_outward')} euler={info.get('euler')}"
        )


def assert_surface_invariants(
    surface_path: Path,
    *,
    closed: bool = True,
    oriented: bool = True,
    outward: bool | None = None,
    euler: int | None = 2,
    min_vertices: int = 1000,
    context: str = "",
    strict: bool = True,
) -> dict:
    """
    Check a surface against topology invariants and raise if they do not hold.

    Euler number alone is not a sufficient test. A mesh with one triangle wound
    backwards is closed and has Euler 2 but is *not* oriented, and a mesh can be
    Euler 2 while still having boundary edges. All three properties are checked
    in-process via lapy, so there is no subprocess, no output parsing, and no
    path that silently reports "fine" because a check could not be performed.

    Parameters
    ----------
    surface_path : Path
        Surface file to check.
    closed, oriented : bool, default True
        Require the mesh to be closed / consistently oriented.
    outward : bool, optional
        Require normals to face outward (positive enclosed volume). Defaults to
        matching `oriented`, because consistent winding in the *wrong* sign is
        not a useful guarantee: it passes every topology check while inverting
        anything that samples along the normal. Only checked on closed meshes.
    euler : int or None, default 2
        Required Euler characteristic; None to skip the check. Use None for
        surfaces that are legitimately not genus 0 yet, e.g. raw marching-cubes
        output before topology correction.
    min_vertices : int, default 1000
        Guards against a "successful" run that produced a near-empty mesh.
    context : str
        Short label for the message, e.g. "rh pre-orig".
    strict : bool, default True
        When False, log the violations at ERROR and return instead of raising.

    Returns
    -------
    dict
        The :func:`validate_surface` report.

    Raises
    ------
    SurfaceInvariantError
        If any required invariant fails and ``strict`` is True.
    """
    info = validate_surface(surface_path)

    violations: list[str] = []
    if not info["exists"]:
        violations.append("file does not exist")
    elif not info["readable"]:
        violations.append(f"unreadable ({info.get('error')})")
    else:
        if closed and not info["is_closed"]:
            violations.append("not closed (has boundary edges)")
        if oriented and not info["is_oriented"]:
            violations.append("not consistently oriented")
        want_outward = oriented if outward is None else outward
        if want_outward and info["is_closed"] and not info["is_outward"]:
            violations.append(
                f"inside-out (signed volume {info['signed_volume']:.0f} < 0)"
            )
        if euler is not None and info["euler"] != euler:
            violations.append(f"euler={info['euler']}, expected {euler}")
        if min_vertices and info["n_vertices"] < min_vertices:
            violations.append(f"only {info['n_vertices']} vertices")

    if violations:
        if strict:
            raise SurfaceInvariantError(surface_path, info, violations, context)
        logger.error(
            "Surface check failed (non-fatal)%s: %s -- %s",
            f" [{context}]" if context else "",
            surface_path,
            "; ".join(violations),
        )

    return info


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
        logger.info("Filename missing in metadata, fixing header from pretess volume")
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
        logger.debug("No changes needed, file already has correct metadata")


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

    Raises
    ------
    SurfaceInvariantError
        If the surface is not closed (orientation cannot be fixed on a mesh
        with boundary edges), or if it is still not oriented after the fix.
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

    # A consistently-wound mesh can still be entirely inside-out. lapy's
    # is_oriented() only tests that neighbouring faces agree, so it returns
    # True for an inverted surface -- and lapy's orient_() then does nothing,
    # because there is nothing inconsistent to fix. pymeshfix is a known source
    # of this: repairing a non-oriented mesh can return a consistent result
    # with the sign flipped. Anything that samples along the normal (notably
    # mris_autodet_gwstats, which estimates the gray/white intensity
    # thresholds) then reads inside for outside and produces inverted
    # statistics, with no error anywhere.
    if mesh.is_oriented() and mesh.is_closed():
        volume = signed_volume(mesh.v, mesh.t)
        if volume < 0:
            logger.warning(
                "Surface is consistently wound but inside-out "
                "(signed volume %.0f); flipping face orientation...",
                volume,
            )
            if backup_path is not None:
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(surface_path, backup_path)

            # .copy(): a [:, ::-1] view has a negative stride, which some
            # writers and C extensions handle poorly.
            mesh.t = mesh.t[:, ::-1].copy()
            from packaging.version import Version

            if Version(lapy.__version__) <= Version("1.0.1"):
                mesh.fsinfo = fsinfo
            mesh.write_fssurf(str(surface_path))

            assert_surface_invariants(
                surface_path,
                closed=True,
                oriented=True,
                outward=True,
                euler=None,
                min_vertices=0,
                context="post-flip",
            )
            logger.info(f"Flipped and saved: {surface_path}")
            return True

    if not mesh.is_oriented():
        # orient_() propagates a consistent winding across the face adjacency
        # graph. On a mesh with boundary edges, or one that is genuinely
        # non-orientable, it cannot succeed -- and it reports nothing when it
        # fails. Refuse up front rather than write out an unchanged mesh and
        # report success.
        if not mesh.is_closed():
            raise SurfaceInvariantError(
                surface_path,
                validate_surface(surface_path),
                ["not closed, so orientation cannot be fixed"],
                context="pre-orient",
            )

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

        # Re-read from disk and confirm the fix actually took, so "Fixed and
        # saved" is a measurement rather than a claim.
        assert_surface_invariants(
            surface_path,
            closed=True,
            oriented=True,
            outward=True,
            euler=None,
            # Size is not this function's concern; it only re-checks the
            # property it just claimed to fix.
            min_vertices=0,
            context="post-orient",
        )
        logger.info(f"Fixed and saved: {surface_path}")
        return True
    else:
        logger.info("Surface orientation is OK")
        return False


def verify_surface_ras(
    surface_path: Path,
    log_file: Path | None = None,
    subject_dir: Path | None = None,
) -> bool:
    """
    Verify that surface has correct vertex locs (surfaceRAS).

    When the header lacks filename/volume info, FreeSurfer interprets vertex
    coordinates in a different space, which shifts the surface relative to the
    volume without any error being raised.

    Parameters
    ----------
    surface_path : Path
        Surface file to check
    log_file : Path, optional
        Log file to append the mris_info invocation and output to
    subject_dir : Path, optional
        Subject directory, used as the command's working directory

    Returns
    -------
    bool
        True if vertex locs is surfaceRAS

    Raises
    ------
    ValueError
        If vertex locs is not surfaceRAS
    FreeSurferError
        If mris_info itself fails
    """
    # Goes through the shared wrapper rather than a bare subprocess.run: that
    # gives a checked exit code, stderr captured into the run log, and the
    # command recorded in fastsurfer_recon.cmd. The previous local
    # implementation ignored the return code entirely, so a crashed mris_info
    # surfaced as a confusing "incorrect vertex locs" error.
    from ..wrappers.mris import mris_info

    info = mris_info(surface_path, log_file=log_file, subject_dir=subject_dir)

    # Check for surfaceRAS with flexible whitespace (mris_info uses variable spacing)
    if re.search(r"vertex\s+locs\s*:\s*surfaceRAS", info):
        logger.debug(f"Surface {surface_path} has correct vertex locs")
        return True

    logger.error(f"mris_info full output:\n{info}")
    raise ValueError(
        f"Surface {surface_path} has incorrect vertex locs. Expected 'surfaceRAS'."
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
        - error: str or None (why the surface could not be read, if it could not)

    Notes
    -----
    A file that cannot be read reports ``readable=False`` with the cause in
    ``error``, rather than being indistinguishable from a genuinely broken
    mesh. Callers that need the distinction to be fatal should go through
    :func:`assert_surface_invariants`.
    """
    # Accept str as well as Path: this is called from stages, scripts and QC
    # tooling, and an AttributeError deep inside a validator is a poor way to
    # report "you passed a string".
    surface_path = Path(surface_path)
    result = {
        "exists": surface_path.exists(),
        "readable": False,
        "n_vertices": 0,
        "n_faces": 0,
        "is_closed": False,
        "is_oriented": False,
        "euler": None,
        "signed_volume": 0.0,
        "is_outward": False,
        "error": None,
    }

    if not result["exists"]:
        return result

    try:
        vertices, faces = fs.read_geometry(surface_path)[:2]
        result["readable"] = True
        result["n_vertices"] = len(vertices)
        result["n_faces"] = len(faces)

        mesh = TriaMesh(vertices, faces)
        # lapy returns numpy scalars (np.bool_, np.int64). Coerce to builtins so
        # the report is JSON-serialisable and compares cleanly with `is`.
        result["is_closed"] = bool(mesh.is_closed())
        result["is_oriented"] = bool(mesh.is_oriented())
        result["euler"] = int(mesh.euler())
        result["signed_volume"] = signed_volume(vertices, faces)
        # Only meaningful for a closed mesh; an open one encloses nothing.
        result["is_outward"] = bool(result["is_closed"] and result["signed_volume"] > 0)

    except (OSError, ValueError, IndexError, TypeError) as e:
        # Truncated/corrupt file, wrong format, or a degenerate face array.
        # Anything else (MemoryError, a bug in lapy) is a real fault and must
        # propagate rather than be reported as "this surface is bad".
        result["readable"] = False
        result["error"] = f"{type(e).__name__}: {e}"
        logger.error("Error validating surface %s: %s", surface_path, e)

    return result


__all__ = [
    "SurfaceInvariantError",
    "assert_surface_invariants",
    "fix_mc_surface_header",
    "fix_surface_orientation",
    "verify_surface_ras",
    "validate_surface",
]
