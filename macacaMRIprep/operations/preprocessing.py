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
from nibabel.orientations import aff2axcodes

from .validation import validate_input_file, ensure_working_directory, validate_output_file
from .registration import flirt_register, flirt_apply_transforms
from ..utils import run_command, calculate_func_tmean, reorient_image_to_target, reorient_image_to_orientation, get_image_shape
from ..config import validate_slice_timing_config
from ..utils.mri import correct_affine_for_mismatch_orientation, get_opposite_orientation

# Import skullstripping from FastSurferCNN package
import sys

# Add the project root to sys.path to enable FastSurferCNN imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from FastSurferCNN.inference.segmentation import run_segmentation

# Import NHPskullstripNN for conform step
from NHPskullstripNN.inference.prediction import skullstripping

# %%
def correct_orientation_mismatch(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
    generate_tmean: bool = False,
) -> Dict[str, str]:
    """Correct orientation mismatch for the input image.
    
    This function corrects the affine matrix when there is a physical misorientation
    of the brain (n×90° rotation). The correction is based on the configuration
    parameters that specify what the axes currently labeled as 'A' and 'S' actually
    point to in physical space.
    
    Args:
        imagef: Input image file (anatomical or functional)
        working_dir: Working directory for output files
        output_name: Name of output file
        logger: Logger instance
        config: Configuration dictionary containing orientation mismatch correction parameters
        generate_tmean: Whether to generate temporal mean (True for func, False for anat)
        
    Returns:
        Dictionary with output file paths:
        - 'imagef_orientation_corrected': Path to orientation-corrected image (or None if skipped)
        - 'imagef_tmean': Path to temporal mean of corrected image (or None if skipped/not generated)
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If orientation correction fails
        ValueError: If configuration parameters are invalid or correction cannot be performed
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    logger.info(f"Workflow: starting orientation mismatch correction")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: working directory - {work_dir}")

    # Initialize outputs dictionary
    outputs = {"imagef_orientation_corrected": None, "imagef_tmean": None}

    # Get configuration from nested structure
    orientation_cfg = config.get("orientation_mismatch_correction", {})
    if not orientation_cfg.get("enabled", False):
        logger.info("Step: orientation mismatch correction skipped (disabled in configuration)")
        return outputs
    
    real_A_is_actually_labeled_as = orientation_cfg.get("real_A_is_actually_labeled_as", "A")
    real_S_is_actually_labeled_as = orientation_cfg.get("real_S_is_actually_labeled_as", "S")
    
    # Normalize to uppercase for consistency (utility function expects uppercase)
    real_A_is_actually_labeled_as = real_A_is_actually_labeled_as.upper()
    real_S_is_actually_labeled_as = real_S_is_actually_labeled_as.upper()
    
    # Check if correction is needed
    if real_A_is_actually_labeled_as == "A" and real_S_is_actually_labeled_as == "S":
        logger.info("Step: orientation mismatch correction skipped (already correct)")
        return outputs
    
    # Perform orientation correction
    try:
        logger.info(f"Step: correcting orientation mismatch")
        logger.info(f"Data: real A axis labeled as - {real_A_is_actually_labeled_as}")
        logger.info(f"Data: real S axis labeled as - {real_S_is_actually_labeled_as}")
        
        # Load image once and reuse
        img = nib.load(image_path)
        affine_cur = img.affine
        
        # Get original orientation
        orig_orientation = "".join(aff2axcodes(affine_cur))
        logger.info(f"Data: original orientation - {orig_orientation}")
        
        # Correct the affine matrix for orientation mismatch
        affine_corrected = correct_affine_for_mismatch_orientation(
            affine_cur, real_A_is_actually_labeled_as, real_S_is_actually_labeled_as
        )
        
        # Get corrected orientation
        corrected_orientation = "".join(aff2axcodes(affine_corrected))
        logger.info(f"Data: corrected orientation - {corrected_orientation}")
        
        # Save the corrected image with updated affine matrix
        output_path = work_dir / output_name
        img_corrected = nib.Nifti1Image(img.get_fdata(), affine_corrected, img.header)
        nib.save(img_corrected, output_path)
        
        # Validate output
        validate_output_file(output_path, logger)
        logger.info(f"Output: orientation corrected - {os.path.basename(output_path)}")
        outputs["imagef_orientation_corrected"] = str(output_path)

        # Generate temporal mean of the corrected image if requested
        if generate_tmean:
            logger.info(f"Step: generating temporal mean")
            image_tmean_path = work_dir / (output_name.split('.nii')[0] + "_tmean.nii.gz")
            calculate_func_tmean(str(output_path), str(image_tmean_path), logger)
            outputs["imagef_tmean"] = str(image_tmean_path)
            logger.info(f"Output: tmean generated - {os.path.basename(image_tmean_path)}")

        logger.info(f"Workflow: orientation mismatch correction completed successfully")
        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: orientation mismatch correction failed: {str(e)}")
        raise RuntimeError(f"Orientation mismatch correction failed: {e}") from e
        

def reorient(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    logger: Optional[logging.Logger] = None,
    target_file: Optional[Union[str, Path]] = None,
    target_orientation: Optional[str] = None,
    generate_tmean: bool = False,
) -> Dict[str, str]:
    """Reorient the input file (anatomical or functional).
    
    Args:
        imagef: Input image file (anatomical or functional)
        working_dir: Working directory
        output_name: Name of output file
        logger: Logger instance
        target_file: Optional target file for reorientation (takes precedence over target_orientation)
        target_orientation: Optional target orientation string (e.g., 'RAS', 'LPI') when no target_file is provided
        generate_tmean: Whether to generate temporal mean (True for func, False for anat)
        
    Returns:
        Dictionary with output file paths
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If reorient fails
        ValueError: If configuration parameters are invalid
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    logger.info(f"Workflow: starting reorient")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: working directory - {work_dir}")

    # Initialize outputs dictionary
    outputs = {"imagef_reoriented": None,
               "imagef_tmean": None}

    if target_file is not None:
        logger.info(f"Step: reorienting image to target file")
        image_reoriented_path = work_dir / output_name
        reorient_image_to_target(image_path, target_file, image_reoriented_path, logger)
        outputs["imagef_reoriented"] = str(image_reoriented_path)
        logger.info(f"Output: image reoriented to target - {os.path.basename(image_reoriented_path)}")
        # update the image_path to the reoriented image
        image_path = str(image_reoriented_path)

    elif target_orientation is not None:
        # Validate and normalize target orientation
        target_orientation = str(target_orientation).upper().strip()
        if len(target_orientation) != 3:
            raise ValueError(
                f"target_orientation must be a 3-character string (e.g., 'RAS', 'LPI'), "
                f"got '{target_orientation}' (length: {len(target_orientation)})"
            )
        
        valid_chars = set('RLAPIS')
        if not all(c in valid_chars for c in target_orientation):
            invalid_chars = [c for c in target_orientation if c not in valid_chars]
            raise ValueError(
                f"target_orientation contains invalid characters: {invalid_chars}. "
                f"Must be from {{R, L, A, P, I, S}}, got '{target_orientation}'"
            )
        
        logger.info(f"Step: reorienting image to orientation {target_orientation}")

        # AFNI uses opposite orientation convention compared to NIfTI/FSL.
        # For example, RAS in NIfTI/FSL corresponds to LPI in AFNI.
        # Convert the target orientation (NIfTI/FSL convention) to AFNI's convention
        # by flipping each direction using get_opposite_orientation.
        target_orientation_afni = ''.join([get_opposite_orientation(d) for d in target_orientation])
        logger.info(f"Data: target orientation (NIfTI/FSL) - {target_orientation}, "
                   f"converted to AFNI convention - {target_orientation_afni}")

        image_reoriented_path = work_dir / output_name
        reorient_image_to_orientation(image_path, target_orientation_afni, image_reoriented_path, logger)
        outputs["imagef_reoriented"] = str(image_reoriented_path)
        logger.info(f"Output: image reoriented to {target_orientation} - {os.path.basename(image_reoriented_path)}")
        # update the image_path to the reoriented image
        image_path = str(image_reoriented_path)

    if generate_tmean:
        logger.info(f"Step: generating temporal mean")
        # Generate Tmean of the functional data
        image_tmean_path = work_dir / (output_name.split('.nii')[0] + "_tmean.nii.gz")
        calculate_func_tmean(image_path, str(image_tmean_path), logger)
        outputs["imagef_tmean"] = str(image_tmean_path)
        logger.info(f"Output: temporal mean generated - {os.path.basename(image_tmean_path)}")
    
    logger.info(f"Workflow: reorient completed - {len([v for v in outputs.values() if v is not None])} outputs generated")
    return outputs


def conform_to_template(
    imagef: Union[str, Path],
    template_file: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    logger: Optional[logging.Logger] = None,
    modal: str = 'anat',
    skip_skullstripping: bool = False,
) -> Dict[str, str]:
    """Conform input image to template space using FLIRT rigid registration.
    
    This function performs the following steps:
    1. Skullstrips the input image using NHPskullstripNN (unless skip_skullstripping=True)
    2. prepare template for registration
    3. Performs FLIRT rigid registration
    4. prepare template for xfm application
    5. Applies transformation
    
    Args:
        imagef: Input image file (anatomical or functional)
        template_file: Template file path
        working_dir: Working directory for intermediate and output files
        output_name: Name of output conformed image file
        logger: Logger instance (optional, will create one if not provided)
        modal: Modality type ('anat' or 'func'), default is 'anat'
        skip_skullstripping: If True, skip skullstripping and assume input is already skullstripped (default: False)
        
    Returns:
        Dictionary with output file paths:
        - 'imagef_conformed': Path to conformed image
        - 'template_f': Path to resampled template file (for QC)
        - 'forward_xfm': Path to forward transformation matrix (.mat file)
        - 'inverse_xfm': Path to inverse transformation matrix (.mat file, may be None if inverse computation failed)
        
    Raises:
        FileNotFoundError: If input or template file doesn't exist
        RuntimeError: If any step fails (with suggestion to disable conform if needed)
        ValueError: If invalid parameters are provided
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    template_path = validate_input_file(template_file, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Hardcoded padding percentage
    padding_percentage = 0.2
    
    logger.info(f"Workflow: starting conform to template")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"Data: template - {os.path.basename(template_path)}")
    logger.info(f"System: working directory - {work_dir}")
    
    try:
        # ------------------------------------------------------------
        # Step 1: Skullstrip the input image using NHPskullstripNN (or skip if already skullstripped)
        brain_f = work_dir / 'brain_for_conform.nii.gz'
        if skip_skullstripping:
            logger.info(f"Step: skipping skullstripping - assuming input is already skullstripped")
            # Use input image directly as brain-extracted image
            # Copy to expected location for consistency
            shutil.copy2(str(image_path), str(brain_f))
            logger.info(f"Using input image directly as brain-extracted image: {brain_f}")
        else:
            logger.info(f"Step: skullstripping input image for registration")
            
            try:
                skull_result = apply_skullstripping(
                    imagef=str(image_path),
                    modal=modal,
                    working_dir=str(work_dir),
                    output_name='brain_for_conform.nii.gz',
                    config=None,  # Use defaults (gpu_device='auto')
                    logger=logger
                )
                
                # Get the brain mask and brain-extracted image paths
                mask_output = skull_result.get('brain_mask')
                brain_extracted = skull_result.get('imagef_skullstripped')
                
                if not mask_output or not os.path.exists(mask_output):
                    raise RuntimeError(f"Skullstripping failed: mask file not found at {mask_output}")
                if not brain_extracted or not os.path.exists(brain_extracted):
                    raise RuntimeError(f"Skullstripping failed: brain-extracted image not found at {brain_extracted}")
                
                # Move brain-extracted image to expected location
                if brain_extracted != str(brain_f):
                    shutil.move(brain_extracted, str(brain_f))
                
                logger.info(f"Brain-extracted image saved to: {brain_f}")
            except Exception as e:
                logger.error(f"Error during skullstripping: {e}")
                raise RuntimeError(
                    f"Conform step failed during skullstripping: {e}. "
                    f"If this issue persists, consider disabling conform by setting 'anat.conform.enabled: false' in your configuration."
                )

        # Step 2: prepare template for registration
        # Step 2.1: Pad the template to ensure input image is fully contained
        logger.info(f"Step: padding template (padding_percentage={padding_percentage})")
        img = nib.load(template_path)
        data = img.get_fdata()
        affine = img.affine.copy()
        header = img.header.copy()
        
        # Handle 4D images: if image has 4 dimensions, average the last dimension
        if data.ndim == 4:
            logger.warning(f"4D image detected (shape: {data.shape}). Averaging the last dimension.")
            data = np.mean(data, axis=-1)
            logger.info(f"Converted to 3D shape: {data.shape}")
        
        original_shape = data.shape[:3]
        logger.info(f"Template original shape: {original_shape}")
        
        # Calculate padding amounts for each dimension
        pad_amounts = (np.array(original_shape) * padding_percentage).astype(int)
        logger.info(f"Padding amounts (per side): {pad_amounts}")
        
        # Calculate new shape
        new_shape = original_shape + 2 * pad_amounts
        logger.info(f"Template new shape: {new_shape}")
        
        # Pad the data with zeros
        pad_width = tuple((pad, pad) for pad in pad_amounts)
        if len(data.shape) > 3:
            pad_width = pad_width + ((0, 0),) * (len(data.shape) - 3)
        
        padded_data = np.pad(data, pad_width, mode='constant', constant_values=0)
        logger.info(f"Padded data shape: {padded_data.shape}")
        
        # Update the affine matrix to account for padding
        pad_shift_voxel = -pad_amounts.astype(float)
        pad_shift_world = affine[:3, :3] @ pad_shift_voxel
        
        logger.debug(f"Padding shift in voxel space: {pad_shift_voxel}")
        logger.debug(f"Padding shift in world space: {pad_shift_world}")
        
        # Update the affine translation
        new_affine = affine.copy()
        new_affine[:3, 3] = affine[:3, 3] + pad_shift_world
        
        logger.debug(f"Original affine translation: {affine[:3, 3]}")
        logger.debug(f"New affine translation: {new_affine[:3, 3]}")
        
        # Create new image with padded data and updated affine
        new_img = nib.Nifti1Image(padded_data.astype(data.dtype), new_affine, header)
        new_img.header.set_xyzt_units('mm', 'sec')
        
        # Save the padded template
        template_f_padded = work_dir / 'template_padded.nii.gz'
        logger.info(f"Saving zero-padded template: {template_f_padded}")
        nib.save(new_img, template_f_padded)
        
        # Validate the saved file exists
        validate_output_file(template_f_padded, logger)
        logger.info(f"Step: template padding completed")

        # Update template path for next steps
        template_f_for_reg = str(template_f_padded)
        
        # Step 2.2: Downsample the template if needed
        # To save computational cost and improve registration, downsample the template if:
        # a) if any template voxel size < brain target voxel size, downsample template to match brain resolution
        # b) if brain resolution < downsample_voxel_size threshold, cap at downsample_voxel_size
        orig_template_voxel_sizes = np.sqrt(np.sum(nib.load(template_f_for_reg).affine[:3, :3] ** 2, axis=0))
        downsample_voxel_size_threshold = 0.5  # Minimum voxel size threshold (mm)
        
        # Load the input image to determine target voxel sizes
        brain_affine = nib.load(brain_f).affine
        
        orig_brain_voxel_sizes = np.sqrt(np.sum(brain_affine[:3, :3] ** 2, axis=0))
        logger.info(f"Input voxel sizes: {np.array2string(orig_brain_voxel_sizes, precision=4, suppress_small=True)} mm")
        
        brain_voxel_sizes = np.round(np.min(orig_brain_voxel_sizes), 2)
        if brain_voxel_sizes <= 0:
            raise ValueError(f"Invalid target voxel size: {brain_voxel_sizes} mm")
        target_voxel_sizes = np.full((3,), brain_voxel_sizes)
        logger.info(f"Target voxel sizes: {target_voxel_sizes} mm")

        # determine if downsampling is needed
        should_downsample = False
        downsample_voxel_sizes = None
        # Give 0.01 mm tolerance for floating point comparison
        if any(orig_template_voxel_sizes < target_voxel_sizes - 0.01):
            should_downsample = True
            downsample_voxel_sizes = target_voxel_sizes.copy()
            # If brain resolution is finer than threshold, cap downsampling at threshold
            if any(target_voxel_sizes < downsample_voxel_size_threshold - 0.01):
                downsample_voxel_sizes = np.full((3,), downsample_voxel_size_threshold)
                logger.info(f"Brain resolution ({target_voxel_sizes[0]:.3f} mm) is finer than threshold ({downsample_voxel_size_threshold} mm), capping downsampling at {downsample_voxel_size_threshold} mm")

        if should_downsample:
            template_f_downsampled = Path(str(template_f_padded).split('.nii.gz')[0] + '_downsampled.nii.gz')
            logger.info(f"Template voxel sizes: {np.array2string(orig_template_voxel_sizes, precision=4, suppress_small=True)} mm")
            logger.info(f"Downsampling template to: {np.array2string(downsample_voxel_sizes, precision=4, suppress_small=True)} mm")
            cmd = [
                '3dresample',
                '-dxyz', str(downsample_voxel_sizes[0]), str(downsample_voxel_sizes[1]), str(downsample_voxel_sizes[2]),
                '-input', template_f_for_reg,
                '-prefix', str(template_f_downsampled),
                '-rmode', 'Cu'
            ]
            logger.debug(f"Command: {' '.join(cmd)}")
            try:
                returncode, stdout, stderr = run_command(cmd, step_logger=logger)
                if returncode != 0:
                    raise RuntimeError(f"3dresample failed (exit code {returncode}): {stderr}")
            except Exception as e:
                logger.error(f"Error during template downsampling: {e}")
                raise RuntimeError(f"Conform step failed during template downsampling: {e}.")
            validate_output_file(template_f_downsampled, logger)
            logger.info(f"Step: template downsampled to {downsample_voxel_sizes[0]:.3f} mm")

            template_f_for_reg = str(template_f_downsampled)

        # ------------------------------------------------------------
        # Step 3: FLIRT rigid registration
        try:
            # Set modality-specific FLIRT parameters
            if modal == 'anat':
                flirt_config = {
                    "registration": {
                        "flirt": {
                            "cost": "corratio",
                            "searchcost": "corratio",
                            "coarsesearch": 40,
                            "finesearch": 15
                        }
                    }
                }
            else:  # modal == 'func'
                flirt_config = {
                    "registration": {
                        "flirt": {
                            "cost": "mutualinfo",
                            "searchcost": "mutualinfo",
                            "coarsesearch": 30,
                            "finesearch": 10
                        }
                    }
                }
            
            registration_result = flirt_register(
                fixedf=template_f_for_reg,
                movingf=str(brain_f),
                working_dir=str(work_dir),
                output_prefix='conform_scanner2native',
                config=flirt_config,
                logger=logger,
                dof=6
            )
            xfm_forward_f = Path(registration_result['forward_transform'])
            xfm_inverse_f = Path(registration_result.get('inverse_transform')) if 'inverse_transform' in registration_result else None
        except Exception as e:
            logger.error(f"Error during FLIRT registration: {e}")
            raise RuntimeError(
                f"Conform step failed during FLIRT registration: {e}. "
            )

        # ------------------------------------------------------------
        # Step 4: prepare template for xfm application
        # Resample template to the same resolution as the input, serves as the reference
        template_f_for_xfm = work_dir / 'template_for_xfm.nii.gz'
        
        if template_f_for_xfm.exists():
            template_f_for_xfm.unlink()
            logger.debug(f"Removed existing template resampled file: {template_f_for_xfm}")

        # Resample to isotropic using minimum brain_voxel_sizes (target voxel size)
        cmd = [
            '3dresample',
            '-dxyz', str(target_voxel_sizes[0]), str(target_voxel_sizes[1]), str(target_voxel_sizes[2]),
            '-input', str(template_f_for_reg),
            '-prefix', str(template_f_for_xfm)
        ]
        logger.debug(f"Command: {' '.join(cmd)}")
        try:
            returncode, stdout, stderr = run_command(cmd, step_logger=logger)
            if returncode != 0:
                raise RuntimeError(f"3dresample failed (exit code {returncode}): {stderr}")
            
            # Validate resampled template exists
            validate_output_file(template_f_for_xfm, logger)
            logger.info(f"Template resampled to: {template_f_for_xfm}")
        except Exception as e:
            logger.error(f"Error during template resampling: {e}")
            raise RuntimeError(
                f"Conform step failed during template resampling: {e}. "
                f"If this issue persists, consider disabling conform by setting 'anat.conform.enabled: false' in your configuration."
            )
        
        logger.info(f"Step: resampling template to input resolution")

        # ------------------------------------------------------------
        # Step 5: Apply the affine transformation to the input image
        try:
            apply_result = flirt_apply_transforms(
                movingf=str(image_path),
                outputf_name=output_name,
                reff=str(template_f_for_xfm),
                working_dir=str(work_dir),
                transformf=str(xfm_forward_f),
                logger=logger,
                interpolation='trilinear',
                generate_tmean=False  # Not needed for anatomical conform
            )
            conformed_f = Path(apply_result['imagef_registered'])
        except Exception as e:
            logger.error(f"Error during affine transformation application: {e}")
            raise RuntimeError(
                f"Conform step failed when applying transformation: {e}. "
                f"If this issue persists, consider disabling conform by setting 'anat.conform.enabled: false' in your configuration."
            )
        
        logger.info(f"Workflow: conform to template completed successfully")
        
        # Build return dictionary
        result = {
            "imagef_conformed": str(conformed_f),
            "template_f": str(template_f_for_xfm),
            "forward_xfm": str(xfm_forward_f)
        }
        
        # Add inverse transform if available
        if xfm_inverse_f is not None and xfm_inverse_f.exists():
            result["inverse_xfm"] = str(xfm_inverse_f)
        else:
            result["inverse_xfm"] = None
        
        return result
        
    except (FileNotFoundError, ValueError) as e:
        # Re-raise these without modification
        raise
    except Exception as e:
        logger.error(f"Workflow: conform to template failed: {str(e)}")
        raise RuntimeError(
            f"Conform step failed: {str(e)}. "
            f"If this issue persists, consider disabling conform by setting 'anat.conform.enabled: false' in your configuration."
        )


def _determine_tpattern(slice_timings: List[Union[float, int]], direction: str = "z") -> str:
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


def slice_timing_correction(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
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
    if logger is None:
        logger = logging.getLogger(__name__)
    
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
    tpattern = _determine_tpattern(slice_timing_data, slice_encoding_direction)
    if tpattern == 'unknown':
        # skip slice timing correction
        logger.warning("Step: unknown slice timing pattern - skipping slice timing correction")
        return outputs
    
    logger.info(f"Data: slice timing pattern - {tpattern}, slice encoding direction - {slice_encoding_direction}")

    # double check whether the slice in the encoding direction is matching the slice_timing_data
    img_shape_original = get_image_shape(image_path, logger)
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
            # Extract just the filename part to avoid double work_dir in path
            output_path_str = str(outputs["imagef_slice_time_corrected"])
            output_filename = Path(output_path_str).stem.replace('.nii', '')  # Remove .nii.gz extension
            tmean_path = str(work_dir / f"{output_filename}_tmean.nii.gz")
            calculate_func_tmean(outputs["imagef_slice_time_corrected"], tmean_path, logger)
            outputs["imagef_slice_time_corrected_tmean"] = tmean_path
            logger.info(f"Output: Tmean of slice time corrected func_all - {os.path.basename(tmean_path)}")

        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: slice timing correction failed: {str(e)}")
        raise RuntimeError(f"Slice timing correction failed: {e}") from e

# 
def motion_correction(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
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
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Get configuration from new nested structure
    motion_cfg = config.get('func', {}).get('motion_correction')
    if not motion_cfg:
        raise ValueError("func.motion_correction configuration not found")
    
    output_path = work_dir / output_name
    
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
    shape = get_image_shape(image_path, logger)
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
    ref_file_path = work_dir / 'func_mc_ref.nii.gz'

    ref_vol = motion_cfg.get('ref_vol')
    if isinstance(ref_vol, int):
        command_ref = ['fslroi', str(image_path), str(ref_file_path), str(ref_vol), '1']
        logger.info(f"Step: using reference timepoint")
        logger.info(f"Data: reference timepoint - {ref_vol}")
    elif ref_vol == 'Tmean':
        command_ref = ['fslmaths', str(image_path), '-Tmean', str(ref_file_path)]
        logger.info(f"Step: using temporal mean as reference")
        logger.info(f"Data: reference type - Tmean")
    elif ref_vol == 'mid':
        # We already have nvols from above
        mid_vol = nvols // 2
        command_ref = ['fslroi', str(image_path), str(ref_file_path), str(mid_vol), '1']
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
        raise RuntimeError(f"Reference volume generation failed: {e}") from e


    # Build motion correction command
    output_prefix = str(output_path).split('.nii')[0]
    command_mcflirt = [
        'mcflirt',
        '-in', str(image_path),
        '-out', output_prefix,
        '-dof', str(motion_cfg.get('dof')),
        '-reffile', str(ref_file_path),
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
            # Extract just the filename part to avoid double work_dir in path
            output_path_str = str(outputs["imagef_motion_corrected"])
            output_filename = Path(output_path_str).stem.replace('.nii', '')  # Remove .nii.gz extension
            tmean_path = str(work_dir / f"{output_filename}_tmean.nii.gz")
            calculate_func_tmean(outputs["imagef_motion_corrected"], tmean_path, logger)
            outputs["imagef_motion_corrected_tmean"] = tmean_path
            logger.info(f"Output: Tmean of motion corrected func_all - {os.path.basename(tmean_path)}")

        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: motion correction failed: {str(e)}")
        raise RuntimeError(f"Motion correction failed: {e}") from e

def despike(
    imagef: Union[str, Path], 
    working_dir: Union[str, Path], 
    output_name: str, 
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
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
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)

    outputs = {"imagef_despiked": None}
    if generate_tmean:
        outputs["imagef_despiked_tmean"] = None

    # check if the input is 4D and the last dimension is larger than 15
    image_shape = get_image_shape(image_path, logger)
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
    output_path = work_dir / output_name
    spikiness_path = work_dir / output_name.replace('.nii.gz', '_spikiness.nii.gz')
    
    logger.info(f"Workflow: starting despiking")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: output path - {output_path}")

    # Build command
    command_despike = [
        '3dDespike',
        '-prefix', str(output_path),
        '-ssave', str(spikiness_path),
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
            # Extract just the filename part to avoid double work_dir in path
            # Use output_name directly to get just the filename without directory
            output_filename = output_name.split('.nii')[0]
            tmean_path = str(work_dir / f"{output_filename}_tmean.nii.gz")
            calculate_func_tmean(outputs["imagef_despiked"], tmean_path, logger)
            outputs["imagef_despiked_tmean"] = tmean_path
            logger.info(f"Output: Tmean of despiked func_all - {os.path.basename(tmean_path)}")

        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: despiking failed: {str(e)}")
        raise RuntimeError(f"Despiking failed: {e}") from e

def apply_segmentation(
    imagef: Union[str, Path],
    modal: str,
    working_dir: Union[str, Path],
    output_name: str,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """Perform brain segmentation using FastSurferCNN.
    
    This function performs multi-class atlas segmentation using FastSurferCNN,
    which produces a brain mask, segmentation, and optionally a hemimask.
    
    Args:
        imagef: Input file (functional or anatomical)
        modal: Modality ('func' or 'anat')
        working_dir: Working directory for this step
        output_name: Name of output file
        config: Configuration dictionary
        logger: Logger instance (optional)
        
    Returns:
        Dictionary with output file paths:
        - 'imagef_skullstripped': Path to skull-stripped image
        - 'brain_mask': Path to brain mask file
        - 'segmentation': Path to segmentation file (optional, if generated)
        - 'hemimask': Path to hemisphere mask file (optional, if generated)
        - 'atlas_lut': Path to atlas ColorLUT TSV (optional, same base as segmentation, .tsv)
        - 'atlas_name': Name of atlas used (optional)
        - 'input_cropped': Path to cropped input (optional, if two-pass refinement used)
        
    Raises:
        FileNotFoundError: If input file or model doesn't exist
        RuntimeError: If segmentation fails
        ValueError: If configuration or modal parameters are invalid
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Validate modal parameter
    if modal not in ['func', 'anat']:
        raise ValueError(f"Invalid modality: {modal}. Must be 'func' or 'anat'")
    
    # Get configuration
    # For anat, use skullstripping_segmentation; for func, use skullstripping
    config_key = 'skullstripping_segmentation' if modal == 'anat' else 'skullstripping'
    skull_cfg = config.get(modal, {}).get(config_key)
    if not skull_cfg:
        raise ValueError(f"{config_key} configuration not found")
    
    # Define output paths at the beginning
    brain_mask_path = work_dir / 'brain_mask.nii.gz'
    
    # Initialize optional output paths (for FastSurferCNN)
    brain_segmentation_path = None
    brain_hemimask_path = None
    brain_input_cropped_path = None
    brain_lut_path = None
    atlas_name = None

    # FastSurferCNN segmentation
    logger.info(f"Workflow: starting segmentation using FastSurferCNN")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: output path - {brain_mask_path}")
    
    # Get FastSurferCNN configuration parameters
    fscnn_cfg = skull_cfg.get('fastSurferCNN', {})
        
    # Create temporary output directory for FastSurferCNN
    # FastSurferCNN needs a directory, not a file path
    temp_output_dir = work_dir / 'fastsurfercnn_output'
    os.makedirs(temp_output_dir, exist_ok=True)
    
    try:
        # Get fix_roi_wm and roi_name settings from config
        # Support legacy 'fix_V1_WM' config key for backward compatibility
        if 'fix_V1_WM' in fscnn_cfg:
            fix_roi_wm = fscnn_cfg.get('fix_V1_WM', False)
            roi_name = 'V1' if fix_roi_wm else fscnn_cfg.get('roi_name', 'V1')
        else:
            # Use explicit fix_roi_wm and roi_name settings
            # For anatomical data, default to True (models typically generate hemimasks)
            # For functional data, default to False (may use binary mask models without hemimasks)
            fix_roi_wm_default = True if modal == 'anat' else False
            fix_roi_wm = fscnn_cfg.get('fix_roi_wm', fix_roi_wm_default)
            roi_name = fscnn_cfg.get('roi_name', 'V1')
        
        # Call FastSurferCNN segmentation function
        # Note: This is the FastSurferCNN.inference.run_segmentation function imported at the top
        # Build kwargs, only include roi_name and wm_thr if fix_roi_wm is True
        segmentation_kwargs = {
            "input_image": image_path,
            "modal": modal,
            "output_dir": temp_output_dir,
            "device_id": fscnn_cfg.get('gpu_device', 'auto'),
            "logger": logger,
            "output_data_format": 'nifti',
            "enable_crop_2round": False,
            "plane_weight_coronal": fscnn_cfg.get('plane_weight_coronal'),
            "plane_weight_axial": fscnn_cfg.get('plane_weight_axial'),
            "plane_weight_sagittal": fscnn_cfg.get('plane_weight_sagittal'),
            "use_mixed_model": fscnn_cfg.get('use_mixed_model', False),
            "fix_roi_wm": fix_roi_wm,
        }
        # Only pass roi_name and wm_thr if fix_roi_wm is True
        if fix_roi_wm:
            segmentation_kwargs["roi_name"] = roi_name
            segmentation_kwargs["wm_thr"] = fscnn_cfg.get('wm_thr', 0.5)

        result = run_segmentation(**segmentation_kwargs)
        
        # Extract brain mask path and atlas_name from result
        fastsurfercnn_mask_path = result.get('brain_mask')
        if not fastsurfercnn_mask_path or not os.path.exists(fastsurfercnn_mask_path):
            raise FileNotFoundError(f"FastSurferCNN did not generate brain mask at expected location: {fastsurfercnn_mask_path}")
        
        # Extract atlas_name if available
        atlas_name = result.get('atlas_name')
        
        # Move the brain mask to the expected location
        shutil.move(fastsurfercnn_mask_path, brain_mask_path)
        logger.info("Workflow: FastSurferCNN segmentation completed successfully")
        logger.info(f"Output: brain mask moved from {fastsurfercnn_mask_path} to {brain_mask_path}")
        
        # Move segmentation if it exists
        fastsurfercnn_seg_path = result.get('segmentation')
        if fastsurfercnn_seg_path and os.path.exists(fastsurfercnn_seg_path):
            brain_segmentation_path = work_dir / 'brain_segmentation.nii.gz'
            shutil.move(fastsurfercnn_seg_path, brain_segmentation_path)
            logger.info(f"Output: brain segmentation moved from {fastsurfercnn_seg_path} to {brain_segmentation_path}")
            # Move LUT alongside segmentation (same base name, .nii.gz → .tsv)
            fastsurfercnn_lut_path = temp_output_dir / 'segmentation_lut.tsv'
            if fastsurfercnn_lut_path.exists():
                brain_lut_path = work_dir / 'brain_segmentation.tsv'
                shutil.move(str(fastsurfercnn_lut_path), str(brain_lut_path))
                logger.info(f"Output: atlas LUT moved from {fastsurfercnn_lut_path.name} to {brain_lut_path.name}")
        
        # Move hemimask if it exists
        fastsurfercnn_hemimask_path = result.get('hemimask')
        if fastsurfercnn_hemimask_path and os.path.exists(fastsurfercnn_hemimask_path):
            brain_hemimask_path = work_dir / 'brain_hemimask.nii.gz'
            shutil.move(fastsurfercnn_hemimask_path, brain_hemimask_path)
            logger.info(f"Output: brain hemimask moved from {fastsurfercnn_hemimask_path} to {brain_hemimask_path}")
        
        # Move input cropped if it exists
        fastsurfercnn_input_cropped_path = result.get('input_cropped')
        if fastsurfercnn_input_cropped_path and os.path.exists(fastsurfercnn_input_cropped_path):
            brain_input_cropped_path = work_dir / 'brain_input_cropped.nii.gz'
            shutil.move(fastsurfercnn_input_cropped_path, brain_input_cropped_path)
            logger.info(f"Output: brain input cropped moved from {fastsurfercnn_input_cropped_path} to {brain_input_cropped_path}")

    except Exception as e:
        logger.error(f"Workflow: FastSurferCNN segmentation failed - {str(e)}")
        raise RuntimeError(f"FastSurferCNN segmentation failed: {e}") from e
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
    
    output_path = work_dir / output_name
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
    if brain_lut_path is not None and os.path.exists(brain_lut_path):
        return_dict["atlas_lut"] = brain_lut_path

    return return_dict


def apply_skullstripping(
    imagef: Union[str, Path],
    modal: str,
    working_dir: Union[str, Path],
    output_name: str,
    config: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """Perform skullstripping using NHPskullstripNN.
    
    This function performs binary brain mask generation using NHPskullstripNN.
    It is used for functional data and conform step where only a brain mask is needed.
    
    Args:
        imagef: Input file (functional or anatomical)
        modal: Modality ('func' or 'anat')
        working_dir: Working directory for this step
        output_name: Name of output file
        config: Configuration dictionary (optional). If provided, should have structure
                {modal: {'skullstripping': {'gpu_device': ...}}}. If None, uses defaults.
        logger: Logger instance (optional)
        
    Returns:
        Dictionary with output file paths:
        - 'imagef_skullstripped': Path to skull-stripped image
        - 'brain_mask': Path to brain mask file
        
    Raises:
        FileNotFoundError: If input file or model doesn't exist
        RuntimeError: If skull stripping fails
        ValueError: If configuration or modal parameters are invalid
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Validate modal parameter
    if modal not in ['func', 'anat']:
        raise ValueError(f"Invalid modality: {modal}. Must be 'func' or 'anat'")
    
    # Get configuration - use defaults if not provided
    if config is not None:
        skull_cfg = config.get(modal, {}).get('skullstripping', {})
        device_id = skull_cfg.get('gpu_device', 'auto')
    else:
        device_id = 'auto'
    
    # Define output paths
    brain_mask_path = work_dir / 'brain_mask.nii.gz'
    
    # Use NHPskullstripNN for skullstripping
    logger.info(f"Workflow: starting skullstripping using NHPskullstripNN")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"System: output path - {brain_mask_path}")
    
    try:
        
        result = skullstripping(
            input_image=str(image_path),
            modal=modal,
            output_path=str(brain_mask_path),
            device_id=device_id
        )
        
        # Extract brain mask path from result
        nhp_mask_path = result.get('brain_mask')
        if not nhp_mask_path or not os.path.exists(nhp_mask_path):
            raise FileNotFoundError(f"NHPskullstripNN did not generate brain mask at expected location: {nhp_mask_path}")
        
        # Move mask to expected location if needed
        if nhp_mask_path != brain_mask_path:
            shutil.move(nhp_mask_path, brain_mask_path)
            logger.info(f"Output: brain mask moved from {nhp_mask_path} to {brain_mask_path}")
        
        logger.info("Workflow: NHPskullstripNN completed successfully")
        
    except Exception as e:
        logger.error(f"Workflow: NHPskullstripNN failed - {str(e)}")
        raise RuntimeError(
            f"Skullstripping failed: {e}. "
            f"If this issue persists, consider disabling skullstripping in your configuration."
        )
    
    # Validate brain mask
    validate_output_file(brain_mask_path, logger)
    logger.info(f"Output: brain mask generated - {os.path.basename(brain_mask_path)}")
    
    # Apply brain mask to input image
    output_path = work_dir / output_name
    command_apply = [
        'fslmaths', str(image_path),
        '-mas', str(brain_mask_path),
        str(output_path)
    ]
    returncode, stdout, stderr = run_command(command_apply, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"fslmaths failed (exit code {returncode}): {stderr}")
    
    # Validate final output
    validate_output_file(output_path, logger)
    logger.info(f"Output: skull stripped image generated - {os.path.basename(output_path)}")
    
    return {
        "imagef_skullstripped": output_path,
        "brain_mask": brain_mask_path
    }


def apply_mask(
    imagef: Union[str, Path],
    maskf: Union[str, Path],
    working_dir: Union[str, Path],
    output_name: str,
    logger: Optional[logging.Logger] = None,
    generate_tmean: bool = False,
) -> Dict[str, Optional[str]]:
    """Apply a mask to an image (3D or 4D) using FSL.

    Shared helper for both the Python step wrappers and Nextflow inline scripts.
    Uses ``fslmaths -mas`` and can optionally compute a temporal mean (tmean) for 4D data.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    image_path = validate_input_file(imagef, logger)
    mask_path = validate_input_file(maskf, logger)
    work_dir = ensure_working_directory(working_dir, logger)

    outputs: Dict[str, Optional[str]] = {
        "imagef_masked": None,
        "imagef_masked_tmean": None,
        "mask_used": None,
    }

    output_path = work_dir / output_name
    logger.info("Workflow: starting apply_mask")
    logger.info(f"Data: input image - {os.path.basename(image_path)}")
    logger.info(f"Data: input mask - {os.path.basename(mask_path)}")
    logger.info(f"System: output path - {output_path}")

    # Binarize mask
    mask_to_use = Path(mask_path)
    mask_binarized = work_dir / "mask_binarized.nii.gz"
    cmd_mask_bin = [
        "fslmaths",
        str(mask_to_use),
        "-abs",
        "-bin",
        str(mask_binarized),
    ]
    returncode, stdout, stderr = run_command(cmd_mask_bin, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"Mask binarization failed (exit code {returncode}): {stderr}")
    validate_output_file(mask_binarized, logger)
    mask_to_use = mask_binarized

    # Apply mask
    cmd_apply = [
        "fslmaths",
        str(Path(image_path)),
        "-mas",
        str(mask_to_use),
        str(output_path),
    ]
    returncode, stdout, stderr = run_command(cmd_apply, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"fslmaths failed (exit code {returncode}): {stderr}")

    validate_output_file(output_path, logger)
    outputs["imagef_masked"] = str(output_path)
    outputs["mask_used"] = str(mask_to_use)

    if generate_tmean:
        tmean_path = work_dir / (output_name.split(".nii")[0] + "_tmean.nii.gz")
        calculate_func_tmean(str(output_path), str(tmean_path), logger)
        outputs["imagef_masked_tmean"] = str(tmean_path)

    logger.info("Workflow: apply_mask completed successfully")
    return outputs

def bias_correction(
    imagef: Union[str, Path],
    working_dir: Union[str, Path],
    modal: str,
    output_name: str,
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
    maskf: Optional[Union[str, Path]] = None,
) -> Dict[str, str]:
    """Perform bias field correction using ANTs N4BiasFieldCorrection.
    
    Args:
        imagef: Input image file
        working_dir: Working directory
        modal: Modality ('func' or 'anat')
        output_name: Name of output file
        config: Configuration dictionary
        logger: Logger instance
        maskf: Optional mask file for bias correction (if provided, will use -x flag)
        
    Returns:
        Dictionary with output file paths:
        - 'imagef_bias_corrected': Bias-corrected image
        - 'bias_field': Bias field map
        - 'imagef_brain': Brain-only image (if mask provided and not dummy)
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If bias correction fails
        ValueError: If configuration parameters are invalid
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Validate inputs
    image_path = validate_input_file(imagef, logger)
    work_dir = ensure_working_directory(working_dir, logger)
    
    # Get image shape and calculate dimension from it
    image_shape = get_image_shape(image_path, logger)
    
    # Make sure the input image is 3D, not 4D (4th dimension must be 1 if present)
    if len(image_shape) > 3 and image_shape[3] != 1:
        raise ValueError("Input image is not 3D, must be 3D for bias correction")

    # Calculate dimension from image shape (number of spatial dimensions)
    # Count non-singleton dimensions, but cap at 3 for spatial dimensions
    # This handles 2D [x,y], 3D [x,y,z], and 4D with t=1 [x,y,z,1] cases
    non_singleton_dims = [d for d in image_shape if d > 1]
    dimension = min(len(non_singleton_dims), 3)
    
    if dimension < 2 or dimension > 3:
        raise ValueError(f"Unsupported image dimension: {dimension}. Expected 2 or 3 spatial dimensions.")

    # Get configuration
    bias_cfg = config.get(modal, {}).get('bias_correction')
    if not bias_cfg:
        raise ValueError("bias_correction configuration not found")

    # Rescale image mean to 100 if configured
    rescale_mean_to_100 = bias_cfg.get('rescale_mean_to_100')
    if rescale_mean_to_100:
        image_path_rescaled = work_dir / "input_rescaled.nii.gz"
        
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

    output_path = work_dir / output_name
    bias_field_path = work_dir / (output_name.split('.nii')[0] + '_bias_field.nii.gz')

    # Get thread count from environment variable (set by Nextflow)
    import os
    num_threads = int(os.environ.get('OMP_NUM_THREADS', 8))
    
    # Set up ITK thread environment variables for subprocess
    from ..utils.system import set_numerical_threads
    env = set_numerical_threads(num_threads, include_itk=True, return_dict=True)
    # Merge with current environment to preserve other variables
    env = {**os.environ, **env}

    # Get mask path if provided (mask is already validated as real in workflow)
    mask_path = None
    if maskf:
        mask_path = validate_input_file(maskf, logger)
        logger.info(f"Workflow: using mask for bias correction - {os.path.basename(mask_path)}")
    
    # Build command
    if bias_cfg.get('algorithm') == 'N4BiasFieldCorrection':
        logger.info(f"Workflow: starting bias field correction using N4BiasFieldCorrection algorithm")
        logger.info(f"Data: input image - {os.path.basename(image_path)}, dimension - {dimension}")
        logger.info(f"System: output path - {output_path}")
        logger.info(f"System: using {num_threads} threads for ITK operations (capped at 32)")
        command = [
            'N4BiasFieldCorrection',
            '-d', str(dimension),
            '-i', str(image_path),
            '-o', f"[{output_path},{bias_field_path}]",
            '-s', str(bias_cfg.get('shrink_factor')),
            '-b', str(bias_cfg.get('bspline_fitting'))
        ]
        # Add mask if provided
        if mask_path:
            command.extend(['-x', str(mask_path)])
            logger.info(f"Workflow: using mask for bias correction")
    else:
        # TODO: add other bias correction algorithms
        pass

    # Execute command with thread-limited environment
    try:
        returncode, stdout, stderr = run_command(command, env=env, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"N4BiasFieldCorrection failed (exit code {returncode}): {stderr}")
        
        logger.info("Workflow: N4BiasFieldCorrection completed successfully")
        
        # Validate outputs
        validate_output_file(output_path, logger)
        outputs = {
            "imagef_bias_corrected": output_path,
            "bias_field": bias_field_path
        }
        
        # If mask is provided, apply mask to generate brain-only image
        if mask_path:
            brain_output_name = output_name.replace('.nii.gz', '_brain.nii.gz')
            if brain_output_name == output_name:  # In case output_name doesn't have .nii.gz
                brain_output_name = output_name.split('.')[0] + '_brain.nii.gz'
            brain_output_path = work_dir / brain_output_name
            
            logger.info(f"Workflow: applying mask to bias-corrected image to generate brain-only version")
            logger.info(f"System: brain output path - {brain_output_path}")
            
            # Apply mask using fslmaths
            command_apply_mask = [
                'fslmaths', str(output_path),
                '-mas', str(mask_path),
                str(brain_output_path)
            ]
            returncode, stdout, stderr = run_command(command_apply_mask, step_logger=logger)
            if returncode != 0:
                raise RuntimeError(f"fslmaths failed when applying mask (exit code {returncode}): {stderr}")
            
            validate_output_file(brain_output_path, logger)
            outputs["imagef_brain"] = brain_output_path
            logger.info(f"Workflow: brain-only image generated - {os.path.basename(brain_output_path)}")
        
        return outputs
        
    except Exception as e:
        logger.error(f"Workflow: bias field correction failed: {str(e)}")
        raise RuntimeError(f"Bias field correction failed: {e}") from e


def generate_t1wt2wcombined(
    t1w_file: Union[str, Path],
    t2w_file: Union[str, Path],
    segmentation_file: Union[str, Path],
    segmentation_lut_file: Union[str, Path],
    output_file: Union[str, Path],
    logger: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """
    Generate T1wT2wCombined image from T1w, T2w, and segmentation.
    
    The combined image is computed as: (T1w - sT2w) / (T1w + sT2w)
    where sT2w is T2w scaled by gray matter intensity ratio:
    sT2w = (T1w_GM_intensity / T2w_GM_intensity) * T2w
    
    Gray matter regions are identified from the segmentation LUT
    where region == 'cortex'.
    
    Args:
        t1w_file: Path to T1w image file
        t2w_file: Path to T2w image file (must be in same space as T1w)
        segmentation_file: Path to segmentation file (e.g., aparc+aseg.orig.nii.gz)
        segmentation_lut_file: Path to segmentation LUT TSV file
        output_file: Path for output combined image
        logger: Optional logger instance
        
    Returns:
        Dictionary with key 'combined_image' containing output file path
        
    Raises:
        FileNotFoundError: If any input file is missing
        ValueError: If segmentation LUT doesn't contain cortex regions
        RuntimeError: If computation fails
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    t1w_file = Path(t1w_file)
    t2w_file = Path(t2w_file)
    segmentation_file = Path(segmentation_file)
    segmentation_lut_file = Path(segmentation_lut_file)
    output_file = Path(output_file)
    
    # Validate input files (NIfTI files only - LUT is TSV, validate separately)
    validate_input_file(t1w_file, logger)
    validate_input_file(t2w_file, logger)
    validate_input_file(segmentation_file, logger)
    
    # Validate LUT file (TSV file, not NIfTI)
    if not segmentation_lut_file.exists():
        raise FileNotFoundError(f"Segmentation LUT file not found: {segmentation_lut_file}")
    if not segmentation_lut_file.suffix == '.tsv':
        raise ValueError(f"Segmentation LUT file must be a TSV file, got: {segmentation_lut_file.suffix}")
    logger.info(f"Using segmentation LUT: {segmentation_lut_file.name}")
    
    try:
        logger.info(f"Generating T1wT2wCombined image from {t1w_file.name} and {t2w_file.name}")
        
        # Load segmentation
        seg_img = nib.load(str(segmentation_file))
        seg = seg_img.get_fdata().astype(int)
        
        # Load T1w and T2w
        t1w_img = nib.load(str(t1w_file))
        t1w = t1w_img.get_fdata()
        t2w_img = nib.load(str(t2w_file))
        t2w = t2w_img.get_fdata()
        
        # Load segmentation LUT
        seg_lut = pd.read_csv(str(segmentation_lut_file), sep='\t')
        
        # Get gray matter intensity from T1w image using seg
        # mask should be keys with "region" column == 'cortex'
        if 'region' not in seg_lut.columns:
            raise ValueError(f"Segmentation LUT must have 'region' column. Found columns: {seg_lut.columns.tolist()}")
        
        gm_values = seg_lut[seg_lut['region'] == 'cortex']['ID'].values
        if len(gm_values) == 0:
            raise ValueError("No cortex regions found in segmentation LUT")
        
        gm_mask = np.isin(seg, gm_values).astype(bool)
        
        if not np.any(gm_mask):
            raise ValueError("No gray matter voxels found in segmentation")
        
        # Get gray matter intensity from T1w and T2w image using seg
        t1w_gm_intensity = t1w[gm_mask].mean()
        t2w_gm_intensity = t2w[gm_mask].mean()
        
        if t2w_gm_intensity == 0:
            raise ValueError("T2w gray matter intensity is zero, cannot compute scaling factor")
        
        logger.info(f"T1w GM intensity: {t1w_gm_intensity:.2f}, T2w GM intensity: {t2w_gm_intensity:.2f}")
        
        # Compute scaled T2w with T1w_GM_intensity / T2w_GM_intensity * T2w
        sT2w = (t1w_gm_intensity / t2w_gm_intensity) * t2w
        
        # Compute CI from: (T1w−sT2w)/(T1w+sT2w)
        dominator = t1w + sT2w
        dominator[dominator == 0] = 1e-6
        combined_image = (t1w - sT2w) / dominator

        # clip the image to [-1, 1]
        combined_image = np.nan_to_num(combined_image)
        combined_image = np.clip(combined_image, -1, 1)
        
        # Save output using T1w header and affine
        output_img = nib.Nifti1Image(combined_image, t1w_img.affine, t1w_img.header)
        output_img.to_filename(str(output_file), dtype=np.float32)
        
        validate_output_file(output_file, logger)
        logger.info(f"T1wT2wCombined image saved to {output_file.name}")
        
        return {
            "combined_image": str(output_file),
            "t1w_gm_intensity": float(t1w_gm_intensity),
            "t2w_gm_intensity": float(t2w_gm_intensity)
        }
        
    except Exception as e:
        logger.error(f"Failed to generate T1wT2wCombined image: {str(e)}")
        raise RuntimeError(f"T1wT2wCombined generation failed: {e}") from e
