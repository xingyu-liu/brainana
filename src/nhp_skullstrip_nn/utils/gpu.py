"""
GPU utilities for device selection.

Re-exports from nhp_mri_prep.utils.gpu_device for centralized device management.
"""

from nhp_mri_prep.utils.gpu_device import (
    resolve_device,
    get_device,
    setup_device,
)

__all__ = ["resolve_device", "get_device", "setup_device"]
