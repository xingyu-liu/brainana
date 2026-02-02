"""
Spherical projection and registration utilities.

Provides functions for:
- Spectral spherical projection (alternative to FreeSurfer qsphere)
- Sphere rotation alignment

Based on original spherically_project.py and rotate_sphere.py from FastSurfer.
"""

# Copyright 2019-2021 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
import math
import logging
import os

import nibabel.freesurfer.io as fs
import numpy as np
import numpy.typing as npt
from lapy import TriaMesh
from lapy.diffgeo import tria_mean_curvature_flow
from lapy.solver import Solver

logger = logging.getLogger(__name__)


def spherically_project(
    mesh: TriaMesh,
    flow_iterations: int = 3,
    use_cholmod: bool = True,
) -> TriaMesh:
    """
    Project a closed surface mesh onto a sphere using spectral embedding.

    Uses the first three non-constant eigenfunctions of the Laplace-Beltrami
    operator to create a spectral embedding, then projects onto a unit sphere.

    Parameters
    ----------
    mesh : TriaMesh
        Input triangle mesh (must be closed)
    flow_iterations : int, default=3
        Mean curvature flow iterations for smoothing
    use_cholmod : bool, default=True
        Use CHOLMOD for faster eigendecomposition

    Returns
    -------
    TriaMesh
        Spherically projected mesh

    Raises
    ------
    ValueError
        If mesh is not closed
    """
    if not mesh.is_closed():
        raise ValueError("Can only project closed meshes")

    def get_flipped_area(tria: TriaMesh) -> float:
        """Compute area of triangles with normals pointing inward."""
        v1 = tria.v[tria.t[:, 0], :]
        v2 = tria.v[tria.t[:, 1], :]
        v3 = tria.v[tria.t[:, 2], :]
        cr = np.cross(v2 - v1, v3 - v1)
        spatvol = np.sum(v1 * cr, axis=1)
        areas = 0.5 * np.sqrt(np.sum(cr * cr, axis=1))
        return np.sum(areas[spatvol < 0])

    # Compute eigenfunctions
    logger.info("Computing Laplace-Beltrami eigenfunctions...")
    fem = Solver(mesh, lump=False, use_cholmod=use_cholmod)
    evals, evecs = fem.eigs(k=4)

    logger.debug(f"Eigenvalues: {evals}")

    # Use eigenfunctions 1-3 (skip constant eigenfunction 0)
    ev1, ev2, ev3 = evecs[:, 1], evecs[:, 2], evecs[:, 3]

    # Sign flip based on brain hemisphere conventions
    # (assumes FreeSurfer coordinate system)
    if np.mean(ev1[mesh.v[:, 1] > np.mean(mesh.v[:, 1])]) < 0:
        ev1 = -ev1
    if np.mean(ev2[mesh.v[:, 2] > np.mean(mesh.v[:, 2])]) < 0:
        ev2 = -ev2
    if np.mean(ev3[mesh.v[:, 0] > np.mean(mesh.v[:, 0])]) > 0:
        ev3 = -ev3

    # Create spectral embedding
    evecs_scaled = np.column_stack([ev2, ev1, ev3])
    
    # Apply mean curvature flow to smooth
    logger.info("Applying mean curvature flow...")
    sphere = TriaMesh(evecs_scaled, mesh.t)
    sphere_smooth = tria_mean_curvature_flow(sphere, max_iter=flow_iterations)

    # Project to unit sphere
    logger.info("Projecting to unit sphere...")
    norms = np.sqrt(np.sum(sphere_smooth.v ** 2, axis=1))
    sphere_smooth.v = sphere_smooth.v / norms[:, np.newaxis]

    # Check for flipped triangles
    flipped_area = get_flipped_area(sphere_smooth)
    total_area = sphere_smooth.area()
    flipped_pct = 100 * flipped_area / total_area
    logger.info(f"Flipped triangle area: {flipped_pct:.2f}%")

    # Scale to FreeSurfer sphere radius (100)
    sphere_smooth.v = sphere_smooth.v * 100.0

    return sphere_smooth


def compute_rotation_angles(
    src_sphere: npt.NDArray,
    src_aparc: npt.NDArray,
    trg_sphere: npt.NDArray,
    trg_aparc: npt.NDArray,
) -> tuple[float, float, float]:
    """
    Compute rotation angles to align source sphere to target.

    Uses parcellation centroids to find the optimal rotation.

    Parameters
    ----------
    src_sphere : ndarray
        Source sphere vertices
    src_aparc : ndarray
        Source parcellation labels
    trg_sphere : ndarray
        Target sphere vertices
    trg_aparc : ndarray
        Target parcellation labels

    Returns
    -------
    tuple[float, float, float]
        Rotation angles (alpha, beta, gamma) in degrees
    """
    from scipy.spatial.transform import Rotation

    # Find common labels
    src_labels = set(np.unique(src_aparc)) - {0, -1}
    trg_labels = set(np.unique(trg_aparc)) - {0, -1}
    common_labels = src_labels & trg_labels

    if len(common_labels) < 3:
        raise ValueError(f"Need at least 3 common labels, found {len(common_labels)}")

    logger.info(f"Using {len(common_labels)} common labels for alignment")

    # Compute centroids for each label
    src_centroids = []
    trg_centroids = []

    for label in sorted(common_labels):
        # Source centroid
        src_mask = src_aparc == label
        src_cent = np.mean(src_sphere[src_mask], axis=0)
        src_cent = src_cent / np.linalg.norm(src_cent) * 100  # Project to sphere

        # Target centroid
        trg_mask = trg_aparc == label
        trg_cent = np.mean(trg_sphere[trg_mask], axis=0)
        trg_cent = trg_cent / np.linalg.norm(trg_cent) * 100

        src_centroids.append(src_cent)
        trg_centroids.append(trg_cent)

    src_pts = np.array(src_centroids)
    trg_pts = np.array(trg_centroids)

    # Find optimal rotation using SVD
    H = src_pts.T @ trg_pts
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T

    # Ensure proper rotation (det = 1)
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T

    # Convert to Euler angles
    rot = Rotation.from_matrix(R)
    angles = rot.as_euler('xyz', degrees=True)

    logger.info(f"Rotation angles: {angles}")
    return tuple(angles)


def spherically_project_surface(
    input_path: Path,
    output_path: Path,
    threads: int = 1,
) -> None:
    """
    Project a surface to sphere and save.

    Parameters
    ----------
    input_path : Path
        Input surface file
    output_path : Path
        Output sphere file
    threads : int, default=1
        Number of threads to use for linear algebra operations.
        Limits OpenMP/MKL/OpenBLAS threading to prevent system slowdown.
    """
    # Set environment variables to limit threading for numerical libraries
    # This is critical because eigendecomposition can use all available CPU cores
    # by default, making the system unresponsive.
    from ..utils.threading import set_numerical_threads
    set_numerical_threads(threads)
    
    logger.info(f"Loading surface: {input_path}")
    vertices, faces, metadata = fs.read_geometry(input_path, read_metadata=True)
    mesh = TriaMesh(vertices, faces)

    # Check if scikit-sparse is available for cholmod
    try:
        import sksparse  # type: ignore[import-untyped]  # noqa: F401
        use_cholmod = True
        logger.debug("Using CHOLMOD for faster eigendecomposition (scikit-sparse available)")
    except ImportError:
        use_cholmod = False
        logger.warning(
            "scikit-sparse not available, falling back to slower eigendecomposition. "
            "Install with: pip install scikit-sparse"
        )

    logger.info("Projecting to sphere...")
    sphere = spherically_project(mesh, use_cholmod=use_cholmod)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fs.write_geometry(output_path, sphere.v, sphere.t, volume_info=metadata)
    logger.info(f"Saved: {output_path}")


def compute_sphere_rotation(
    src_sphere_path: Path,
    src_aparc_path: Path,
    trg_sphere_path: Path,
    trg_aparc_path: Path,
    output_path: Path,
) -> None:
    """
    Compute and save rotation angles for sphere alignment.

    Parameters
    ----------
    src_sphere_path : Path
        Source sphere surface
    src_aparc_path : Path
        Source parcellation annotation
    trg_sphere_path : Path
        Target sphere surface
    trg_aparc_path : Path
        Target parcellation annotation
    output_path : Path
        Output file for angles (text file)
    """
    # Load data
    src_sphere = fs.read_geometry(src_sphere_path)[0]
    src_aparc = fs.read_annot(src_aparc_path)[0]
    trg_sphere = fs.read_geometry(trg_sphere_path)[0]
    trg_aparc = fs.read_annot(trg_aparc_path)[0]

    # Compute rotation
    angles = compute_rotation_angles(src_sphere, src_aparc, trg_sphere, trg_aparc)

    # Save angles
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(f"{angles[0]:.6f} {angles[1]:.6f} {angles[2]:.6f}\n")
    logger.info(f"Saved angles to: {output_path}")


__all__ = [
    "spherically_project",
    "compute_rotation_angles",
    "spherically_project_surface",
    "compute_sphere_rotation",
]

