"""
I/O utilities for FastSurfer surface reconstruction.

Handles reading/writing of images, surfaces, and FreeSurfer directory structures.
"""

from .subjects_dir import SubjectsDir
from .image import read_image, write_image, mgh_from_sitk, sitk_from_mgh
from .lta import read_lta, write_lta
from .surface import convert_fs_surface_to_gifti

__all__ = [
    "SubjectsDir",
    # Image I/O
    "read_image",
    "write_image",
    "mgh_from_sitk",
    "sitk_from_mgh",
    # LTA I/O
    "read_lta",
    "write_lta",
    # Surface I/O
    "convert_fs_surface_to_gifti",
]
