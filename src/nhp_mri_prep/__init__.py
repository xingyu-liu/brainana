"""
nhp_mri_prep - NHP MRI preprocessing and registration (brainana package).

This package provides tools for:
1. Preprocessing of functional and anatomical MRI data
2. Registration between different spaces (functional, anatomical, template)
3. Quality control and visualization
4. Pipeline management and configuration

Structure:
- operations: Preprocessing, registration, validation, synthesis (preprocessing.py, registration.py, validation.py, synthesis_multiple_anat.py)
- quality_control: QC reports and snapshots
- config: Configuration (Config, defaults, BIDS adapter)
- utils: Logging, BIDS helpers, MRI utilities, templates
- steps: Step logic for Nextflow (functional.py, anatomical.py, qc.py, bids_discovery.py)
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("brainana")
except PackageNotFoundError:
    __version__ = "0.0.0"

# Note: Package metadata (author, email, classifiers) is defined in pyproject.toml
# No need to duplicate it here - use `importlib.metadata` if needed at runtime

# Import core functionality - unified preprocessing module
from .operations import (
    reorient,
    slice_timing_correction,
    motion_correction,
    despike,
    apply_segmentation,
    apply_skullstripping,
    bias_correction,
    ants_register,
    ants_apply_transforms,
    compose_ants_registration_cmd,
    compose_transform_cmd,
)

# Import quality control functionality
from .quality_control import (
    create_motion_correction_qc,
    create_skullstripping_qc,
    create_registration_qc,
    create_bias_correction_qc,
    generate_qc_report,
)


# Import configuration functionality
from .config import (
    Config,
    load_config,
    get_config
)

# Import utility functions
from .utils import run_command, setup_logging, get_logger

__all__ = [
    '__version__',
    # Functional preprocessing
    'slice_timing_correction',
    'motion_correction',
    'despike',
    'apply_segmentation',
    'apply_skullstripping',
    # Shared preprocessing
    'bias_correction',
    # Quality control
    'create_motion_correction_qc',
    'create_skullstripping_qc',
    'create_registration_qc',
    'create_bias_correction_qc',
    'generate_qc_report',
    'generate_report',     # backward compatibility
    # Registration
    'ants_register',
    # Configuration
    'Config',
    'load_config',
    'get_config',
    # Utilities
    'run_command',
    'setup_logging',
    'get_logger'
]

# Note: Package info display can be enabled by setting environment variable NHP_MRI_PREP_VERBOSE=1
import os
if os.environ.get('NHP_MRI_PREP_VERBOSE', '0') == '1':
    # Use logging instead of print for consistency
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"System: nhp_mri_prep v{__version__} (brainana) - NHP MRI preprocessing package")