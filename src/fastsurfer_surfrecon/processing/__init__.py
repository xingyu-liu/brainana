"""
Core processing functions for FastSurfer surface reconstruction.

This module contains the computational functions that perform
the actual image and surface processing operations.

Dependency import policy
------------------------
Rule A -- declared core dependencies (numpy, scipy, nibabel, lapy, pymeshfix)
are imported unguarded at module scope. Never wrap them in
``try/except ImportError``. A missing core dependency is a corrupt
environment: it must fail at import, in the first second, not degrade into a
warning that surfaces hours into a run.

Rule B -- genuinely optional dependencies get a guarded import, a module-level
capability flag, and an explicit log at the fallback -- and the fallback must
be correctness-equivalent, differing only in cost. ``spherical.py``'s
scikit-sparse/CHOLMOD fallback is the reference implementation. If a fallback
would change *results*, the dependency is not optional; promote it to Rule A.

Rule C -- never rely on a transitive *optional* dependency of a dependency.
``pymeshfix.MeshFix`` is unusable without pyvista, which is only a
``pymeshfix[extras]`` dependency that no resolver installs for us. Use the
pyvista-free ``pymeshfix._meshfix.PyTMesh`` API instead (see
``topology_fix.py``). A grep for ``import pyvista`` cannot see this class of
requirement, which is why it must be covered by a test that actually calls the
third-party API rather than merely importing it.
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
    assert_surface_invariants,
    SurfaceInvariantError,
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
    "assert_surface_invariants",
    "SurfaceInvariantError",
]
