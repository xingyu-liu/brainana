"""
Utility functions for nhp_mri_prep.

This module provides system utilities (command execution and logging).
"""

from .system import run_command, check_dependency, set_numerical_threads
from .logger import (
    setup_logging, 
    get_logger,
    setup_step_logging,
    setup_workflow_logging,
    ensure_workflow_log_exists,
    log_workflow_start,
    log_workflow_end,
    log_step_start,
    log_step_end,
    normalize_verbose,
    verbose_to_log_level
)
from .mri import (
    calculate_func_tmean, 
    reorient_image_to_target,
    reorient_image_to_orientation,
    get_image_orientation,
    get_image_shape, 
    get_image_resolution
)
from .templates import (
    resolve_template,
    resolve_template_file,
    list_available_templates,
    validate_template_spec,
    print_available_templates,
    get_template_manager
)
from .bids import (
    parse_bids_entities,
    create_bids_filename,
    create_bids_output_filename,
    get_filename_stem,
    find_bids_metadata,
    BIDS_ENTITY_ORDER
)
from .nextflow import create_output_link
from .gpu_device import resolve_device, get_device, setup_device

__all__ = [
    'run_command',
    'check_dependency',
    'set_numerical_threads',
    'setup_logging', 'get_logger', 'setup_step_logging', 'setup_workflow_logging', 'log_workflow_start', 'log_workflow_end',
    'log_step_start', 'log_step_end', 'ensure_workflow_log_exists', 'normalize_verbose', 'verbose_to_log_level',
    'calculate_func_tmean', 'reorient_image_to_target', 'reorient_image_to_orientation', 'get_image_orientation', 'get_image_shape', 'get_image_resolution',
    'resolve_template', 'resolve_template_file', 'list_available_templates', 'validate_template_spec',
    'print_available_templates', 'get_template_manager',
    'parse_bids_entities', 'create_bids_filename', 'create_bids_output_filename', 'get_filename_stem', 'find_bids_metadata', 'BIDS_ENTITY_ORDER',
    'create_output_link',
    'resolve_device', 'get_device', 'setup_device',
] 