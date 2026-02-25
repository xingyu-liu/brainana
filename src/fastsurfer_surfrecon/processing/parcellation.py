"""
Surface parcellation utilities.

Provides functions for:
- Sampling volume parcellation labels onto surfaces
- Smoothing and cleaning surface parcellations
- Label island detection and removal

Based on original sample_parc.py and smooth_aparc.py from FastSurfer.
"""

# Copyright 2019-2024 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Optional, Tuple
import logging

import nibabel as nib
import nibabel.freesurfer.io as fs
import numpy as np
import numpy.typing as npt
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from lapy import TriaMesh

logger = logging.getLogger(__name__)

# Type aliases
SurfaceType = Tuple[npt.NDArray, npt.NDArray]  # (vertices, faces)


# =============================================================================
# Mesh Adjacency and Graph Operations
# =============================================================================

def get_adjacency_matrix(faces: npt.NDArray, n_vertices: int) -> sparse.csr_matrix:
    """
    Create symmetric sparse adjacency matrix from triangle mesh.

    Parameters
    ----------
    faces : ndarray, shape (m, 3)
        Triangle face indices
    n_vertices : int
        Number of vertices

    Returns
    -------
    sparse.csr_matrix
        Symmetric adjacency matrix (bool)
    """
    i = faces[:, [0, 1, 1, 2, 2, 0]].ravel()
    j = faces[:, [1, 0, 2, 1, 0, 2]].ravel()
    data = np.ones(len(i), dtype=bool)
    adj = sparse.csr_matrix((data, (i, j)), shape=(n_vertices, n_vertices))
    # Ensure symmetric
    return (adj + adj.T).astype(bool)


def get_cluster_adjacency(faces: npt.NDArray, labels: npt.NDArray) -> sparse.csc_matrix:
    """
    Compute adjacency matrix excluding edges that cross label boundaries.

    Parameters
    ----------
    faces : ndarray, shape (m, 3)
        Triangle face indices
    labels : ndarray, shape (n,)
        Vertex labels

    Returns
    -------
    sparse.csc_matrix
        Adjacency matrix with cross-label edges removed
    """
    t0, t1, t2 = faces[:, 0], faces[:, 1], faces[:, 2]
    i = np.column_stack((t0, t1, t1, t2, t2, t0)).ravel()
    j = np.column_stack((t1, t0, t2, t1, t0, t2)).ravel()
    
    # Keep only edges where both vertices have the same label
    keep = labels[i] == labels[j]
    i, j = i[keep], j[keep]
    
    data = np.ones(len(i))
    return sparse.csc_matrix((data, (i, j)), shape=(len(labels), len(labels)))


def find_label_islands(
    surface: SurfaceType,
    labels: npt.NDArray,
) -> npt.NDArray:
    """
    Find vertices in disconnected islands for all labels.

    Parameters
    ----------
    surface : tuple
        (vertices, faces) from nibabel
    labels : ndarray
        Vertex labels

    Returns
    -------
    ndarray
        Indices of vertices in disconnected islands
    """
    vertices, faces = surface
    
    # Adjacency without cross-label edges
    adj = get_cluster_adjacency(faces, labels)
    
    # Find connected components
    n_components, component_labels = connected_components(
        csgraph=adj, directed=False, return_labels=True
    )
    
    # For each label, find islands (not connected to main component)
    unique_labels = np.unique(labels)
    island_vertices = []
    
    for label_id in unique_labels:
        label_mask = labels == label_id
        label_components = component_labels[label_mask]
        label_indices = np.where(label_mask)[0]
        
        # Find the main component (most vertices)
        main_component = np.bincount(label_components).argmax()
        
        # Vertices not in main component are islands
        island_mask = label_components != main_component
        if np.any(island_mask):
            island_verts = label_indices[island_mask]
            island_vertices.extend(island_verts)
            logger.debug(f"Label {label_id}: found {len(island_verts)} island vertices")
    
    return np.array(island_vertices, dtype=np.int32)


# =============================================================================
# Mode Filter (Smoothing)
# =============================================================================

def mode_filter(
    adj: sparse.csr_matrix,
    labels: npt.NDArray,
    fill_label: int | None = None,
    no_vote_labels: npt.ArrayLike | None = None,
) -> npt.NDArray:
    """
    Apply mode filter (smoothing) to labels on mesh vertices.

    Each vertex gets the most common label among its neighbors.

    Parameters
    ----------
    adj : sparse.csr_matrix
        Adjacency matrix (include self in adj for self-voting)
    labels : ndarray
        Vertex labels
    fill_label : int, optional
        Only smooth vertices with this label. If None, smooth all.
    no_vote_labels : array-like, optional
        Labels that should not participate in voting

    Returns
    -------
    ndarray
        Smoothed labels
    """
    n = len(labels)
    labels_new = labels.copy()
    
    # Which vertices to process
    if fill_label is not None:
        process_ids = np.where(labels == fill_label)[0]
        if len(process_ids) == 0:
            return labels_new
    else:
        process_ids = np.arange(n)
    
    # Get neighbor labels for each vertex to process
    for vid in process_ids:
        # Get neighbors (including self if in adj)
        neighbors = adj[vid].indices
        neighbor_labels = labels[neighbors]
        
        # Exclude no-vote labels
        if no_vote_labels is not None:
            valid = ~np.isin(neighbor_labels, no_vote_labels)
            neighbor_labels = neighbor_labels[valid]
        
        if len(neighbor_labels) == 0:
            continue
        
        # Most common label wins
        counts = np.bincount(neighbor_labels)
        labels_new[vid] = np.argmax(counts)
    
    return labels_new


def smooth_aparc(
    surface: SurfaceType,
    labels: npt.NDArray,
    cortex: npt.NDArray | None = None,
    iterations: int = 10,
) -> npt.NDArray:
    """
    Smooth surface parcellation labels.

    Fills holes and smooths boundaries in the parcellation.

    Parameters
    ----------
    surface : tuple
        (vertices, faces) from nibabel
    labels : ndarray
        Vertex labels
    cortex : ndarray, optional
        Cortex label indices (only smooth within cortex)
    iterations : int, default=10
        Number of smoothing iterations

    Returns
    -------
    ndarray
        Smoothed labels
    """
    vertices, faces = surface
    n_vertices = len(vertices)
    
    # Create adjacency with self-connections
    adj = get_adjacency_matrix(faces, n_vertices)
    adj = adj + sparse.eye(n_vertices, dtype=bool)
    
    # Create cortex mask
    if cortex is not None:
        cortex_mask = np.zeros(n_vertices, dtype=bool)
        cortex_mask[cortex] = True
    else:
        cortex_mask = np.ones(n_vertices, dtype=bool)
    
    labels_smooth = labels.copy()
    
    # Iteratively smooth unknown (0) labels within cortex only.
    # mode_filter(fill_label=0) updates all vertices with label 0, so we must re-mask
    # after each iteration so labels do not bleed outside cortex.
    for i in range(iterations):
        unknown_in_cortex = (labels_smooth == 0) & cortex_mask
        n_unknown = np.sum(unknown_in_cortex)
        
        if n_unknown == 0:
            break
        
        # Apply mode filter to unknown vertices (may assign to non-cortex; we fix below)
        labels_smooth = mode_filter(
            adj, labels_smooth,
            fill_label=0,
            no_vote_labels=[0],  # Don't vote for unknown
        )
        # Restrict labels to cortex: non-cortex must stay 0
        if cortex is not None:
            labels_smooth[~cortex_mask] = 0

        logger.debug(f"Smoothing iteration {i+1}: {n_unknown} unknown vertices")
    
    # Final clamp so output never has labels outside cortex
    if cortex is not None:
        labels_smooth[~cortex_mask] = 0

    return labels_smooth


# =============================================================================
# Volume to Surface Sampling
# =============================================================================

def sample_volume_to_surface(
    surface: SurfaceType,
    image: nib.Nifti1Image | nib.MGHImage,
    cortex: npt.NDArray | None = None,
    proj_mm: float = 0.0,
    search_radius: float | None = None,
) -> npt.NDArray:
    """
    Sample volume labels onto surface vertices.

    Parameters
    ----------
    surface : tuple
        (vertices, faces) from nibabel
    image : nibabel image
        Volume to sample
    cortex : ndarray, optional
        Cortex vertex indices
    proj_mm : float, default=0
        Project along normal by this distance (mm)
    search_radius : float, optional
        If sample is 0, search within this radius for non-zero value

    Returns
    -------
    ndarray
        Sampled labels for each vertex
    """
    vertices, faces = surface
    n_vertices = len(vertices)
    
    # Create cortex mask
    if cortex is not None:
        mask = np.zeros(n_vertices, dtype=bool)
        mask[cortex] = True
    else:
        mask = np.ones(n_vertices, dtype=bool)
    
    data = np.asarray(image.dataobj)
    
    # Compute vertex normals using LaPy
    T = TriaMesh(vertices, faces)
    if not T.is_oriented():
        logger.warning("Surface not oriented, flipping normals")
        T.orient_()
    
    # Sample coordinates (with projection along normal)
    sample_coords = vertices + proj_mm * T.vertex_normals()
    sample_coords = sample_coords[mask]
    
    # Transform to voxel space
    Torig = image.header.get_vox2ras_tkr()
    Tinv = np.linalg.inv(Torig)
    vox_coords = sample_coords @ Tinv[:3, :3].T + Tinv[:3, 3]
    
    # Nearest neighbor sampling
    vox_nn = np.rint(vox_coords).astype(int)
    samples = data[vox_nn[:, 0], vox_nn[:, 1], vox_nn[:, 2]]
    
    # Search for non-zero if requested
    if search_radius and np.any(samples == 0):
        zero_idx = np.where(samples == 0)[0]
        logger.info(f"Searching {len(zero_idx)} zero samples within radius {search_radius}")
        for idx in zero_idx:
            samples[idx] = _search_nearest_nonzero(
                data, vox_nn[idx], search_radius, image.header.get_zooms()[0]
            )
    
    # Create full result array
    result = np.zeros(n_vertices, dtype=samples.dtype)
    result[mask] = samples
    return result


def _search_nearest_nonzero(
    data: npt.NDArray,
    center: npt.NDArray,
    radius: float,
    voxel_size: float,
) -> int:
    """Search for nearest non-zero value within radius."""
    r_vox = int(np.ceil(radius / voxel_size))
    
    # Search in expanding shells
    for r in range(1, r_vox + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    if abs(dx) == r or abs(dy) == r or abs(dz) == r:
                        x, y, z = center + np.array([dx, dy, dz])
                        if 0 <= x < data.shape[0] and 0 <= y < data.shape[1] and 0 <= z < data.shape[2]:
                            val = data[x, y, z]
                            if val != 0:
                                return val
    return 0


# =============================================================================
# Label Translation
# =============================================================================

def translate_labels(
    labels: npt.NDArray,
    volume_lut: Path,
    surface_lut: Path,
) -> Tuple[npt.NDArray, npt.NDArray, npt.NDArray]:
    """
    Translate volume labels to surface labels using lookup tables.

    Parameters
    ----------
    labels : ndarray
        Volume label IDs
    volume_lut : Path
        Volume label lookup table
    surface_lut : Path
        Surface label lookup table

    Returns
    -------
    surface_labels : ndarray
        Translated surface labels
    ctab : ndarray
        Color table for surface labels
    names : ndarray
        Label names
    """
    # Load LUTs
    surf_data = np.loadtxt(surface_lut, usecols=(0, 2, 3, 4, 5), dtype=int)
    surf_ids = surf_data[:, 0]
    surf_ctab = surf_data[:, 1:5]
    surf_names = np.loadtxt(surface_lut, usecols=(1,), dtype=str)
    
    vol_data = np.loadtxt(volume_lut, usecols=(0, 2, 3, 4, 5), dtype=int)
    vol_ids = vol_data[:, 0]
    vol_names = np.loadtxt(volume_lut, usecols=(1,), dtype=str)
    
    # Verify names match
    if not np.all(vol_names == surf_names):
        raise ValueError("LUT label names do not match")
    
    # Create translation lookup dictionary (handles negative indices)
    # Use dictionary to support both positive and negative label IDs
    lut_dict = dict(zip(vol_ids, surf_ids))
    
    # Translate labels using dictionary lookup
    # Unknown labels (not in LUT) are set to 0 (background)
    surface_labels = np.zeros_like(labels, dtype=labels.dtype)
    unique_labels = np.unique(labels)
    for vol_id in unique_labels:
        if vol_id in lut_dict:
            surface_labels[labels == vol_id] = lut_dict[vol_id]
        # Labels not in LUT remain 0 (background)
    
    return surface_labels, surf_ctab, surf_names


# =============================================================================
# High-Level Functions
# =============================================================================

def sample_parcellation(
    surface_path: Path,
    segmentation_path: Path,
    cortex_path: Path,
    output_path: Path,
    volume_lut: Path,
    surface_lut: Path,
    proj_mm: float = 0.6,
    search_radius: float = 2.0,
    surface: Optional[SurfaceType] = None,
) -> None:
    """
    Sample volume parcellation onto surface and save annotation.

    Parameters
    ----------
    surface_path : Path
        Input surface file
    segmentation_path : Path
        Input segmentation volume
    cortex_path : Path
        Cortex label file
    output_path : Path
        Output annotation file
    volume_lut : Path
        Volume label lookup table
    surface_lut : Path
        Surface label lookup table
    proj_mm : float, default=0.6
        Projection distance along normal
    search_radius : float, default=2.0
        Search radius for zero samples
    surface : SurfaceType, optional
        Pre-loaded surface tuple (vertices, faces). If provided, surface_path is not loaded.
    """
    if surface is None:
        logger.info(f"Loading surface: {surface_path}")
        surface_data = fs.read_geometry(surface_path, read_metadata=True)
        # Extract only vertices and faces (ignore metadata)
        surface = (surface_data[0], surface_data[1])
    
    logger.info(f"Loading segmentation: {segmentation_path}")
    seg = nib.load(segmentation_path)
    
    logger.info(f"Loading cortex label: {cortex_path}")
    cortex = fs.read_label(cortex_path)
    
    # Sample volume
    logger.info("Sampling volume to surface...")
    vol_labels = sample_volume_to_surface(
        surface, seg, cortex, proj_mm, search_radius
    )
    
    # Translate labels
    logger.info("Translating labels...")
    surf_labels, ctab, names = translate_labels(vol_labels, volume_lut, surface_lut)
    
    # Find and remove islands
    logger.info("Finding label islands...")
    islands = find_label_islands(surface, surf_labels)
    surf_labels[islands] = 0
    
    # Smooth
    logger.info("Smoothing parcellation...")
    surf_labels = smooth_aparc(surface, surf_labels, cortex)
    
    # Ensure no labels outside cortex (safeguard before save)
    n_vertices = len(surf_labels)
    cortex_mask = np.zeros(n_vertices, dtype=bool)
    cortex_mask[cortex] = True
    surf_labels[~cortex_mask] = 0

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fs.write_annot(output_path, surf_labels, ctab=ctab, names=names)
    logger.info(f"Saved: {output_path}")


def smooth_aparc_files(
    insurf: Path,
    inaparc: Path,
    incort: Path,
    outaparc: Path,
    iterations: int = 10,
    surface: Optional[SurfaceType] = None,
) -> None:
    """
    Smooth surface parcellation from files.
    
    Wrapper around smooth_aparc() that handles file I/O.
    
    Parameters
    ----------
    insurf : Path
        Input surface file
    inaparc : Path
        Input annotation file
    incort : Path
        Input cortex label file
    outaparc : Path
        Output annotation file
    iterations : int, default=10
        Number of smoothing iterations
    surface : SurfaceType, optional
        Pre-loaded surface tuple (vertices, faces). If provided, insurf is not loaded.
    """
    if surface is None:
        logger.info(f"Loading surface: {insurf}")
        surface_data = fs.read_geometry(insurf, read_metadata=True)
        surface = (surface_data[0], surface_data[1])
    
    logger.info(f"Loading annotation: {inaparc}")
    aparc = fs.read_annot(inaparc)
    labels = aparc[0]
    ctab = aparc[1]
    names = aparc[2]
    
    logger.info(f"Loading cortex label: {incort}")
    cortex = fs.read_label(incort)
    
    # Smooth
    logger.info("Smoothing parcellation...")
    smoothed_labels = smooth_aparc(surface, labels, cortex, iterations=iterations)
    
    # Save
    outaparc.parent.mkdir(parents=True, exist_ok=True)
    fs.write_annot(outaparc, smoothed_labels, ctab=ctab, names=names)
    logger.info(f"Saved: {outaparc}")


__all__ = [
    # Mesh operations
    "get_adjacency_matrix",
    "get_cluster_adjacency",
    "find_label_islands",
    # Smoothing
    "mode_filter",
    "smooth_aparc",
    # Sampling
    "sample_volume_to_surface",
    "translate_labels",
    # High-level
    "sample_parcellation",
    "smooth_aparc_files",
]

