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
Utilities for predictor configuration, atlas setup, and image preprocessing.

This module provides helper functions for:
- Validating checkpoint files
- Loading configurations from multiple plane checkpoints
- Extracting and validating atlas metadata
- Image cropping and two-pass refinement logic
"""

from pathlib import Path

import nibabel as nib
import numpy as np
import yacs.config

from FastSurferCNN.utils import logging
from FastSurferCNN.utils.checkpoint import (
    extract_atlas_metadata,
    extract_training_config,
)

LOGGER = logging.getLogger(__name__)


def validate_checkpoints(
    ckpt_ax: Path | None,
    ckpt_cor: Path | None,
    ckpt_sag: Path | None,
) -> None:
    """
    Validate that at least one checkpoint is provided.

    Parameters
    ----------
    ckpt_ax : Path, optional
        Checkpoint path for axial plane.
    ckpt_cor : Path, optional
        Checkpoint path for coronal plane.
    ckpt_sag : Path, optional
        Checkpoint path for sagittal plane.

    Raises
    ------
    ValueError
        If no checkpoints are provided.
    """
    if all(ckpt is None for ckpt in [ckpt_ax, ckpt_cor, ckpt_sag]):
        raise ValueError(
            "At least one checkpoint must be provided. "
            "Please specify --ckpt_ax, --ckpt_cor, and/or --ckpt_sag."
        )


def setup_atlas_from_checkpoints(
    ckpt_ax: Path | None,
    ckpt_cor: Path | None,
    ckpt_sag: Path | None,
) -> tuple[str | None, dict]:
    """
    Extract and validate atlas metadata from checkpoint files.

    Parameters
    ----------
    ckpt_ax : Path, optional
        Path to checkpoint file for axial plane.
    ckpt_cor : Path, optional
        Path to checkpoint file for coronal plane.
    ckpt_sag : Path, optional
        Path to checkpoint file for sagittal plane.

    Returns
    -------
    tuple[str | None, dict]
        Atlas name (None for binary tasks) and full atlas metadata dictionary.

    Raises
    ------
    RuntimeError
        If no atlas metadata found, checkpoints use different atlases, or mode mismatch.
    """
    LOGGER.info("Extracting atlas information from checkpoints...")

    # Try to extract atlas from each checkpoint (they should all be the same)
    atlas_metadatas = {}
    plane_checkpoints = [
        ("axial", ckpt_ax),
        ("coronal", ckpt_cor),
        ("sagittal", ckpt_sag),
    ]

    for plane, ckpt_path in plane_checkpoints:
        if ckpt_path is not None:
            metadata = extract_atlas_metadata(ckpt_path)
            if metadata:
                atlas_metadatas[plane] = metadata
                is_binary = metadata.get("is_binary_task", False)
                if is_binary:
                    LOGGER.info(
                        f"  {plane.capitalize():9s}: Binary task "
                        f"({metadata['num_classes']} classes)"
                    )
                else:
                    atlas_name = metadata.get("atlas_name", "Unknown")
                    LOGGER.info(
                        f"  {plane.capitalize():9s}: {atlas_name} "
                        f"({metadata['num_classes']} classes)"
                    )

    if not atlas_metadatas:
        raise RuntimeError(
            "Could not extract atlas metadata from any checkpoint. "
            "Please verify your checkpoint files are valid and contain atlas information."
        )

    # Validate that all checkpoints use the same mode (binary vs multi-class)
    is_binary_flags = {meta.get("is_binary_task", False) for meta in atlas_metadatas.values()}
    if len(is_binary_flags) > 1:
        raise RuntimeError(
            "Checkpoint mode mismatch: Some checkpoints are binary, others are multi-class. "
            "All checkpoints must use the same task type."
        )
    
    is_binary = list(is_binary_flags)[0]
    
    if is_binary:
        # Binary task - atlas_name is optional but can be provided (e.g., "brainmask")
        # Check if any checkpoint has atlas_name saved (from CLASS_OPTIONS[0] during training)
        atlas_names = {meta.get("atlas_name") for meta in atlas_metadatas.values() if meta.get("atlas_name") is not None}
        if atlas_names:
            # Use the atlas_name if provided (all should be the same)
            if len(atlas_names) > 1:
                LOGGER.warning(
                    f"Binary checkpoints have different atlas names: {atlas_names}. "
                    f"Using first: {sorted(atlas_names)[0]}"
                )
            atlas_name = sorted(atlas_names)[0]
            LOGGER.info(f"✓ Validated: Binary brain mask task (atlas: {atlas_name})")
        else:
            # No atlas_name provided - this is OK for binary models
            atlas_name = None
            LOGGER.info("✓ Validated: Binary brain mask task (no atlas)")
        atlas_metadata = list(atlas_metadatas.values())[0]
    else:
        # Multi-class task - validate that all checkpoints use the same atlas
        atlas_names = {meta.get("atlas_name") for meta in atlas_metadatas.values()}
        if None in atlas_names:
            raise RuntimeError(
                "Multi-class checkpoints missing atlas_name in metadata. "
                "Please ensure all checkpoints were saved with complete atlas metadata."
            )
        if len(atlas_names) > 1:
            raise RuntimeError(
                f"Checkpoint atlas mismatch: {atlas_names}. "
                "All checkpoints must be trained on the same atlas."
            )

        # Use the atlas from any checkpoint (they're all the same)
        atlas_name = list(atlas_names)[0]
        atlas_metadata = list(atlas_metadatas.values())[0]
        LOGGER.info(f"✓ Validated atlas: {atlas_name}")

    return atlas_name, atlas_metadata


def load_multiplane_configs(
    ckpt_ax: Path | None = None,
    ckpt_cor: Path | None = None,
    ckpt_sag: Path | None = None,
    batch_size: int = 1,
) -> tuple[
    yacs.config.CfgNode,
    yacs.config.CfgNode,
    yacs.config.CfgNode,
    yacs.config.CfgNode,
]:
    """
    Load training configurations from multiple plane checkpoints.

    This function loads the training configuration from up to 3 checkpoint
    files (one for each plane: axial, coronal, sagittal) for multi-view inference.

    Checkpoints contain the full training config, eliminating the need for
    separate config files during inference.

    Parameters
    ----------
    ckpt_ax : Path, optional
        The path to the axial checkpoint.
    ckpt_cor : Path, optional
        The path to the coronal checkpoint.
    ckpt_sag : Path, optional
        The path to the sagittal checkpoint.
    batch_size : int, default=1
        The batch size for the network.

    Returns
    -------
    tuple[yacs.config.CfgNode, ...]
        Configurations: (cfg_fin, cfg_cor, cfg_sag, cfg_ax)

    Raises
    ------
    RuntimeError
        If no valid configuration is found.
    """
    # Load all configs from checkpoints
    plane_configs = [
        ("coronal", ckpt_cor),
        ("sagittal", ckpt_sag),
        ("axial", ckpt_ax),
    ]

    cfgs = {}
    for plane_name, ckpt in plane_configs:
        if ckpt is not None:
            LOGGER.info(f"Loading {plane_name} config from checkpoint")
            cfgs[plane_name] = extract_training_config(ckpt, batch_size)
        else:
            cfgs[plane_name] = None

    cfg_cor = cfgs["coronal"]
    cfg_sag = cfgs["sagittal"]
    cfg_ax = cfgs["axial"]

    # Return the first non-None cfg as cfg_fin
    cfg_fin = next(
        (cfg for cfg in (cfg_cor, cfg_sag, cfg_ax) if cfg is not None),
        None,
    )
    if cfg_fin is None:
        raise RuntimeError(
            "No valid configuration passed! At least one checkpoint must be provided."
        )

    return (cfg_fin, cfg_cor, cfg_sag, cfg_ax)


# ============================================================================
# Image preprocessing utilities
# ============================================================================

# Two-pass refinement parameters
TWO_PASS_BRAIN_RATIO_THRESHOLD = 0.20  # Trigger refinement if brain occupies < 20% of FOV
TWO_PASS_CROP_MARGIN = 0.08  # 8% margin around brain bounding box


def crop_image_to_brain_mask(
    image_path: Path | str,
    brain_mask_path: Path | str,
    margin: float = 0.1,
    save_path: Path | str | None = None,
) -> nib.analyze.SpatialImage:
    """
    Crop image to brain mask region with margin.
    
    Parameters
    ----------
    image_path : Path, str
        Path to input image to crop
    brain_mask_path : Path, str
        Path to brain mask image (binary mask, same shape as input image)
    margin : float, default=0.1
        Margin to add as percentage of brain bounding box size
    save_path : Path, str, optional
        If provided, save the cropped image as NIfTI to this path
        
    Returns
    -------
    nib.analyze.SpatialImage
        Cropped image with updated affine matrix
    """
    # Load image and mask from paths
    img = nib.load(image_path)
    img_data = np.asanyarray(img.dataobj)
    brain_mask_img = nib.load(brain_mask_path)
    brain_mask = np.asanyarray(brain_mask_img.dataobj)
    
    # Validate dimensions match
    if img_data.shape != brain_mask.shape:
        raise ValueError(
            f"Image shape {img_data.shape} does not match brain mask shape {brain_mask.shape}"
        )
    
    # Check if brain mask has any non-zero values
    if np.all(brain_mask == 0):
        raise ValueError("Brain mask is empty (all zeros). Cannot determine crop region.")
    
    # Find bounding box of brain area
    brain_area = np.where(brain_mask != 0)
    if len(brain_area) == 0 or len(brain_area[0]) == 0:
        raise ValueError("Brain mask has no non-zero voxels. Cannot determine crop region.")
    
    # Get number of dimensions from np.where result (should match mask dimensions)
    n_dims = len(brain_area)
    mask_ndims = len(brain_mask.shape)
    
    if n_dims != mask_ndims:
        raise ValueError(
            f"Mismatch: np.where returned {n_dims} dimensions but mask has {mask_ndims} dimensions. "
            f"Mask shape: {brain_mask.shape}, brain_area length: {len(brain_area)}"
        )
    
    if n_dims < 2 or n_dims > 3:
        raise ValueError(f"Expected 2D or 3D brain mask, got {n_dims}D mask with shape {brain_mask.shape}")
    
    # Calculate bounding box for each dimension [min, max]
    # dim_range shape: (n_dims, 2) where dim_range[i, 0] = min, dim_range[i, 1] = max for dimension i
    dim_range = np.array([[np.min(brain_area[i]), np.max(brain_area[i])] for i in range(n_dims)])
    dim_length = dim_range[:, 1] - dim_range[:, 0] + 1  # +1 because range is inclusive
    
    # Add margin to the brain area
    margin_pixels = (margin * dim_length).astype(int)
    dim_range[:, 0] = dim_range[:, 0] - margin_pixels
    dim_range[:, 1] = dim_range[:, 1] + margin_pixels
    
    # Clamp to image boundaries
    for i in range(n_dims):
        if dim_range[i, 0] < 0:
            dim_range[i, 0] = 0
        if dim_range[i, 1] >= img_data.shape[i]:
            dim_range[i, 1] = img_data.shape[i] - 1
    
    # Create slices based on number of dimensions
    if n_dims == 3:
        xmin, xmax = int(dim_range[0, 0]), int(dim_range[0, 1]) + 1
        ymin, ymax = int(dim_range[1, 0]), int(dim_range[1, 1]) + 1
        zmin, zmax = int(dim_range[2, 0]), int(dim_range[2, 1]) + 1
        crop_slices = (slice(xmin, xmax), slice(ymin, ymax), slice(zmin, zmax))
    elif n_dims == 2:
        xmin, xmax = int(dim_range[0, 0]), int(dim_range[0, 1]) + 1
        ymin, ymax = int(dim_range[1, 0]), int(dim_range[1, 1]) + 1
        crop_slices = (slice(xmin, xmax), slice(ymin, ymax))
    else:
        raise ValueError(f"Unsupported number of dimensions: {n_dims}")
    
    # Crop the image data
    cropped_data = img_data[crop_slices]
    
    # Update affine to account for cropping (translate origin)
    cropped_affine = img.affine.copy()
    # Calculate translation in world coordinates
    if n_dims == 3:
        origin_voxel = np.array([xmin, ymin, zmin, 1.0])
    else:
        origin_voxel = np.array([xmin, ymin, 0, 1.0])
    origin_world = img.affine @ origin_voxel
    cropped_affine[:3, 3] = origin_world[:3]
    
    # Create new image with cropped data and updated affine
    cropped_img = nib.MGHImage(cropped_data, cropped_affine, img.header.copy())
    
    # Save as NIfTI if save_path is provided
    if save_path is not None:
        save_path = Path(save_path)
        # Ensure output directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use the dtype from the input image
        save_dtype = img_data.dtype
        cropped_data_save = cropped_data.astype(save_dtype)
        
        # Create NIfTI image with cropped affine and header
        cropped_nii = nib.Nifti1Image(cropped_data_save, cropped_affine, img.header.copy())
        # Update header data type
        cropped_nii.header.set_data_dtype(save_dtype)
        
        # Save the NIfTI file
        nib.save(cropped_nii, save_path)
    
    return cropped_img


def should_apply_refinement(
    brain_mask: np.ndarray,
    orig_img: nib.analyze.SpatialImage,
    model_height: int,
) -> tuple[bool, float, int]:
    """
    Determine if two-pass refinement should be applied.
    
    Parameters
    ----------
    brain_mask : np.ndarray
        Binary brain mask
    orig_img : nib.analyze.SpatialImage
        Original image
    model_height : int
        Model height from checkpoint config
        
    Returns
    -------
    tuple[bool, float, int]
        (should_refine, brain_ratio, max_orig_dim)
        should_refine: True if refinement should be applied
        brain_ratio: Ratio of brain volume to total volume
        max_orig_dim: Maximum dimension of original image
    """
    brain_volume = np.sum(brain_mask > 0)
    total_volume = np.prod(brain_mask.shape)
    brain_ratio = brain_volume / total_volume
    
    orig_shape = orig_img.shape
    max_orig_dim = max(orig_shape)
    
    should_refine = (
        brain_ratio < TWO_PASS_BRAIN_RATIO_THRESHOLD
        and max_orig_dim > model_height
    )
    
    return should_refine, brain_ratio, max_orig_dim

