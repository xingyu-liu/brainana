"""
Registration functions for macacaMRIprep.

This module contains functions for image registration using ANTs,
including command composition and transformation application.
"""

import os
import logging
from typing import Dict, Any, Optional, Union, List
from pathlib import Path

from .validation import validate_input_file, ensure_working_directory, validate_output_file
from ..utils import run_command, calculate_func_tmean
from ..config import get_config

# Default registration step parameters (hardcoded)
REGISTRATION_STEP_DEFAULTS = {
    "translation": {
        "gradient_step": "[0.1]",
        "metric": ["MI[fixed,moving,1,32,regular,0.25]"],
        "shrink": "8x4x2x1",
        "convergence": "[1000x500x250x100,1e-6,10]",
        "smooth": "3x2x1x0vox"
    },
    "rigid": {
        "gradient_step": "[0.1]",
        "metric": ["MI[fixed,moving,1,32,regular,0.25]"],
        "shrink": "8x4x2x1",
        "convergence": "[1000x500x250x100,1e-6,10]",
        "smooth": "3x2x1x0vox"
    },
    "affine": {
        "gradient_step": "[0.1]",
        "metric": ["MI[fixed,moving,1,32,regular,0.25]"],
        "shrink": "8x4x2x1",
        "convergence": "[1000x500x250x100,1e-6,10]",
        "smooth": "3x2x1x0vox"
    },
    "syn": {
        "gradient_step": "[0.1,3,0]",
        "metric": [
            "mattes[fixed,moving,0.5,32,regular,0.3]",
            "cc[fixed,moving,0.5,4,regular,0.3]"
        ],
        "shrink": "4x2x1",
        "convergence": "[500x300x100,1e-8,10]",
        "smooth": "1x0.5x0vox"
    }
}

# %% 
def compose_transform_cmd(
    transform: str, 
    config: Dict[str, Any], 
    fixedf: Union[str, Path], 
    movingf: Union[str, Path]
) -> List[str]:
    """Compose ANTs transform command arguments.
    
    Args:
        transform: Transform type
        config: Transform configuration
        fixedf: Fixed image path
        movingf: Moving image path
        
    Returns:
        List of command arguments
    """
    cmd = [
        "--transform", f"{transform}{config.get('gradient_step')}",
        "--convergence", f"{config.get('convergence')}",
        "--shrink-factors", f"{config.get('shrink')}",
        "--smoothing-sigmas", f"{config.get('smooth')}"
    ]
    
    # Add metrics
    for metric in config.get('metric'):
        metric_str = metric.replace('fixed', str(fixedf)).replace('moving', str(movingf))
        cmd.extend(["--metric", metric_str])

    return cmd

def compose_ants_registration_cmd(
    fixedf: Union[str, Path],
    movingf: Union[str, Path],
    output_path_prefix: str,
    config: Dict[str, Any],
    xfm_type: str = 'affine'
) -> List[str]:
    """Compose ANTs registration command arguments.
    
    Args:
        fixedf: Fixed (template) image path
        movingf: Moving image path
        config: Registration configuration
        xfm_type: Type of transformation to perform. Options: 'translation', 'rigid', 'affine', 'syn'
        
    Returns:
        List of command arguments
    """    
    cmd = [
        'antsRegistration',
        '--dimensionality', '3',
        '--float', '0',
        '--interpolation', config.get('interpolation'),
        '--use-histogram-matching', '0',
        '--initial-moving-transform', f"[{str(fixedf)},{str(movingf)},1]",
        '--winsorize-image-intensities', '[0.005,0.995]',
        '--output', f"[{output_path_prefix}_,{output_path_prefix}_registered.nii.gz]",
        '--write-composite-transform', '1',
        
    ]

    # Define the order of transformation stages
    stages = ['translation', 'rigid', 'affine', 'syn']
    
    # Find the index of the xfm_type
    try:
        xfm_index = stages.index(xfm_type)
    except ValueError:
        raise ValueError(f"Invalid xfm_type value: {xfm_type}. Must be one of {stages}")
    
    # Enable initialize-transforms-per-stage when multiple linear stages are used
    # This allows each linear stage to initialize from the previous stage's transform
    # (e.g., Translation -> Rigid -> Affine)
    if xfm_index >= 1:  # More than just translation (rigid, affine, or syn)
        cmd.extend(['--initialize-transforms-per-stage', '1'])
        # disable collapse-output-transforms when initialize-transforms-per-stage is enabled
        cmd.extend(['--collapse-output-transforms', '0'])
    else:
        cmd.extend(['--collapse-output-transforms', '1'])
    
    # Add transformation stages up to and including the xfm_type
    for i, stage_name in enumerate(stages):
        if i > xfm_index:
            break
        # Use hardcoded defaults for registration step parameters
        stage_config = REGISTRATION_STEP_DEFAULTS.get(stage_name)
        if stage_config is None:
            raise ValueError(f"Unknown registration stage: {stage_name}")
        stage_cmd = compose_transform_cmd(stage_name, stage_config, fixedf, movingf)
        cmd.extend(stage_cmd)
    
    return cmd

def ants_register(
    fixedf: Union[str, Path],
    movingf: Union[str, Path],
    working_dir: Union[str, Path],
    output_prefix: str,
    config: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    xfm_type: Optional[str] = 'syn'
) -> Dict[str, str]:
    """Run ANTs registration.
    
    Args:
        fixedf: Fixed (template) image path
        movingf: Moving image path
        working_dir: Working directory
        output_prefix: Prefix for output files
        config: Configuration dictionary (optional, will use default if not provided)
        logger: Logger instance (optional, will create if not provided)
        xfm_type: Type of transformation to perform. Options: 'translation', 'rigid', 'affine', 'syn'
        
    Returns:
        Dictionary containing paths to output files
        
    Raises:
        FileNotFoundError: If input files don't exist
        RuntimeError: If registration fails
        ValueError: If configuration is invalid
    """
    # Use provided config/logger or get defaults
    if config is None:
        config = get_config().to_dict()
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs and setup
    work_dir = ensure_working_directory(working_dir, logger)
    output_path_prefix = os.path.join(str(work_dir), output_prefix)
    logger.info(f"Data: output prefix - {output_prefix}")
    
    # Get registration configuration with proper nesting access
    reg_config = config.get("registration")
    if not reg_config:
        raise ValueError("Registration configuration not found in config")

    # Validate input files
    fixed_path = validate_input_file(fixedf, logger)
    moving_path = validate_input_file(movingf, logger)

    # Initialize outputs dictionary
    outputs = {
        "output_path_prefix": output_path_prefix,
        'imagef_registered': None,
        'forward_transform': None,
        'inverse_transform': None,
    }

    # Get thread count from config, default to 8 to avoid oversubscription when running multiple processes
    num_threads = reg_config.get('threads', 8)
    
    # Set up ITK thread environment variables
    from ..utils.system import setup_itk_thread_env
    env = setup_itk_thread_env(num_threads)

    # Build ANTs registration command
    command_ants = compose_ants_registration_cmd(
        fixed_path, moving_path, output_path_prefix, 
        reg_config, xfm_type=xfm_type)
    # Normalize verbose to integer (0, 1, or 2) and convert to ANTs format (0 or 1)
    from ..utils.logger import normalize_verbose
    verbose = normalize_verbose(config.get('general', {}).get('verbose', 1))
    command_ants.extend(['--verbose', str(1 if verbose >= 1 else 0)])

    # Execute ANTs registration with thread-limited environment
    try:
        logger.info(f"Step: executing ANTs registration command with {len(command_ants)} arguments")
        logger.info(f"System: using {num_threads} threads for ITK operations (capped at 32)")
        returncode, stdout, stderr = run_command(command_ants, env=env, step_logger=logger)
        
        if returncode != 0:
            raise RuntimeError(f"antsRegistration failed (exit code {returncode}): {stderr}")
        
        logger.info("Step: ANTs registration completed successfully")
        
    except Exception as e:
        logger.error(f"Step: ANTs registration failed - {str(e)}")
        raise
    
    # Collect and validate output files (outputs dict already initialized above)
    
    # Main registered image
    registered_image = os.path.join(os.path.dirname(output_path_prefix), 
                               os.path.basename(output_path_prefix) + "_registered.nii.gz")
    if os.path.exists(registered_image):
        validate_output_file(registered_image, logger)
        outputs["imagef_registered"] = registered_image
        logger.info(f"Output: registered image created - {registered_image}")
    else:
        logger.warning(f"Data: expected registered image not found - {registered_image}")
    
    # Transform files
    forward_transform = os.path.join(os.path.dirname(output_path_prefix),
                                   os.path.basename(output_path_prefix) + "_Composite.h5")
    if os.path.exists(forward_transform):
        outputs["forward_transform"] = forward_transform
        logger.info(f"Output: forward transform created - {forward_transform}")
    
    inverse_transform = os.path.join(os.path.dirname(output_path_prefix),
                                   os.path.basename(output_path_prefix) + "_InverseComposite.h5")
    if os.path.exists(inverse_transform):
        outputs["inverse_transform"] = inverse_transform
        logger.info(f"Output: inverse transform created - {inverse_transform}")
    
    logger.info(f"Step: registration completed with {len(outputs)} output files - {list(outputs.keys())}")
    return outputs

def ants_apply_transforms(
    movingf: Union[str, Path],
    moving_type: int,
    interpolation: str,
    outputf_name: Union[str, Path],
    fixedf: Union[str, Path],
    working_dir: Union[str, Path],
    transformf: Union[list[Union[str, Path]], Union[str, Path]],
    logger: Optional[logging.Logger] = None,
    reff: Optional[Union[str, Path]] = None,
    generate_tmean: Optional[bool] = True
) -> Dict[str, str]:
    
    """Apply ANTs transformations to functional data.
    
    Args:
        movingf: Moving (source) functional image
        moving_type: Type of moving image (0:scalar, 1:vector, 2:tensor, 3:time series)
        interpolation: Interpolation type
        outputf_name: Name for output file
        fixedf: Fixed (target) image
        working_dir: Working directory for outputs
        transformf: List of transformation files to apply (ANTs transforms)
        logger: Logger instance
        reff: Reference image for output space (optional)
        generate_tmean: Whether to generate temporal mean
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input files don't exist
        RuntimeError: If transformation application fails
    """
    # Validate inputs
    if logger is None:
        logger = logging.getLogger(__name__)
        
    movingf = validate_input_file(movingf, logger)
    fixedf = validate_input_file(fixedf, logger)
    if reff is not None:
        reff = validate_input_file(reff, logger)
    work_dir = ensure_working_directory(working_dir, logger)

    outputf_name = work_dir / outputf_name

    # Ensure transformf is a list
    if not isinstance(transformf, list):
        transformf = [transformf]

    # Apply ANTs transformations
    cmd = [
        "antsApplyTransforms",
        "-d", "3", "-e", str(moving_type),
        "--input", str(movingf),
        "--output", str(outputf_name),
        "--interpolation", interpolation
    ]

    if reff is not None:
        cmd.extend(["--reference-image", str(reff)])
    else:
        cmd.extend(["--reference-image", str(fixedf)])
        
    # Add transformation files in reverse order because ANTs applies transforms from right to left
    # i.e. the last transform in the command is applied first to the moving image
    for transform_file in reversed(transformf):
        cmd.extend(["--transform", str(transform_file)])
    
    logger.debug(f"System: apply transforms command - {' '.join(cmd)}")
    
    # Get thread count from config if available, default to 8
    num_threads = 8
    try:
        config = get_config().to_dict()
        reg_config = config.get("registration", {})
        num_threads = reg_config.get('threads', 8)
    except Exception:
        pass  # Use default if config access fails
    
    # Set up ITK thread environment variables
    from ..utils.system import setup_itk_thread_env
    env = setup_itk_thread_env(num_threads)
    
    logger.debug(f"System: using {num_threads} threads for ITK operations (capped at 32)")
    
    try:
        run_command(cmd, env=env, step_logger=logger)
        
        # Validate output
        validate_output_file(outputf_name, logger)
        
        outputs = {"imagef_registered": str(outputf_name)}
        logger.info(f"Step: transform application completed successfully - {outputf_name}")
        
        # Generate temporal mean if requested
        if generate_tmean:
            tmean_file = work_dir / Path(str(outputf_name).replace('.nii.gz', '_tmean.nii.gz'))
            calculate_func_tmean(str(outputf_name), str(tmean_file), logger)
            outputs["imagef_registered_tmean"] = str(tmean_file)
            logger.info(f"Output: tmean generated - {tmean_file}")
        
        return outputs
        
    except Exception as e:
        logger.error(f"Step: transform application failed - {e}")
        raise RuntimeError(f"Transform application failed: {e}")

# %%
