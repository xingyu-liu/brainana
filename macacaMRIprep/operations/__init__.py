"""
Core preprocessing functions for macacaMRIprep.

This module provides a clean interface to all preprocessing steps,
organized into logical submodules for better maintainability.
"""

# Import validation utilities
from .validation import (
    validate_input_file,
    ensure_working_directory,
    validate_output_file
)

# Import all preprocessing steps (functional, anatomical, and shared)
from .preprocessing import (
    reorient,
    correct_orientation_mismatch,
    slice_timing_correction,
    motion_correction,
    despike,
    apply_segmentation,
    apply_skullstripping,
    bias_correction,
    conform_to_template
)

# Import registration functions
from .registration import (
    ants_register,
    ants_apply_transforms,
    compose_ants_registration_cmd,
    compose_transform_cmd
)

# Import synthesis functions
from .synthesis_multiple_anat import (
    synthesize_multiple_anatomical
)

__all__ = [
    # Validation
    'validate_input_file',
    'ensure_working_directory', 
    'validate_output_file',
    
    # Preprocessing (functional + anatomical)
    'reorient',
    'correct_orientation_mismatch',
    'slice_timing_correction',
    'motion_correction',
    'despike',
    'apply_segmentation',
    'apply_skullstripping',
    'bias_correction',
    'conform_to_template',
    
    # Registration
    'ants_register',
    'ants_apply_transforms',
    'ants_apply_transform_func2template',
    'compose_ants_registration_cmd',
    'compose_transform_cmd',
    
    # Synthesis
    'synthesize_multiple_anatomical',
] 