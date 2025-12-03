"""
Preprocessing steps for macacaMRIprep.

This module contains all preprocessing functions for both anatomical and functional MRI data,
including slice timing correction, motion correction, despike, skull stripping, and bias correction.
"""

import os
import shutil
import pandas as pd
import numpy as np
import logging
import time
from typing import Dict, Any, Optional, Union, List
from pathlib import Path
import nibabel as nib

from .validation import validate_input_file, ensure_working_directory, validate_output_file
from ..utils import run_command, calculate_func_tmean, reorient_image_to_target, check_image_shape
from ..config import validate_slice_timing_config
# Import skullstripping from FastSurferCNN package
import sys
from pathlib import Path

# Add the project root to sys.path to enable FastSurferCNN imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from FastSurferCNN.inference.skullstripping import skullstrip_fastsurfercnn

# %%
def reorient(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    logger: logging.Logger,
    modal: str = "func",
    target_file: Optional[Union[str, Path]] = None,
    generate_tmean: bool = False,
) -> Dict[str, str]:
    """Reorient the input file (anatomical or functional).
    
    Args:
        imagef: Input image file (anatomical or functional)
        working_dir: Working directory
        logger: Logger instance
        modal: Image modality ('anat' or 'func')
        target_file: Optional target file for reorientation
        generate_tmean: Whether to generate temporal mean (True for func, False for anat)
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If reorient fails
        ValueError: If configuration parameters are invalid
    """
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Validate modal parameter
    if modal not in ["anat", "func"]:
        raise ValueError(f"Modal must be 'anat' or 'func', got '{modal}'")
    
    logger.info(f"Workflow: starting reorient for {modal} image")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: working directory - {work_dir}")
    
    # Initialize outputs dictionary
    outputs = {"imagef_reoriented": None,
               "imagef_tmean": None}

    if target_file is not None:
        logger.info(f"Step: reorienting image to target")
        image_reoriented_path = work_dir / f"{modal}_reoriented.nii.gz"
        reorient_image_to_target(image_path, target_file, image_reoriented_path, logger)
        outputs["imagef_reoriented"] = str(image_reoriented_path)
        logger.info(f"Output: image reoriented to target - {os.path.basename(image_reoriented_path)}")
        # update the image_path to the reoriented image
        image_path = str(image_reoriented_path)

    if generate_tmean:
        logger.info(f"Step: generating temporal mean")
        # Generate Tmean of the functional data
        image_tmean_path = os.path.join(str(work_dir), f"{modal}_tmean.nii.gz")
        calculate_func_tmean(image_path, image_tmean_path, logger)
        outputs["imagef_tmean"] = image_tmean_path
        logger.info(f"Output: temporal mean generated - {os.path.basename(image_tmean_path)}")
    
    logger.info(f"Workflow: reorient completed - {len([v for v in outputs.values() if v is not None])} outputs generated")
    return outputs

def determine_tpattern(slice_timings: List[Union[float, int]], direction: str = "z") -> str:
    """
    Determines the slice timing pattern (tpattern) given a list of slice timings.
    Returns one of: 'alt+z', 'alt+z2', 'alt-z', 'alt-z2', 'seq+z', 'seq-z'
    """
    # Handle edge cases
    if len(slice_timings) == 0:
        return 'unknown'
    
    if len(slice_timings) == 1:
        return 'unknown'
    
    # reverse the slice timings if the direction is negative
    if '-' in direction:
        slice_timings = slice_timings[::-1]
        direction = direction.replace('-', '+')
    
    indexed_timings = list(enumerate(slice_timings))
    sorted_by_time = sorted(indexed_timings, key=lambda x: x[1])
    sorted_indices = [i for i, _ in sorted_by_time]
    n_slices = len(slice_timings)

    def is_seq(indices):
        return indices == sorted(indices)

    def is_reverse_seq(indices):
        return indices == sorted(indices, reverse=True)

    # Check sequential patterns first
    if is_seq(sorted_indices):
        return f'seq+z'
    if is_reverse_seq(sorted_indices):
        return f'seq-z'

    # Check for special alt+z2 and alt-z2 patterns
    if n_slices >= 4:
        # alt+z2: slice 1 has minimum timing (acquired first)
        if sorted_indices[0] == 1:
            return f'alt+z2'
        # alt-z2: slice n-2 has minimum timing (acquired first)  
        if sorted_indices[0] == n_slices - 2:
            return f'alt-z2'

    # Check for standard alternating patterns
    # Split acquisition order into even and odd slice groups
    even_slices = [i for i in sorted_indices if i % 2 == 0]
    odd_slices = [i for i in sorted_indices if i % 2 == 1]
    
    # Check if even and odd slices are grouped together in acquisition order
    if len(even_slices) > 0 and len(odd_slices) > 0:
        # Find positions of even and odd slices in acquisition order
        even_positions = [sorted_indices.index(i) for i in even_slices]
        odd_positions = [sorted_indices.index(i) for i in odd_slices]
        
        # Check if even slices are acquired before odd slices (strict separation)
        if max(even_positions) < min(odd_positions):
            # Even slices acquired first - check if they follow a valid pattern
            if even_slices == sorted(even_slices):
                return f'alt+z'  # ascending order within even group
            elif even_slices == sorted(even_slices, reverse=True):
                return f'alt-z'  # descending order within even group
        elif max(odd_positions) < min(even_positions):
            # Odd slices acquired first - check if they follow a valid pattern
            if odd_slices == sorted(odd_slices):
                return f'alt+z'  # ascending order within odd group
            elif odd_slices == sorted(odd_slices, reverse=True):
                return f'alt-z'  # descending order within odd group

    return 'unknown'

# %%
def slice_timing_correction(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    config: Dict[str, Any],
    logger: logging.Logger,
    generate_tmean: bool = True
) -> Dict[str, str]:
    """Perform slice timing correction using AFNI's 3dTshift.
    
    Args:
        imagef: Input functional file
        working_dir: Working directory
        output_name: Name of output file
        config: Configuration dictionary
        logger: Logger instance
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If slice timing correction fails or AFNI is not available
        ValueError: If configuration parameters are invalid
    """
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Get configuration from new nested structure
    slice_timing_cfg = config.get('func', {}).get('slice_timing_correction')
    if not slice_timing_cfg:
        raise ValueError("func.slice_timing configuration not found")

    # Check if slice timing is enabled and has valid data
    if not slice_timing_cfg.get('enabled', False):
        logger.info("Step: slice timing correction skipped (disabled in configuration)")
        return {"imagef_slice_time_corrected": None, "imagef_slice_time_corrected_tmean": None}
    
    # Check if we have valid repetition_time and slice_timing
    tr = slice_timing_cfg.get('repetition_time')
    slice_times = slice_timing_cfg.get('slice_timing')
    
    if tr is None or slice_times is None:
        logger.warning(
            "Step: slice timing correction skipped - missing required metadata "
            "(RepetitionTime or SliceTiming). Slice timing correction requires BIDS metadata."
        )
        return {"imagef_slice_time_corrected": None, "imagef_slice_time_corrected_tmean": None}

    validate_slice_timing_config(slice_timing_cfg)
    
    # Initialize outputs dictionary
    outputs = {"imagef_slice_time_corrected": None}
    if generate_tmean:
        outputs["imagef_slice_time_corrected_tmean"] = None

    # set the output path
    output_path = work_dir / output_name
    logger.info(f"Workflow: starting slice timing correction")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: output path - {output_path}")

    # determine the tpattern
    slice_timing_data = slice_timing_cfg.get('slice_timing')
    slice_encoding_direction = slice_timing_cfg.get('slice_encoding_direction')
    
    # Custom slice timing values provided - analyze to determine pattern
    logger.info(f"Step: determining slice timing pattern")
    tpattern = determine_tpattern(slice_timing_data, slice_encoding_direction)
    if tpattern == 'unknown':
        # skip slice timing correction
        logger.warning("Step: unknown slice timing pattern - skipping slice timing correction")
        return outputs
    
    logger.info(f"Data: slice timing pattern - {tpattern}, slice encoding direction - {slice_encoding_direction}")

    # double check whether the slice in the encoding direction is matching the slice_timing_data
    img_shape_original = check_image_shape(image_path, logger)
    if 'x' in slice_encoding_direction:
        img_shape_original = img_shape_original[0]
    elif 'y' in slice_encoding_direction:
        img_shape_original = img_shape_original[1]
    if img_shape_original != len(slice_timing_data):
        logger.warning(f"Slice encoding direction swapped between {slice_encoding_direction} and z, "
                       f"but the shape of the image is not matching the slice timing data: {img_shape_original} != {len(slice_timing_data)}. "
                       f"Skipping slice timing correction.")
        return outputs
    
    # swap the slice encoding direction if it is not z to run the 3dTshift
    if 'z' not in slice_encoding_direction:
        img = nib.load(image_path)
        img_data = img.get_fdata()
        temp_path = Path(work_dir) / f"func_all_swap{slice_encoding_direction}z.nii.gz"
        if 'x' in slice_encoding_direction:
            img_data_swap = np.swapaxes(img_data, 0, 2)
        elif 'y' in slice_encoding_direction:
            img_data_swap = np.swapaxes(img_data, 1, 2)

        nib.save(nib.Nifti1Image(img_data_swap, img.affine, img.header), temp_path)
        image_path = str(temp_path)
        logger.info(f"Step: swapping slice encoding direction")
        logger.info(f"Data: swapped image path - {os.path.basename(image_path)}")

    # Build command
    command_slicetimer = [
        '3dTshift',
        '-prefix', str(output_path),
        '-TR', f'{slice_timing_cfg.get("repetition_time")}s',
        '-tzero', str(slice_timing_cfg.get('tzero')),
        '-tpattern', tpattern,
        str(image_path)
    ]

    # Execute command
    try:
        returncode, stdout, stderr = run_command(command_slicetimer, cwd=str(work_dir), step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"slice timing correction failed (exit code {returncode}): {stderr}")

        # swap back the slice encoding direction if it is not z
        if 'z' not in slice_encoding_direction:
            img = nib.load(output_path)
            img_data = img.get_fdata()
            if 'x' in slice_encoding_direction:
                img_data_swap = np.swapaxes(img_data, 0, 2)
            elif 'y' in slice_encoding_direction:
                img_data_swap = np.swapaxes(img_data, 1, 2)
            nib.save(nib.Nifti1Image(img_data_swap, img.affine, img.header), output_path)
            logger.info(f"Step: swapping slice encoding direction back")
            logger.info(f"Data: swapped image path - {os.path.basename(output_path)}")

        # Validate output
        validate_output_file(output_path, logger)
        logger.info("Workflow: slice timing correction completed successfully")
        outputs["imagef_slice_time_corrected"] = str(output_path)

        # Generate Tmean of the func_all
        if generate_tmean:
            tmean_path = str(Path(work_dir) / Path(outputs["imagef_slice_time_corrected"].split('.nii')[0] + "_tmean.nii.gz"))
            calculate_func_tmean(outputs["imagef_slice_time_corrected"], tmean_path, logger)
            outputs["imagef_slice_time_corrected_tmean"] = tmean_path
            logger.info(f"Output: Tmean of slice time corrected func_all - {os.path.basename(tmean_path)}")

        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: slice timing correction failed: {str(e)}")
        raise


# %%
def motion_correction(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    logger: logging.Logger,
    config: Dict[str, Any],
    generate_tmean: bool = True
) -> Dict[str, str]:
    """Perform motion correction using FSL's mcflirt.
    
    Args:
        imagef: Input functional file
        working_dir: Working directory
        output_name: Name of output file
        logger: Logger instance
        config: Configuration dictionary
        generate_tmean: Whether to generate temporal mean of corrected image
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If motion correction fails
        ValueError: If configuration parameters are invalid
    """
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Get configuration from new nested structure
    motion_cfg = config.get('func', {}).get('motion_correction')
    if not motion_cfg:
        raise ValueError("func.motion_correction configuration not found")
    
    output_path = os.path.join(str(work_dir), output_name)
    
    logger.info(f"Workflow: starting motion correction")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: output path - {output_path}")

    outputs = {
        "imagef_motion_corrected": None, 
        "motion_parameters": None,
        "motion_correction_ref_file": None
    }
    if generate_tmean:
        outputs["imagef_motion_corrected_tmean"] = None

    # Check number of volumes and skip if fewer than 15
    shape = check_image_shape(image_path, logger)
    if len(shape) < 4:
        logger.error(f"Input image has {len(shape)} dimensions, expected 4D for functional data")
        return outputs
    
    nvols = shape[3]
    logger.info(f"Input image has {nvols} volumes")
    
    if nvols < 15:
        logger.warning(f"Step: skipping motion correction - only {nvols} volumes (< 15)")
        # Return None outputs to indicate motion correction was skipped
        return outputs

    # Generate reference volume
    ref_file_path = os.path.join(str(work_dir), 'func_mc_ref.nii.gz')

    ref_vol = motion_cfg.get('ref_vol')
    if isinstance(ref_vol, int):
        command_ref = ['fslroi', str(image_path), ref_file_path, str(ref_vol), '1']
        logger.info(f"Step: using reference timepoint")
        logger.info(f"Data: reference timepoint - {ref_vol}")
    elif ref_vol == 'Tmean':
        command_ref = ['fslmaths', str(image_path), '-Tmean', ref_file_path]
        logger.info(f"Step: using temporal mean as reference")
        logger.info(f"Data: reference type - Tmean")
    elif ref_vol == 'mid':
        # We already have nvols from above
        mid_vol = nvols // 2
        command_ref = ['fslroi', str(image_path), ref_file_path, str(mid_vol), '1']
        logger.info(f"Step: using middle timepoint as reference")
        logger.info(f"Data: reference timepoint - {mid_vol}")
    else:
        raise ValueError(f"Invalid ref_vol parameter: {ref_vol}")
    
    # Generate reference volume
    try:
        returncode, stdout, stderr = run_command(command_ref, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"Reference volume generation failed (exit code {returncode}): {stderr}")
        
        validate_output_file(ref_file_path, logger)
        logger.info("Workflow: reference volume generated successfully")
        
    except Exception as e:
        logger.error(f"Workflow: reference volume generation failed: {str(e)}")
        raise


    # Build motion correction command
    output_prefix = output_path.split('.nii')[0]
    command_mcflirt = [
        'mcflirt',
        '-in', str(image_path),
        '-out', output_prefix,
        '-dof', str(motion_cfg.get('dof')),
        '-reffile', ref_file_path,
        '-mats',
        '-plots'
    ]
    
    # Execute motion correction
    try:
        returncode, stdout, stderr = run_command(command_mcflirt, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"mcflirt failed (exit code {returncode}): {stderr}")
        
        logger.info("Workflow: motion correction completed successfully")
        
        # Validate output
        validate_output_file(output_path, logger)
        
        outputs["imagef_motion_corrected"] = output_path
        outputs['motion_correction_ref_file'] = ref_file_path

        # Check for motion parameters
        motion_params = output_prefix + '.par'
        if os.path.exists(motion_params):
            # convert motion parameters to a tsv
            motion_params_df = pd.read_table(motion_params, sep=r'\s+', header=None)
            motion_params_df.columns = ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z']
            tsv_path = output_prefix + '.tsv'
            motion_params_df.to_csv(tsv_path, sep='\t', index=False)
            outputs["motion_parameters"] = tsv_path
            outputs["motion_parameters_par"] = motion_params  # Keep original as backup
        else:
            logger.warning("Data: motion parameters file not found")
            outputs["motion_parameters"] = None
        
        # Generate Tmean of the func_all
        if generate_tmean:
            tmean_path = str(Path(work_dir) / Path(outputs["imagef_motion_corrected"].split('.nii')[0] + "_tmean.nii.gz"))
            calculate_func_tmean(outputs["imagef_motion_corrected"], tmean_path, logger)
            outputs["imagef_motion_corrected_tmean"] = tmean_path
            logger.info(f"Output: Tmean of motion corrected func_all - {os.path.basename(tmean_path)}")

        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: motion correction failed: {str(e)}")
        raise

def despike(
    imagef: Union[str, Path], 
    working_dir: Union[str, Path], 
    output_name: str, 
    logger: logging.Logger,
    config: Dict[str, Any],
    generate_tmean: bool = True
) -> Dict[str, str]:
    """Perform despiking using AFNI's 3dDespike.
    
    Args:
        imagef: Input functional file
        working_dir: Working directory
        output_name: Name of output file
        logger: Logger instance
        config: Configuration dictionary
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If despiking fails
        ValueError: If configuration parameters are invalid
    """
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)

    outputs = {"imagef_despiked": None}
    if generate_tmean:
        outputs["imagef_despiked_tmean"] = None

    # check if the input is 4D and the last dimension is larger than 15
    image_shape = check_image_shape(image_path, logger)
    if len(image_shape) != 4:
        logger.warning("Step: input image is not 4D - skipping despiking")
        return outputs
    if image_shape[3] <= 15:
        logger.warning("Step: time series is too short (less than 15 volumes) - skipping despiking")
        return outputs
    
    # Get configuration
    despike_cfg = config.get('func', {}).get('despike')
    if not despike_cfg:
        raise ValueError("despike configuration not found")
    
    # set the output path
    output_path = os.path.join(str(work_dir), output_name)
    spikiness_path = os.path.join(str(work_dir), output_name.replace('.nii.gz', '_spikiness.nii.gz'))
    
    logger.info(f"Workflow: starting despiking")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: output path - {output_path}")

    # Build command
    command_despike = [
        '3dDespike',
        '-prefix', output_path,
        '-ssave', spikiness_path,
        '-cut', str(despike_cfg.get('c1')), str(despike_cfg.get('c2')),
        str(image_path)
    ]

    if despike_cfg.get('localedit'):
        command_despike.append('-localedit')

    # Execute command
    try:
        returncode, stdout, stderr = run_command(command_despike, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"3dDespike failed (exit code {returncode}): {stderr}")
        
        logger.info("Workflow: despiking completed successfully")
        
        # Validate outputs
        validate_output_file(output_path, logger)
        outputs = {"imagef_despiked": output_path,
                   "spikiness_map": spikiness_path}
        
        # Generate Tmean of the func_all
        if generate_tmean:
            tmean_path = str(Path(work_dir) / Path(outputs["imagef_despiked"].split('.nii')[0] + "_tmean.nii.gz"))
            calculate_func_tmean(outputs["imagef_despiked"], tmean_path, logger)
            outputs["imagef_despiked_tmean"] = tmean_path
            logger.info(f"Output: Tmean of despiked func_all - {os.path.basename(tmean_path)}")

        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: despiking failed: {str(e)}")
        raise

def apply_skullstripping(
    imagef: Union[str, Path],
    modal: str,
    working_dir: Union[str, Path],
    output_name: str,
    logger: logging.Logger,
    config: Dict[str, Any],
) -> Dict[str, str]:
    """Perform skullstripping using various methods (BET, FastSurferCNN, or macacaMRINN).
    
    Args:
        imagef: Input file (functional or anatomical)
        modal: Modality ('func' or 'anat')
        working_dir: Working directory for this step
        output_name: Name of output file
        logger: Logger instance
        config: Configuration dictionary
        
    Returns:
        Dictionary with output file paths:
        - 'imagef_skullstripped': Path to skull-stripped image
        - 'brain_mask': Path to brain mask file
        
    Raises:
        FileNotFoundError: If input file or model doesn't exist
        RuntimeError: If skull stripping fails
        ValueError: If configuration or modal parameters are invalid
    """
    # Import the streamlined skull stripping API
    # from .skullstripping import skull_strip
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Validate modal parameter
    if modal not in ['func', 'anat']:
        raise ValueError(f"Invalid modality: {modal}. Must be 'func' or 'anat'")
    
    # Get configuration
    skull_cfg = config.get(modal, {}).get('skullstripping')
    if not skull_cfg:
        raise ValueError("skullstripping configuration not found")
    method = skull_cfg.get('method')
    if method not in ['bet', 'fastSurferCNN', 'macacaMRINN']:
        raise ValueError(f"Invalid skull stripping method: {method}. Must be 'bet', 'fastSurferCNN', or 'macacaMRINN'")

    # Define output paths at the beginning
    brain_mask_path = os.path.join(str(work_dir), 'brain_mask.nii.gz')
    
    # Initialize optional output paths (for FastSurferCNN)
    brain_segmentation_path = None
    brain_hemimask_path = None
    brain_input_cropped_path = None
    atlas_name = None

    if method == 'bet':
        logger.info(f"Workflow: starting skullstripping using FSL BET method")
        logger.info(f"Data: input image - {os.path.basename(image_path)}")
        logger.info(f"System: output path - {brain_mask_path}")
        command_bet = [
            'bet2', str(image_path), str(brain_mask_path.replace('_mask.nii.gz', '')),
            '-f', str(skull_cfg.get('bet', {}).get('fractional_intensity')),
            '-m', '-n'
        ]
        returncode, stdout, stderr = run_command(command_bet, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"bet2 failed (exit code {returncode}): {stderr}")
        logger.info("Workflow: FSL BET completed successfully")

    elif method == 'fastSurferCNN':
        logger.info(f"Workflow: starting skullstripping using FastSurferCNN method")
        logger.info(f"Data: input image - {os.path.basename(image_path)}")
        logger.info(f"System: output path - {brain_mask_path}")
        
        # Get FastSurferCNN configuration parameters
        fscnn_cfg = skull_cfg.get('fastSurferCNN', {})
        
        # Create temporary output directory for FastSurferCNN
        # FastSurferCNN needs a directory, not a file path
        temp_output_dir = os.path.join(str(work_dir), 'fastsurfercnn_output')
        os.makedirs(temp_output_dir, exist_ok=True)
        
        try:
            # Call FastSurferCNN skullstripping function
            # Note: This is the FastSurferCNN.inference.skullstrip_fastsurfercnn function imported at the top
            result = skullstrip_fastsurfercnn(
                input_image=image_path,
                modal=modal,
                output_dir=temp_output_dir,
                device_id=fscnn_cfg.get('gpu_device', 'auto'),
                logger=logger,
                output_data_format='nifti',
                enable_crop_2round=fscnn_cfg.get('enable_crop_2round', False),
                plane_weight_coronal=fscnn_cfg.get('plane_weight_coronal'),
                plane_weight_axial=fscnn_cfg.get('plane_weight_axial'),
                plane_weight_sagittal=fscnn_cfg.get('plane_weight_sagittal'),
                use_mixed_model=fscnn_cfg.get('use_mixed_model', False),
            )
            
            # Extract brain mask path and atlas_name from result
            fastsurfercnn_mask_path = result.get('brain_mask')
            if not fastsurfercnn_mask_path or not os.path.exists(fastsurfercnn_mask_path):
                raise FileNotFoundError(f"FastSurferCNN did not generate brain mask at expected location: {fastsurfercnn_mask_path}")
            
            # Extract atlas_name if available
            atlas_name = result.get('atlas_name')
            
            # Move the brain mask to the expected location
            shutil.move(fastsurfercnn_mask_path, brain_mask_path)
            logger.info("Workflow: FastSurferCNN completed successfully")
            logger.info(f"Output: brain mask moved from {fastsurfercnn_mask_path} to {brain_mask_path}")
            
            # Move segmentation if it exists
            fastsurfercnn_seg_path = result.get('segmentation')
            if fastsurfercnn_seg_path and os.path.exists(fastsurfercnn_seg_path):
                brain_segmentation_path = os.path.join(str(work_dir), 'brain_segmentation.nii.gz')
                shutil.move(fastsurfercnn_seg_path, brain_segmentation_path)
                logger.info(f"Output: brain segmentation moved from {fastsurfercnn_seg_path} to {brain_segmentation_path}")
            
            # Move hemimask if it exists
            fastsurfercnn_hemimask_path = result.get('hemimask')
            if fastsurfercnn_hemimask_path and os.path.exists(fastsurfercnn_hemimask_path):
                brain_hemimask_path = os.path.join(str(work_dir), 'brain_hemimask.nii.gz')
                shutil.move(fastsurfercnn_hemimask_path, brain_hemimask_path)
                logger.info(f"Output: brain hemimask moved from {fastsurfercnn_hemimask_path} to {brain_hemimask_path}")
            
            # Move input cropped if it exists
            fastsurfercnn_input_cropped_path = result.get('input_cropped')
            if fastsurfercnn_input_cropped_path and os.path.exists(fastsurfercnn_input_cropped_path):
                brain_input_cropped_path = os.path.join(str(work_dir), 'brain_input_cropped.nii.gz')
                shutil.move(fastsurfercnn_input_cropped_path, brain_input_cropped_path)
                logger.info(f"Output: brain input cropped moved from {fastsurfercnn_input_cropped_path} to {brain_input_cropped_path}")


        except Exception as e:
            logger.error(f"Workflow: FastSurferCNN failed - {str(e)}")
            raise

    elif method == 'macacaMRINN':
        logger.info(f"Workflow: starting skullstripping using macacaMRINN method")
        logger.info(f"Data: input image - {os.path.basename(image_path)}")
        logger.info(f"System: output path - {brain_mask_path}")
        
        # Import macacaMRINN skullstripping function
        try:
            from macacaMRINN.inference.prediction import skullstripping as macacaMRINN_skullstripping
        except ImportError as e:
            raise ImportError(f"Failed to import macacaMRINN: {e}. Make sure macacaMRINN is installed and available.")
        
        # Get macacaMRINN configuration parameters
        mrin_cfg = skull_cfg.get('macacaMRINN', {})
        
        # Don't pass config - let macacaMRINN use parameters from checkpoint
        # Only pass gpu_device as it's a runtime parameter, not a model parameter
        try:
            # Call macacaMRINN skullstripping function
            # Parameters like rescale_dim, num_input_slices, morph_iterations 
            # will be loaded from the model checkpoint automatically
            result = macacaMRINN_skullstripping(
                input_image=image_path,
                modal=modal,
                output_path=brain_mask_path,
                device_id=mrin_cfg.get('gpu_device', 'auto'),
                logger=logger,
                config=None  # Use checkpoint parameters instead
            )
            
            # Extract brain mask path and atlas_name from result
            mrin_mask_path = result.get('brain_mask')
            if not mrin_mask_path or not os.path.exists(mrin_mask_path):
                raise FileNotFoundError(f"macacaMRINN did not generate brain mask at expected location: {mrin_mask_path}")
            
            # Extract atlas_name if available
            atlas_name = result.get('atlas_name')
            
            # The mask should already be at brain_mask_path, but verify
            if mrin_mask_path != brain_mask_path:
                # Move the brain mask to the expected location if needed
                if os.path.exists(mrin_mask_path):
                    shutil.move(mrin_mask_path, brain_mask_path)
                    logger.info(f"Output: brain mask moved from {mrin_mask_path} to {brain_mask_path}")
            
            logger.info("Workflow: macacaMRINN completed successfully")
            
        except Exception as e:
            logger.error(f"Workflow: macacaMRINN failed - {str(e)}")
            raise

    # Validate brain mask
    validate_output_file(brain_mask_path, logger)
    logger.info(f"Output: brain mask generated - {os.path.basename(brain_mask_path)}")

    # Validate optional outputs (segmentation and hemimask from FastSurferCNN)
    if brain_segmentation_path is not None and os.path.exists(brain_segmentation_path):
        validate_output_file(brain_segmentation_path, logger)
        logger.info(f"Output: brain segmentation generated - {os.path.basename(brain_segmentation_path)}")
    if brain_hemimask_path is not None and os.path.exists(brain_hemimask_path):
        validate_output_file(brain_hemimask_path, logger)
        logger.info(f"Output: brain hemimask generated - {os.path.basename(brain_hemimask_path)}")
    
    # Apply brain mask to input image
    # If two-pass refinement was used, the mask is in cropped space, so use cropped input
    image_to_mask = image_path
    if brain_input_cropped_path is not None and os.path.exists(brain_input_cropped_path):
        image_to_mask = brain_input_cropped_path
        logger.info(f"Step: using cropped input for mask application (two-pass refinement detected)")
    
    output_path = os.path.join(str(work_dir), output_name)
    command_apply = [
        'fslmaths', str(image_to_mask),
        '-mul', str(brain_mask_path),
        str(output_path)
    ]
    returncode, stdout, stderr = run_command(command_apply, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"fslmaths failed (exit code {returncode}): {stderr}")
    
    # Validate final output
    validate_output_file(output_path, logger)
    logger.info(f"Output: skull stripped image generated - {os.path.basename(output_path)}")
    
    # Build return dictionary with optional segmentation and hemimask
    return_dict = {
        'atlas_name': atlas_name,
        "imagef_skullstripped": output_path,
        "brain_mask": brain_mask_path
    }
    
    # Add segmentation and hemimask if they exist (generated by FastSurferCNN)
    if brain_segmentation_path is not None and os.path.exists(brain_segmentation_path):
        return_dict["segmentation"] = brain_segmentation_path
    if brain_hemimask_path is not None and os.path.exists(brain_hemimask_path):
        return_dict["hemimask"] = brain_hemimask_path
    if brain_input_cropped_path is not None and os.path.exists(brain_input_cropped_path):
        return_dict["input_cropped"] = brain_input_cropped_path

    return return_dict

def bias_correction(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    modal: str,
    output_name: str,
    logger: logging.Logger,
    config: Dict[str, Any],
) -> Dict[str, str]:
    """Perform bias field correction using ANTs N4BiasFieldCorrection.
    
    Args:
        imagef: Input image file
        working_dir: Working directory
        modal: Modality ('func' or 'anat')
        output_name: Name of output file
        logger: Logger instance
        config: Configuration dictionary
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If bias correction fails
        ValueError: If configuration parameters are invalid
    """
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # make sure the input image is 3D, not 4D
    image_shape = check_image_shape(image_path, logger)
    if image_shape[3] != 1:
        raise ValueError("Input image is not 3D, must be 3D for bias correction")

    # Get configuration
    bias_cfg = config.get(modal, {}).get('bias_correction')
    if not bias_cfg:
        raise ValueError("bias_correction configuration not found")

    # Rescale image mean to 100 if configured
    rescale_mean_to_100 = bias_cfg.get('rescale_mean_to_100')
    if rescale_mean_to_100:
        image_path_rescaled = os.path.join(str(work_dir), "input_rescaled.nii.gz")
        
        # Get mean value using fslstats
        returncode, stdout, stderr = run_command(['fslstats', str(image_path), '-M'], step_logger=logger)
        mean_value = float(stdout.strip())
        
        # Rescale image to mean intensity of 100 by multiplying by 100/mean_value
        command_rescale = [
            'fslmaths', str(image_path),
            '-div', str(mean_value/100),
            str(image_path_rescaled)
        ]
        returncode, stdout, stderr = run_command(command_rescale, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"fslmaths failed (exit code {returncode}): {stderr}")
            
        logger.info(f"Workflow: image rescaled to mean intensity of 100")
        image_path = image_path_rescaled

    output_path = os.path.join(str(work_dir), output_name)
    bias_field_path = os.path.join(str(work_dir), output_name.split('.nii')[0] + '_bias_field.nii.gz')

    # Build command
    if bias_cfg.get('algorithm') == 'N4BiasFieldCorrection':
        logger.info(f"Workflow: starting bias field correction using N4BiasFieldCorrection algorithm")
        logger.info(f"Data: input image - {os.path.basename(image_path)}")
        logger.info(f"System: output path - {output_path}")
        command = [
            'N4BiasFieldCorrection',
            '-d', str(bias_cfg.get('dimension')),
            '-i', str(image_path),
            '-o', f"[{output_path},{bias_field_path}]",
            '-s', str(bias_cfg.get('shrink_factor')),
            '-b', str(bias_cfg.get('bspline_fitting'))
        ]
    else:
        # TODO: add other bias correction algorithms
        pass

    # Execute command
    try:
        returncode, stdout, stderr = run_command(command, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"N4BiasFieldCorrection failed (exit code {returncode}): {stderr}")
        
        logger.info("Workflow: N4BiasFieldCorrection completed successfully")
        
        # Validate outputs
        validate_output_file(output_path, logger)
        outputs = {
            "imagef_bias_corrected": output_path,
            "bias_field": bias_field_path
        }
        
        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: bias field correction failed: {str(e)}")
        raise
