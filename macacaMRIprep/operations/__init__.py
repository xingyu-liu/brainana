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
    precheck,
    slice_timing_correction,
    motion_correction,
    despike,
    apply_skullstripping,
    bias_correction
)

# Import registration functions
from .registration import (
    ants_register,
    ants_apply_transforms,
    compose_ants_registration_cmd,
    compose_transform_cmd
)

# Import pipeline functionality
from .pipeline import (
    Pipeline
)

__all__ = [
    # Validation
    'validate_input_file',
    'ensure_working_directory', 
    'validate_output_file',
    
    # Preprocessing (functional + anatomical)
    'precheck',
    'slice_timing_correction',
    'motion_correction',
    'despike',
    'apply_skullstripping',
    'bias_correction',
    
    # Registration
    'ants_register',
    'ants_apply_transforms',
    'ants_apply_transform_func2template',
    'compose_ants_registration_cmd',
    'compose_transform_cmd',
    
    # Pipeline
    'Pipeline',
    'PipelineStep',
    'StepStatus'
] 