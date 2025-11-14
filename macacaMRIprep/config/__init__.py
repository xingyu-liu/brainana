"""
Modern configuration management for macacaMRIprep.

This module provides a clean, modern API for configuration management with:
- Multiple file format support (JSON, YAML)
- Dot notation access (config.get('func.motion_correction.enabled'))
- BIDS metadata adaptation
- Configuration validation
- No global state dependencies

Examples:
    Basic usage:
        >>> from macacaMRIprep.config import load_config
        >>> config = load_config('my_config.yaml')
        >>> config.get('func.motion_correction.enabled')
        True

    Creating from dictionary:
        >>> config = Config({'general': {'verbose': 2}})
        >>> config.save('output.yaml')

    BIDS adaptation:
        >>> config.adapt_from_bids(bids_metadata)
"""
# Import from available modules
from .config_io import load_config, get_default_config
from .config import Config, get_config
from .config_validation import validate_config, validate_slice_timing_config
from .bids_adapter import update_config_from_bids_metadata


# For backward compatibility with old config module
DEFAULT_CONFIG = get_default_config()

__all__ = [
    'Config',
    'load_config',
    'get_config',
    'DEFAULT_CONFIG',
    'validate_config',
    'update_config_from_bids_metadata',
    'validate_slice_timing_config',
]