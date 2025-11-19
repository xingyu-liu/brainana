# Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
High-level API for brain segmentation.

This module provides the main user-facing functions for running
segmentation and skullstripping on brain images.
"""

import copy
import shutil
import traceback
from pathlib import Path
from typing import Literal

import nibabel as nib
import numpy as np

from FastSurferCNN.data_loader import data_utils
from FastSurferCNN.inference.predictor import RunModelOnData
from FastSurferCNN.inference.predictor_utils import (
    crop_image_to_brain_mask,
    should_apply_refinement,
    validate_checkpoints,
    TWO_PASS_BRAIN_RATIO_THRESHOLD,
    TWO_PASS_CROP_MARGIN,
)
from FastSurferCNN.postprocessing.postseg_utils import (
    create_hemisphere_masks,
    create_mask,
)
from FastSurferCNN.utils import logging

LOGGER = logging.getLogger(__name__)

# Brain mask creation parameters
MASK_DILATION_SIZE = 5  # Dilation kernel size for mask creation
MASK_EROSION_SIZE = 4   # Erosion kernel size for mask creation


def _apply_two_pass_refinement(
    input_image: Path,
    output_dir: Path,
    file_ext: str,
    atlas_name: str,
    atlas_metadata: dict | None,
    ckpt_ax: Path | None,
    ckpt_sag: Path | None,
    ckpt_cor: Path | None,
    device: str,
    viewagg_device: str,
    threads: int,
    batch_size: int,
    plane_weight_coronal: float | None,
    plane_weight_axial: float | None,
    plane_weight_sagittal: float | None,
    fix_wm_islands: bool,
    output_data_format: Literal["mgz", "nifti"],
) -> bool:
    """
    Apply two-pass refinement: crop image and run fresh segmentation.
    
    This function moves first-pass outputs to pass_1/ directory, crops the 
    ORIGINAL input image using the brain mask, then runs a completely fresh
    segmentation on the cropped image. This avoids any state/affine issues
    from reusing the predictor.
    
    Parameters
    ----------
    input_image : Path
        Original input image path
    output_dir : Path
        Output directory
    file_ext : str
        File extension for output files
    atlas_name : str
        Name of the atlas
    atlas_metadata : dict, optional
        Atlas metadata from checkpoint
    ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
        Checkpoint paths for each plane
    device : str
        Device to run inference on
    viewagg_device : str
        Device to run view aggregation on
    threads : int
        Number of threads for CPU operations
    batch_size : int
        Batch size for inference
    plane_weight_coronal, plane_weight_axial, plane_weight_sagittal : float, optional
        Weights for multi-view prediction
    fix_wm_islands : bool
        Whether to apply WM island correction
    output_data_format : {"mgz", "nifti"}
        Output file format
        
    Returns
    -------
    bool
        True if refinement completed successfully, False if it failed
    """
    pass_1_dir = output_dir / "pass_1"
    pass_1_dir.mkdir(parents=True, exist_ok=True)
    
    LOGGER.info("Applying two-pass refinement...")
    LOGGER.info(f"  Moving first-pass outputs to {pass_1_dir.name}/")
    
    # Define first-pass files
    first_pass_files = {
        "segmentation": output_dir / f"segmentation{file_ext}",
        "mask": output_dir / f"mask{file_ext}",
    }
    
    # Check for hemimask
    hemi_mask_path = output_dir / f"mask_hemi{file_ext}"
    if hemi_mask_path.exists():
        first_pass_files["hemimask"] = hemi_mask_path
    
    try:
        # Step 1: Move first-pass outputs to pass_1 directory
        for key, src_path in first_pass_files.items():
            if src_path.exists():
                dst_path = pass_1_dir / src_path.name
                shutil.move(str(src_path), str(dst_path))
                LOGGER.info(f"  Moved {key}: {src_path.name}")
        
        # Step 2: Crop ORIGINAL input image using first-pass mask
        mask_path = pass_1_dir / f"mask{file_ext}"
        cropped_input_path = output_dir / f"input_cropped{file_ext}"
        
        LOGGER.info(f"  Cropping original input to brain region (margin={TWO_PASS_CROP_MARGIN*100:.0f}%)...")
        
        # Load original image to get its shape for logging
        orig_img = nib.load(input_image)
        
        cropped_img = crop_image_to_brain_mask(
            str(input_image),  # Crop the ORIGINAL input image
            str(mask_path),     # Using mask from first pass
            margin=TWO_PASS_CROP_MARGIN,
            save_path=cropped_input_path,
        )
        
        LOGGER.info(f"  ✓ Cropped: {orig_img.shape} → {cropped_img.shape}")
        LOGGER.info(f"  ✓ Space saved: {np.prod(orig_img.shape) / np.prod(cropped_img.shape):.1f}x reduction")
        LOGGER.info(f"  ✓ Saved cropped input: {cropped_input_path.name}")
        
        # Step 3: Run FRESH segmentation on cropped image (starting from scratch)
        LOGGER.info("  Running 2nd pass with fresh predictor on cropped image...")
        LOGGER.info("  (This runs the full pipeline from scratch - no state reuse)")
        
        run_segmentation(
            input_image=cropped_input_path,
            output_dir=output_dir,  # Outputs go back to main directory
            atlas_name=atlas_name,
            atlas_metadata=atlas_metadata,
            ckpt_ax=ckpt_ax,
            ckpt_sag=ckpt_sag,
            ckpt_cor=ckpt_cor,
            device=device,
            viewagg_device=viewagg_device,
            threads=threads,
            batch_size=batch_size,
            plane_weight_coronal=plane_weight_coronal,
            plane_weight_axial=plane_weight_axial,
            plane_weight_sagittal=plane_weight_sagittal,
            fix_wm_islands=fix_wm_islands,
            output_data_format=output_data_format,
            enable_crop_2round=False,  # Don't recurse!
        )
        
        LOGGER.info("  ✓ Two-pass refinement completed successfully")
        return True
        
    except Exception as e:
        LOGGER.error(f"  ✗ Two-pass refinement failed: {e}")
        LOGGER.debug(f"  Error details: {traceback.format_exc()}")
        LOGGER.warning("  Falling back to first-pass prediction")
        LOGGER.info(f"  First-pass outputs are available in {pass_1_dir.name}/")
        
        # Try to restore first-pass outputs to main directory
        try:
            LOGGER.info("  Restoring first-pass outputs to main directory...")
            for key, src_path in first_pass_files.items():
                dst_path = pass_1_dir / src_path.name
                if dst_path.exists():
                    shutil.copy(str(dst_path), str(src_path))
                    LOGGER.info(f"  Restored {key}: {src_path.name}")
        except Exception as restore_error:
            LOGGER.error(f"  Failed to restore first-pass outputs: {restore_error}")
        
        return False


def run_segmentation(
    input_image: str | Path,
    output_dir: str | Path,
    atlas_name: str,
    atlas_metadata: dict | None = None,
    ckpt_ax: Path | None = None,
    ckpt_sag: Path | None = None,
    ckpt_cor: Path | None = None,
    device: str = "auto",
    viewagg_device: str = "auto",
    threads: int = 1,
    batch_size: int = 1,
    plane_weight_coronal: float | None = None,
    plane_weight_axial: float | None = None,
    plane_weight_sagittal: float | None = None,
    fix_wm_islands: bool = True,
    output_data_format: Literal["mgz", "nifti"] = "nifti",
    enable_crop_2round: bool = False,
) -> dict[str, Path]:
    """
    Run segmentation and save outputs (segmentation, mask, hemimask) to output directory.
    
    This is a high-level convenience function that implements the automatic 
    "input space → model space → input space" workflow:
    1. Runs FastSurferCNN segmentation on the input image (in model space)
    2. Resamples segmentation back to native input space (in-memory, pure Python)
    3. Creates brain mask and hemisphere mask from the resampled segmentation
    4. Saves all outputs to the specified output directory (all in native space)
    
    All outputs are automatically in the same space as the input image.
    Uses pure Python resampling (no external tool dependencies).
    
    Parameters
    ----------
    input_image : str, Path
        Path to input image
    output_dir : str, Path
        Output directory where segmentation, mask, and hemimask will be saved
    atlas_name : str
        Name of the atlas (e.g., "ARM2", "ARM3")
    atlas_metadata : dict, optional
        Atlas metadata extracted from checkpoint
    ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
        Checkpoint paths for each plane
    device : str, default="auto"
        Device to run inference on
    viewagg_device : str, default="auto"
        Device to run view aggregation on
    threads : int, default=1
        Number of threads for CPU operations
    batch_size : int, default=1
        Batch size for inference
    plane_weight_coronal, plane_weight_axial, plane_weight_sagittal : float, optional
        Weights for multi-view prediction
    fix_wm_islands : bool, default=True
        Whether to apply WM island correction
    output_data_format : {"mgz", "nifti"}, default="nifti"
        Output file format. "mgz" saves as .mgz (MGH format), "nifti" saves as .nii.gz (NIfTI format).
        Resampling uses pure Python (in-memory), no external tools needed.
    enable_crop_2round : bool, default=False
        If True, enable two-pass refinement: after first pass, if brain occupies < 20% of FOV
        and image dimension > model height, crop the ORIGINAL input image to brain region 
        and run a completely fresh segmentation on it. First-pass outputs are moved to 
        output_dir/pass_1/, cropped input is saved as output_dir/input_cropped.{ext}, and 
        final outputs (from second pass) are saved to main output_dir in cropped image's native space.
        
    Note
    ----
    Preprocessing parameters (vox_size, orientation, image_size)
    are automatically read from checkpoint metadata (required), ensuring consistency
    with the training configuration.
    
    Returns
    -------
    dict[str, Path]
        Dictionary with keys:
        - 'segmentation': Path to saved segmentation file
        - 'mask': Path to saved brain mask file
        - 'hemimask': Path to saved hemisphere mask file (if created)
        - 'input_cropped': Path to cropped input (if two-pass refinement was applied)
    """
    input_image = Path(input_image)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate checkpoints
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)

    # Initialize predictor
    # Preprocessing parameters (vox_size, orientation, image_size)
    # are automatically read from checkpoint metadata if available
    predictor = RunModelOnData(
        atlas_name=atlas_name,
        atlas_metadata=atlas_metadata,
        ckpt_ax=ckpt_ax,
        ckpt_sag=ckpt_sag,
        ckpt_cor=ckpt_cor,
        device=device,
        viewagg_device=viewagg_device,
        threads=threads,
        batch_size=batch_size,
        plane_weight_coronal=plane_weight_coronal,
        plane_weight_axial=plane_weight_axial,
        plane_weight_sagittal=plane_weight_sagittal,
        fix_wm_islands=fix_wm_islands,
    )

    # Run prediction (returns segmentation in model/conformed space)
    LOGGER.info(f"Running segmentation on {input_image}")
    pred_data = predictor.get_prediction(str(input_image))

    # Map output format to file extension
    format_to_ext = {"mgz": ".mgz", "nifti": ".nii.gz"}
    file_ext = format_to_ext[output_data_format]
    seg_path = output_dir / f"segmentation{file_ext}"
    seg_path.parent.mkdir(parents=True, exist_ok=True)

    # Always resample to native space
    if predictor._should_resample():
        LOGGER.info("Resampling segmentation to native space...")
        pred_data_final = predictor._resample_to_native(
            pred_data, interpolation="nearest"
        )
        LOGGER.info(f"Successfully resampled segmentation (shape: {pred_data_final.shape})")
        
        data_utils.save_image(
            predictor._input_native_img.header,
            predictor._input_native_img.affine,
            pred_data_final,
            seg_path,
            dtype=np.int16,
        )
    else:
        # Input was already conformed - save directly (still in native space)
        LOGGER.info("No resampling needed - input was already conformed")
        data_utils.save_image(
            predictor._conformed_img.header,
            predictor._conformed_img.affine,
            pred_data,
            seg_path,
            dtype=np.int16,
        )
        pred_data_final = pred_data

    # Create masks from the final segmentation
    LOGGER.info("Creating brain mask...")
    brain_mask = create_mask(
        copy.deepcopy(pred_data_final),
        MASK_DILATION_SIZE,
        MASK_EROSION_SIZE,
    )
    brain_mask = brain_mask.astype(np.uint8)

    LOGGER.info("Creating hemisphere mask...")
    try:
        hemi_mask = create_hemisphere_masks(
            brain_mask, pred_data_final, lut_path=predictor.lut_path
        )
    except Exception as e:
        LOGGER.warning(f"Could not create hemisphere mask: {e}")
        hemi_mask = None

    # Save mask and hemimask
    # Get reference image for header/affine (always use native if available)
    if predictor._should_resample():
        reference_img = predictor._input_native_img
    else:
        reference_img = predictor._conformed_img

    mask_path = output_dir / f"mask{file_ext}"
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving brain mask to {mask_path}")
    data_utils.save_image(
        reference_img.header,
        reference_img.affine,
        brain_mask,
        mask_path,
        dtype=np.uint8,
    )

    if hemi_mask is not None:
        hemi_mask_path = output_dir / f"mask_hemi{file_ext}"
        hemi_mask_path.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.info(f"Saving hemisphere mask to {hemi_mask_path}")
        data_utils.save_image(
            reference_img.header,
            reference_img.affine,
            hemi_mask,
            hemi_mask_path,
            dtype=np.uint8,
        )
    else:
        hemi_mask_path = None

    # Build result dictionary
    result = {
        "segmentation": seg_path,
        "mask": mask_path,
    }
    if hemi_mask_path is not None:
        result["hemimask"] = hemi_mask_path

    # Check if two-pass refinement is needed
    if enable_crop_2round:
        # Get model height from checkpoint config
        model_height = predictor.cfg_fin.MODEL.HEIGHT
        
        # Check if refinement should be applied
        should_refine, brain_ratio, max_orig_dim = should_apply_refinement(
            brain_mask, reference_img, model_height
        )
        
        LOGGER.info(f"Checking two-pass refinement criteria...")
        LOGGER.info(f"  Brain occupancy: {brain_ratio*100:.1f}% of FOV")
        LOGGER.info(f"  Image dimensions: {reference_img.shape} (max: {max_orig_dim})")
        LOGGER.info(f"  Model height: {model_height}")
        
        if should_refine:
            LOGGER.info(
                f"  → Applying two-pass refinement "
                f"(brain < {TWO_PASS_BRAIN_RATIO_THRESHOLD*100:.0f}%, dim > {model_height})"
            )
            
            # Apply two-pass refinement (runs fresh segmentation on cropped image)
            refinement_applied = _apply_two_pass_refinement(
                input_image=input_image,
                output_dir=output_dir,
                file_ext=file_ext,
                atlas_name=atlas_name,
                atlas_metadata=atlas_metadata,
                ckpt_ax=ckpt_ax,
                ckpt_sag=ckpt_sag,
                ckpt_cor=ckpt_cor,
                device=device,
                viewagg_device=viewagg_device,
                threads=threads,
                batch_size=batch_size,
                plane_weight_coronal=plane_weight_coronal,
                plane_weight_axial=plane_weight_axial,
                plane_weight_sagittal=plane_weight_sagittal,
                fix_wm_islands=fix_wm_islands,
                output_data_format=output_data_format,
            )
            
            # If refinement succeeded, update result paths to reflect second-pass outputs
            # (which are already saved by the fresh run_segmentation call)
            if refinement_applied:
                LOGGER.info("  ✓ Second-pass outputs are now in main directory")
                # Update result dict to include cropped input
                result["input_cropped"] = output_dir / f"input_cropped{file_ext}"
        else:
            if brain_ratio >= TWO_PASS_BRAIN_RATIO_THRESHOLD:
                LOGGER.info(
                    f"  → Skipping refinement (brain occupancy >= {TWO_PASS_BRAIN_RATIO_THRESHOLD*100:.0f}%)"
                )
            else:
                LOGGER.info(
                    f"  → Skipping refinement (image dimension <= {model_height})"
                )

    return result

