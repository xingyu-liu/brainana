##########################################################################
# NSAp - Copyright (C) CEA, 2016
# Distributed under the terms of the CeCILL-B license, as published by
# the CEA-CNRS-INRIA. Refer to the LICENSE file or to
# http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html
# for details.
##########################################################################

"""
MacacaMRIprep - A Python package for preprocessing and registration of macaque MRI data.

This package provides tools for:
1. Preprocessing of functional and anatomical MRI data
2. Registration between different spaces (functional, anatomical, template)
3. Quality control and visualization
4. Pipeline management and configuration

The core functionality is now organized into modular components:
- core.functional: Functional MRI preprocessing steps
- core.shared: Shared preprocessing steps (skull stripping, bias correction)
- core.registration: Image registration functions
- core.validation: Input/output validation utilities
"""

# Get version from pyproject.toml
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib

def _get_version_from_pyproject() -> str:
    """Get version from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
        return data["project"]["version"]

__version__ = _get_version_from_pyproject()

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

__author__ = 'Your Name'
__email__ = 'your.email@example.com'
__license__ = 'MIT'
__status__ = 'Development'

# Package metadata
PACKAGE_DESCRIPTION = 'A Python package for preprocessing and registration of neuroimaging data'
PACKAGE_AUTHOR = 'Your Name'
PACKAGE_EMAIL = 'your.email@example.com'
PACKAGE_CLASSIFIERS = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.11',
    'Programming Language :: Python :: 3.12',
    'Topic :: Scientific/Engineering :: Medical Science Apps.',
]

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

# Note: Package info display can be enabled by setting environment variable MACACAMRIPREP_VERBOSE=1
import os
if os.environ.get('MACACAMRIPREP_VERBOSE', '0') == '1':
    # Use logging instead of print for consistency
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"System: macacaMRIprep v{__version__} - Macaque MRI preprocessing package")