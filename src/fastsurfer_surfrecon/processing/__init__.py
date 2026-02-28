"""
Core processing functions for FastSurfer surface reconstruction.

This module contains the computational functions that perform
the actual image and surface processing operations.
"""

# Bias correction
from .bias_correction import (
    n4_bias_correction,
    normalize_intensity,
    normalize_wm_from_aseg,
    normalize_wm_from_centroid,
    get_brain_centroid,
    read_talairach_xfm,
    get_talairach_origin_voxel,
    bias_correct_and_normalize,
)

# Segmentation
from .segmentation import (
    create_wm_segmentation,
    create_wm_from_file,
    paint_corpus_callosum,
    paint_cc_from_pred,
)

# Parcellation
from .parcellation import (
    get_adjacency_matrix,
    get_cluster_adjacency,
    find_label_islands,
    mode_filter,
    smooth_aparc,
    sample_volume_to_surface,
    translate_labels,
    sample_parcellation,
)

# Spherical projection
from .spherical import (
    spherically_project,
    compute_rotation_angles,
    spherically_project_surface,
    compute_sphere_rotation,
)

# Surface fixes
from .surface_fix import (
    fix_mc_surface_header,
    fix_surface_orientation,
    verify_surface_ras,
    validate_surface,
)

__all__ = [
    # Bias correction
    "n4_bias_correction",
    "normalize_intensity",
    "normalize_wm_from_aseg",
    "normalize_wm_from_centroid",
    "get_brain_centroid",
    "read_talairach_xfm",
    "get_talairach_origin_voxel",
    "bias_correct_and_normalize",
    # Segmentation
    "create_wm_segmentation",
    "create_wm_from_file",
    "paint_corpus_callosum",
    "paint_cc_from_pred",
    # Parcellation
    "get_adjacency_matrix",
    "get_cluster_adjacency",
    "find_label_islands",
    "mode_filter",
    "smooth_aparc",
    "sample_volume_to_surface",
    "translate_labels",
    "sample_parcellation",
    # Spherical
    "spherically_project",
    "compute_rotation_angles",
    "spherically_project_surface",
    "compute_sphere_rotation",
    # Surface fixes
    "fix_mc_surface_header",
    "fix_surface_orientation",
    "verify_surface_ras",
    "validate_surface",
]
