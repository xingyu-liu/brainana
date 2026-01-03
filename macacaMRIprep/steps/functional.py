"""
Standalone functional processing step functions.

These functions wrap the existing operations to provide standardized
inputs/outputs for Nextflow integration.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .types import StepInput, StepOutput
from ..operations.preprocessing import (
    reorient,
    slice_timing_correction,
    motion_correction,
    despike,
    bias_correction,
    conform_to_template,
    apply_skullstripping
)
from ..operations.registration import ants_register, ants_apply_transforms, flirt_apply_transforms
from ..utils import get_image_resolution, calculate_func_tmean
from ..utils import run_command
import numpy as np

logger = logging.getLogger(__name__)


def func_reorient(input: StepInput, template_file: Optional[Path] = None) -> StepOutput:
    """
    Reorient functional image to template orientation or RAS, and generate tmean.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        template_file: Optional template file for reorientation target
        
    Returns:
        StepOutput with reoriented file and tmean
    """
    if not input.config.get("func.reorient.enabled", True):
        logger.info("Step: reorient skipped (disabled in configuration)")
        # Still generate tmean from original
        tmean_path = input.working_dir / "func_tmean.nii.gz"
        calculate_func_tmean(str(input.input_file), str(tmean_path), logger)
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "reorient", "skipped": True},
            additional_files=[tmean_path]
        )
    
    # Determine target for reorientation
    target_file = None
    target_orientation = None
    
    if template_file:
        target_file = str(template_file)
    else:
        target_orientation = "RAS"
    
    # Call operation (with tmean generation)
    result = reorient(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "func_reoriented.nii.gz",
        logger=logger,
        target_file=target_file,
        target_orientation=target_orientation,
        generate_tmean=True
    )
    
    output_file = Path(result["imagef_reoriented"]) if result.get("imagef_reoriented") else input.input_file
    tmean_file = Path(result["imagef_tmean"]) if result.get("imagef_tmean") else None
    
    additional_files = []
    if tmean_file:
        additional_files.append(tmean_file)
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "reorient",
            "modality": "func",
            "target_file": str(template_file) if template_file else None,
            "target_orientation": target_orientation
        },
        additional_files=additional_files
    )


def func_slice_timing_correction(input: StepInput) -> StepOutput:
    """
    Perform slice timing correction on functional image.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        
    Returns:
        StepOutput with slice-timed file and tmean
    """
    if not input.config.get("func.slice_timing_correction.enabled", True):
        logger.info("Step: slice timing correction skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "slice_timing_correction", "skipped": True}
        )
    
    # Call operation
    result = slice_timing_correction(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "func_slice_timed.nii.gz",
        config=input.config,
        logger=logger,
        generate_tmean=True
    )
    
    output_file = Path(result["imagef_slice_time_corrected"]) if result.get("imagef_slice_time_corrected") else input.input_file
    tmean_file = Path(result["imagef_slice_time_corrected_tmean"]) if result.get("imagef_slice_time_corrected_tmean") else None
    
    additional_files = []
    if tmean_file:
        additional_files.append(tmean_file)
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "slice_timing_correction",
            "modality": "func"
        },
        additional_files=additional_files
    )


def func_motion_correction(input: StepInput) -> StepOutput:
    """
    Perform motion correction on functional image.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        
    Returns:
        StepOutput with motion-corrected file, tmean, and motion parameters
    """
    if not input.config.get("func.motion_correction.enabled", True):
        logger.info("Step: motion correction skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "motion_correction", "skipped": True}
        )
    
    # Call operation
    result = motion_correction(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "func_motion_corrected.nii.gz",
        config=input.config,
        logger=logger,
        generate_tmean=True
    )
    
    output_file = Path(result["imagef_motion_corrected"]) if result.get("imagef_motion_corrected") else input.input_file
    tmean_file = Path(result["imagef_motion_corrected_tmean"]) if result.get("imagef_motion_corrected_tmean") else None
    motion_params = Path(result["motion_parameters"]) if result.get("motion_parameters") else None
    
    additional_files = []
    if tmean_file:
        additional_files.append(tmean_file)
    if motion_params:
        additional_files.append(motion_params)
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "motion_correction",
            "modality": "func",
            "dof": input.config.get("func", {}).get("motion_correction", {}).get("dof", 6)
        },
        additional_files=additional_files
    )


def func_despike(input: StepInput) -> StepOutput:
    """
    Perform despiking on functional image.
    
    Args:
        input: StepInput with input_file, working_dir, config, metadata
        
    Returns:
        StepOutput with despiked file and tmean
    """
    if not input.config.get("func.despike.enabled", True):
        logger.info("Step: despiking skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "despike", "skipped": True}
        )
    
    # Call operation
    result = despike(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "func_despiked.nii.gz",
        config=input.config,
        logger=logger,
        generate_tmean=True
    )
    
    output_file = Path(result["imagef_despiked"]) if result.get("imagef_despiked") else input.input_file
    tmean_file = Path(result["imagef_despiked_tmean"]) if result.get("imagef_despiked_tmean") else None
    
    additional_files = []
    if tmean_file:
        additional_files.append(tmean_file)
    if result.get("spikiness_map"):
        additional_files.append(Path(result["spikiness_map"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "despike",
            "modality": "func"
        },
        additional_files=additional_files
    )


def func_bias_correction(input: StepInput) -> StepOutput:
    """
    Perform bias field correction on functional tmean image.
    
    Note: This operates on the tmean image, not the full 4D BOLD.
    
    Args:
        input: StepInput with input_file (should be tmean), working_dir, config, metadata
        
    Returns:
        StepOutput with bias-corrected tmean file
    """
    if not input.config.get("func.bias_correction.enabled", True):
        logger.info("Step: bias correction skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "bias_correction", "skipped": True}
        )
    
    # Call operation
    result = bias_correction(
        imagef=str(input.input_file),
        working_dir=str(input.working_dir),
        modal="func",
        output_name=input.output_name or "func_bias_corrected.nii.gz",
        config=input.config,
        logger=logger
    )
    
    output_file = Path(result["imagef_bias_corrected"])
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "bias_correction",
            "modality": "func",
            "algorithm": input.config.get("func", {}).get("bias_correction", {}).get("algorithm", "N4BiasFieldCorrection")
        }
    )


def func_conform(input: StepInput, target_file: Path) -> StepOutput:
    """
    Conform functional tmean image to target space.
    
    Args:
        input: StepInput with input_file (tmean), working_dir, config, metadata
        target_file: Target file for conforming (anatomical or template)
        
    Returns:
        StepOutput with conformed tmean file and transform files
    """
    if not input.config.get("func.conform.enabled", True):
        logger.info("Step: conform skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "conform", "skipped": True}
        )
    
    # Check if skullstripping is disabled
    skip_skullstripping = not input.config.get("func.skullstripping.enabled", True)
    
    # Call operation
    result = conform_to_template(
        imagef=str(input.input_file),
        template_file=str(target_file),
        working_dir=str(input.working_dir),
        output_name=input.output_name or "func_tmean_conformed.nii.gz",
        logger=logger,
        modal="func",
        skip_skullstripping=skip_skullstripping
    )
    
    output_file = Path(result["imagef_conformed"]) if result.get("imagef_conformed") else input.input_file
    additional_files = []
    
    if result.get("forward_xfm"):
        additional_files.append(Path(result["forward_xfm"]))
    if result.get("inverse_xfm"):
        additional_files.append(Path(result["inverse_xfm"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "conform",
            "modality": "func",
            "target_file": str(target_file)
        },
        additional_files=additional_files
    )


def func_skullstripping(input: StepInput) -> StepOutput:
    """
    Perform skull stripping on functional tmean image.
    
    Args:
        input: StepInput with input_file (tmean), working_dir, config, metadata
        
    Returns:
        StepOutput with skull-stripped tmean file and brain mask
    """
    if not input.config.get("func.skullstripping.enabled", True):
        logger.info("Step: skull stripping skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "skullstripping", "skipped": True}
        )
    
    # Call operation
    result = apply_skullstripping(
        imagef=str(input.input_file),
        modal="func",
        working_dir=str(input.working_dir),
        output_name=input.output_name or "func_brain.nii.gz",
        config=input.config,
        logger=logger
    )
    
    output_file = Path(result["imagef_skullstripped"])
    additional_files = []
    
    if result.get("brain_mask"):
        additional_files.append(Path(result["brain_mask"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "skullstripping",
            "modality": "func",
            "method": "NHPskullstripNN"
        },
        additional_files=additional_files
    )


def func_registration(
    input: StepInput,
    target_file: Path,
    target_type: str  # 'anat' or 'template'
) -> StepOutput:
    """
    Register functional tmean image to target (anatomical or template).
    
    Args:
        input: StepInput with input_file (tmean), working_dir, config, metadata
        target_file: Target file for registration
        target_type: Type of target ('anat' or 'template')
        
    Returns:
        StepOutput with registered tmean file and transform files
    """
    if not input.config.get("registration.enabled", True):
        logger.info("Step: registration skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "registration", "skipped": True}
        )
    
    # Get transform type from config
    config_key = f"func2{target_type}_xfm_type"
    xfm_type = input.config.get("registration", {}).get(config_key, "syn")
    
    # Resample target to functional resolution if requested
    fixedf = str(target_file)
    if input.config.get("registration.keep_original_func_resolution", True):
        func_res = np.round(get_image_resolution(str(input.input_file), logger=logger), 1)
        reff = input.working_dir / "target_res-func_for_registration.nii.gz"
        cmd_resample = [
            '3dresample',
            '-input', str(target_file),
            '-prefix', str(reff),
            '-rmode', 'Cu',
            '-dxyz', str(func_res[0]), str(func_res[1]), str(func_res[2])
        ]
        run_command(cmd_resample, step_logger=logger)
        fixedf = str(reff)
        logger.info(f"Output: target resampled to func resolution for registration")
    
    # Call operation
    result = ants_register(
        movingf=str(input.input_file),
        fixedf=fixedf,
        working_dir=str(input.working_dir),
        output_prefix=f"func2{target_type}_tmean",
        config=input.config,
        logger=logger,
        xfm_type=xfm_type
    )
    
    output_file = Path(result["imagef_registered"])
    additional_files = []
    
    if result.get("forward_transform"):
        additional_files.append(Path(result["forward_transform"]))
    if result.get("inverse_transform"):
        additional_files.append(Path(result["inverse_transform"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "registration",
            "modality": "func",
            "target_type": target_type,
            "xfm_type": xfm_type
        },
        additional_files=additional_files
    )


def func_apply_transforms(
    input: StepInput,
    transform_files: List[Path],
    reference_file: Path,
    interpolation: Optional[str] = None
) -> StepOutput:
    """
    Apply transforms to full 4D functional BOLD image.
    
    Args:
        input: StepInput with input_file (full 4D BOLD), working_dir, config, metadata
        transform_files: List of transform files to apply
        reference_file: Reference file for resampling
        interpolation: Interpolation method (default from config)
        
    Returns:
        StepOutput with registered 4D BOLD file and tmean
    """
    if interpolation is None:
        interpolation = input.config.get("registration", {}).get("interpolation", "LanczosWindowedSinc")
    
    # Convert transform files to strings
    transform_strs = [str(tf) for tf in transform_files]
    
    # Call operation
    result = ants_apply_transforms(
        movingf=str(input.input_file),
        moving_type=3,  # 3D image
        interpolation=interpolation,
        outputf_name=input.output_name or "func_registered.nii.gz",
        fixedf=str(reference_file),
        transformf=transform_strs,
        reff=str(reference_file),
        working_dir=str(input.working_dir),
        generate_tmean=True,
        config=input.config,
        logger=logger
    )
    
    output_file = Path(result["imagef_registered"])
    additional_files = []
    
    if result.get("imagef_registered_tmean"):
        additional_files.append(Path(result["imagef_registered_tmean"]))
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "apply_transforms",
            "modality": "func",
            "interpolation": interpolation,
            "num_transforms": len(transform_files)
        },
        additional_files=additional_files
    )

