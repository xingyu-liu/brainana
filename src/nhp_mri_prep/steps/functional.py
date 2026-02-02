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
from ..operations.registration import ants_register, ants_apply_transforms, flirt_apply_transforms, flirt_register, flirt_register
from ..utils import get_image_resolution, calculate_func_tmean
from ..utils import run_command
import numpy as np
import nibabel as nib

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
            additional_files={"tmean": tmean_path}
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
    
    additional_files = {}
    if tmean_file:
        additional_files["tmean"] = tmean_file
    
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
    
    additional_files = {}
    if tmean_file:
        additional_files["tmean"] = tmean_file
    
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
    
    additional_files = {}
    if tmean_file:
        additional_files["tmean"] = tmean_file
    if motion_params:
        additional_files["motion_params"] = motion_params
    
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
    
    additional_files = {}
    if tmean_file:
        additional_files["tmean"] = tmean_file
    if result.get("spikiness_map"):
        additional_files["spikiness_map"] = Path(result["spikiness_map"])
    
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


def func_conform(input: StepInput, target_file: Path, bold_4d_file: Optional[Path] = None) -> StepOutput:
    """
    Conform functional tmean image to target space, and optionally apply transform to full 4D BOLD.
    
    Args:
        input: StepInput with input_file (tmean), working_dir, config, metadata
        target_file: Target file for conforming (anatomical or template)
        bold_4d_file: Optional path to full 4D BOLD timeseries to also conform
        
    Returns:
        StepOutput with conformed tmean file, conformed 4D BOLD (if provided), and transform files
    """
    if not input.config.get("func.conform.enabled", True):
        logger.info("Step: conform skipped (disabled in configuration)")
        return StepOutput(
            output_file=input.input_file,
            metadata={"step": "conform", "skipped": True}
        )
    
    # Check if skullstripping is disabled
    skip_skullstripping = not input.config.get("func.skullstripping.enabled", True)
    
    # Step 1: Conform the tmean (used for registration)
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
    additional_files = {}
    
    if result.get("forward_xfm"):
        additional_files["forward_transform"] = Path(result["forward_xfm"])
    if result.get("inverse_xfm"):
        additional_files["inverse_transform"] = Path(result["inverse_xfm"])
    if result.get("template_f"):
        additional_files["template_resampled"] = Path(result["template_f"])
    
    # Step 2: Apply the same transform to the full 4D BOLD timeseries if provided
    if bold_4d_file and bold_4d_file.exists() and result.get("forward_xfm"):
        logger.info("Step: applying conform transform to full 4D BOLD timeseries")
        from ..operations.registration import flirt_apply_transforms
        
        # Use the conformed tmean as reference for resampling
        # Pass only filename, not full path, since flirt_apply_transforms will prepend work_dir
        bold_4d_conformed_filename = "func_bold_conformed.nii.gz"
        
        # Apply transform to 4D BOLD
        bold_result = flirt_apply_transforms(
            movingf=str(bold_4d_file),
            outputf_name=bold_4d_conformed_filename,
            reff=str(output_file),  # Use conformed tmean as reference
            working_dir=str(input.working_dir),
            transformf=str(result["forward_xfm"]),
            logger=logger,
            interpolation="trilinear",
            generate_tmean=False  # Don't generate tmean, we already have it
        )
        
        if bold_result.get("imagef_registered"):
            additional_files["bold_4d_conformed"] = Path(bold_result["imagef_registered"])
            logger.info(f"Output: conformed 4D BOLD saved - {bold_result['imagef_registered']}")
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "conform",
            "modality": "func",
            "target_file": str(target_file),
            "bold_4d_conformed": str(bold_4d_file) if bold_4d_file else None
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
    additional_files = {}
    
    if result.get("brain_mask"):
        additional_files["brain_mask"] = Path(result["brain_mask"])
    
    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "skullstripping",
            "modality": "func",
            "method": "nhp_skullstrip_nn"
        },
        additional_files=additional_files
    )


def func_apply_mask(input: StepInput, brain_mask: Path, generate_tmean: bool = True) -> StepOutput:
    """
    Apply mask to image.
    
    Args:
        input: StepInput with input_file (4d or 3d), working_dir, config, metadata
        brain_mask: Path to brain mask
        generate_tmean: Whether to generate tmean
        
    Returns:
        StepOutput with masked image and tmean (if generated)
    """
    # Ensure working directory exists
    input.working_dir.mkdir(parents=True, exist_ok=True)

    if not brain_mask.exists():
        raise FileNotFoundError(f"Brain mask not found: {brain_mask}")

    # Apply mask
    from ..operations.preprocessing import apply_mask

    output_name = input.output_name or "func_brain.nii.gz"
    result = apply_mask(
        imagef=str(input.input_file),
        maskf=str(brain_mask),
        working_dir=str(input.working_dir),
        output_name=output_name,
        logger=logger,
        generate_tmean=generate_tmean
    )

    output_file = Path(result["imagef_masked"])  # type: ignore[arg-type]
    additional_files = {"brain_mask": brain_mask}
    if generate_tmean and result.get("imagef_masked_tmean"):
        additional_files["tmean"] = Path(result["imagef_masked_tmean"])

    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "apply_brain_mask",
            "modality": "func",
        },
        additional_files=additional_files,
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
    
    # Ensure working directory exists
    input.working_dir.mkdir(parents=True, exist_ok=True)
    
    # Get transform type from config
    config_key = f"func2{target_type}_xfm_type"
    xfm_type = input.config.get("registration", {}).get(config_key, "syn")
    
    # Resample target to functional resolution if requested
    fixedf = str(target_file)
    if input.config.get("registration.keep_func_resolution", True):
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
    additional_files = {}
    
    if result.get("forward_transform"):
        additional_files["forward_transform"] = Path(result["forward_transform"])
    if result.get("inverse_transform"):
        additional_files["inverse_transform"] = Path(result["inverse_transform"])
    
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
    
    # Ensure working directory exists
    input.working_dir.mkdir(parents=True, exist_ok=True)
    
    # Call operation
    result = ants_apply_transforms(
        movingf=str(input.input_file),
        moving_type=3,  # 3D image (time series)
        interpolation=interpolation,
        outputf_name=input.output_name or "func_registered.nii.gz",
        fixedf=str(reference_file),
        transformf=transform_strs,
        reff=str(reference_file),
        working_dir=str(input.working_dir),
        generate_tmean=True,
        logger=logger
    )
    
    output_file = Path(result["imagef_registered"])
    additional_files = {}
    
    if result.get("imagef_registered_tmean"):
        additional_files["tmean"] = Path(result["imagef_registered_tmean"])
    
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


def func_within_ses_coreg(
    input: StepInput,
    reference_tmean: Path,
    reference_run: str,
    current_run: str,
    bold_file: Path
) -> StepOutput:
    """
    Coregister a functional run to a reference run within the same session.
    
    This is used when multiple runs exist in a session. Later runs are
    coregistered to the first run using tmean images, then the transform
    is applied to the BOLD file.
    
    Args:
        input: StepInput with input_file (tmean to be coregistered), working_dir, config, metadata
        reference_tmean: Path to reference tmean (from first run)
        reference_run: Run identifier for reference (e.g., "01")
        current_run: Run identifier for current run (e.g., "02")
        bold_file: Path to BOLD file to be coregistered
        
    Returns:
        StepOutput with coregistered tmean, coregistered BOLD, and transform files
    """
    # Set FLIRT parameters for functional coregistration (rigid registration)
    flirt_config = {
        "registration": {
            "flirt": {
                "cost": "mutualinfo",
                "searchcost": "mutualinfo",
                "coarsesearch": 40,
                "finesearch": 15,
                "searchrx": [-60, 60],
                "searchry": [-60, 60],
                "searchrz": [-60, 60]
            }
        }
    }
    
    # Step 1: FLIRT rigid registration from current run tmean to reference run tmean
    try:
        registration_result = flirt_register(
            fixedf=str(reference_tmean),
            movingf=str(input.input_file),  # Current run tmean
            working_dir=str(input.working_dir),
            output_prefix=f"run{current_run}_to_run{reference_run}_coreg",
            config=flirt_config,
            logger=logger,
            dof=6  # Use rigid registration for within-session coregistration
        )
        xfm_forward_f = Path(registration_result['forward_transform'])
        xfm_inverse_f = Path(registration_result.get('inverse_transform')) if 'inverse_transform' in registration_result else None
    except Exception as e:
        logger.error(f"Error during FLIRT registration for run {current_run} to run {reference_run}: {e}")
        raise RuntimeError(
            f"Within-session coregistration failed during FLIRT registration: {e}"
        )
    
    # Step 2: Apply the affine transformation to the tmean image
    try:
        apply_result = flirt_apply_transforms(
            movingf=str(input.input_file),
            outputf_name=f"run{current_run}_to_run{reference_run}_tmean_coreg.nii.gz",
            reff=str(reference_tmean),
            working_dir=str(input.working_dir),
            transformf=str(xfm_forward_f),
            logger=logger,
            interpolation='trilinear',
            generate_tmean=False
        )
        tmean_coregistered = Path(apply_result['imagef_registered'])
    except Exception as e:
        logger.error(f"Error during tmean transformation application: {e}")
        raise RuntimeError(
            f"Within-session coregistration failed when applying transformation to tmean: {e}"
        )
    
    # Step 3: Apply the same transform to the BOLD file
    bold_coregistered = None
    if bold_file and bold_file.exists():
        try:
            apply_result_bold = flirt_apply_transforms(
                movingf=str(bold_file),
                outputf_name=f"run{current_run}_to_run{reference_run}_bold_coreg.nii.gz",
                reff=str(reference_tmean),  # Use tmean as reference for BOLD too
                working_dir=str(input.working_dir),
                transformf=str(xfm_forward_f),
                logger=logger,
                interpolation='trilinear',
                generate_tmean=False
            )
            bold_coregistered = Path(apply_result_bold['imagef_registered'])
        except Exception as e:
            logger.error(f"Error during BOLD transformation application: {e}")
            raise RuntimeError(
                f"Within-session coregistration failed when applying transformation to BOLD: {e}"
            )
    
    additional_files = {}
    if xfm_forward_f.exists():
        additional_files["forward_transform"] = xfm_forward_f
    if xfm_inverse_f is not None and xfm_inverse_f.exists():
        additional_files["inverse_transform"] = xfm_inverse_f
    if bold_coregistered and bold_coregistered.exists():
        additional_files["bold_coregistered"] = bold_coregistered
    
    return StepOutput(
        output_file=tmean_coregistered,
        metadata={
            "step": "within_ses_coreg",
            "modality": "func",
            "reference_run": reference_run,
            "current_run": current_run,
            "xfm_type": "rigid"
        },
        additional_files=additional_files
    )


def func_average_tmean(tmean_files: List[Path], working_dir: Path, config: Dict[str, Any]) -> StepOutput:
    """
    Average multiple tmean files (typically after within-session coregistration).
    
    Args:
        tmean_files: List of Path objects to tmean files to average
        working_dir: Working directory for output
        config: Configuration dictionary
        
    Returns:
        StepOutput with averaged tmean file
    """
    if len(tmean_files) == 0:
        raise ValueError("No tmean files provided for averaging")
    
    if len(tmean_files) == 1:
        # Single file, just return it (no averaging needed)
        logger.info("Only one tmean file provided, skipping averaging")
        return StepOutput(
            output_file=tmean_files[0],
            metadata={
                "step": "average_tmean",
                "num_files": 1,
                "skipped": True
            }
        )
    
    logger.info(f"Averaging {len(tmean_files)} tmean files")
    
    # Incremental mean calculation to avoid loading all images into memory at once
    # Process images one by one: accumulate sum, then divide by count
    sum_data = None
    reference_img = None
    valid_count = 0
    
    for tmean_file in tmean_files:
        if not tmean_file.exists():
            logger.warning(f"Tmean file does not exist: {tmean_file}, skipping")
            continue
        try:
            img = nib.load(str(tmean_file))
            img_data = img.get_fdata()
            
            # Initialize sum with first valid image
            if sum_data is None:
                sum_data = img_data.astype(np.float64)  # Use float64 for accumulation precision
                reference_img = img  # Save first image for header/affine
            else:
                # Accumulate sum incrementally
                sum_data += img_data
            
            valid_count += 1
        except Exception as e:
            logger.warning(f"Failed to load tmean file {tmean_file}: {e}, skipping")
            continue
    
    if valid_count == 0:
        raise ValueError("No valid tmean files could be loaded for averaging")
    
    if valid_count == 1:
        logger.info("Only one valid tmean file after filtering, skipping averaging")
        return StepOutput(
            output_file=tmean_files[0],
            metadata={
                "step": "average_tmean",
                "num_files": 1,
                "skipped": True
            }
        )
    
    # Calculate mean by dividing accumulated sum by count
    mean_data = (sum_data / valid_count).astype(np.float32)
    
    # Create averaged image using reference header
    averaged_img = nib.Nifti1Image(
        mean_data.astype(np.float32),
        affine=reference_img.affine,
        header=reference_img.header
    )
    
    # Generate output filename
    output_name = "func_tmean_averaged.nii.gz"
    averaged_path = working_dir / output_name
    
    # Save averaged image
    nib.save(averaged_img, str(averaged_path))
    
    logger.info(f"Averaged tmean saved: {averaged_path}")
    
    return StepOutput(
        output_file=averaged_path,
        metadata={
            "step": "average_tmean",
            "num_files": valid_count,
            "input_files": [str(f) for f in tmean_files]
        }
    )

