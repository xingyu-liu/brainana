#!/usr/bin/env python3
"""
Test script to save each step of the conforming process for visual diagnosis.

This script breaks down the conforming process into individual steps and saves
intermediate results so you can visually inspect what happens at each stage.
"""

import sys
import logging
import numpy as np
import nibabel as nib
from pathlib import Path
import json

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

from FastSurferCNN.data_loader.conform import (
    conformed_vox_img_size,
    prepare_mgh_header,
    map_image,
    conform,
)
from FastSurferCNN.data_loader import data_utils
from FastSurferCNN.inference.predictor_utils import load_multiplane_configs
from FastSurferCNN.utils.checkpoint import read_checkpoint_file

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration - modify these to match your test case
input_image = "/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_classic/working/sub-032309/ses-001/anat/sub-032309_ses-001_T1w/03_anat_bias_correction/anat_bias_corrected.nii.gz"
output_dir = Path(input_image).parent / "conforming_debug"
checkpoint_path = None  # Will auto-detect from modal

modal = "anat"  # or "func"

# If checkpoint_path is None, we'll try to find it
if checkpoint_path is None:
    from FastSurferCNN.utils.constants import PRETRAINED_MODEL_DIR
    if modal == "anat":
        checkpoint_path = PRETRAINED_MODEL_DIR / "T1w_seg-ARM2_planecoronal.pkl"
    else:
        checkpoint_path = PRETRAINED_MODEL_DIR / "EPI_seg-brainmask_planecoronal.pkl"

def convert_to_json_serializable(obj):
    """Convert numpy types and arrays to JSON-serializable types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_json_serializable(item) for item in obj]
    else:
        return obj

def save_image_with_info(img, path, info_dict=None):
    """Save image and optionally save info as JSON."""
    data_utils.save_image(
        img.header,
        img.affine,
        np.asanyarray(img.dataobj),
        path,
        dtype=np.float32,
    )
    logger.info(f"Saved: {path}")
    
    if info_dict:
        info_path = path.with_suffix('.json')
        # Convert numpy types to native Python types
        json_dict = convert_to_json_serializable(info_dict)
        with open(info_path, 'w') as f:
            json.dump(json_dict, f, indent=2)
        logger.info(f"Saved info: {info_path}")

def main():
    logger.info("=" * 80)
    logger.info("CONFORMING STEP-BY-STEP DEBUG TEST")
    logger.info("=" * 80)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    # Load input image
    logger.info(f"\n{'='*80}")
    logger.info("STEP 0: Loading input image")
    logger.info(f"{'='*80}")
    img = nib.load(input_image)
    
    orig_shape = img.shape[:3]
    orig_zooms = img.header.get_zooms()[:3]
    orig_affine = img.affine
    orig_orientation = "".join(nib.orientations.aff2axcodes(orig_affine))
    orig_center_vox = np.array(orig_shape, dtype=float) / 2.0
    orig_center_world = (orig_affine @ np.hstack((orig_center_vox, [1.0])))[:3]
    
    logger.info(f"Original shape: {orig_shape}")
    logger.info(f"Original voxel sizes (mm): {orig_zooms}")
    logger.info(f"Original orientation: {orig_orientation}")
    logger.info(f"Original center (voxel): {orig_center_vox}")
    logger.info(f"Original center (world): {orig_center_world}")
    
    # Save original image
    save_image_with_info(
        img,
        output_dir / "00_original_image.nii.gz",
        {
            "shape": list(orig_shape),
            "voxel_sizes_mm": list(orig_zooms),
            "orientation": orig_orientation,
            "center_voxel": list(orig_center_vox),
            "center_world": list(orig_center_world),
            "affine": orig_affine.tolist(),
        }
    )
    
    # Load preprocessing parameters from checkpoint
    logger.info(f"\n{'='*80}")
    logger.info("STEP 0.5: Loading preprocessing parameters from checkpoint")
    logger.info(f"{'='*80}")
    
    if not Path(checkpoint_path).exists():
        logger.error(f"Checkpoint not found: {checkpoint_path}")
        logger.info("Using default parameters: vox_size='min', orientation='lia', img_size='cube' (for testing)")
        vox_size = "min"
        orientation = "lia"
        img_size = "cube"  # Set to 'cube' for testing padding logic (default would be 'fov')
    else:
        logger.info(f"Loading checkpoint: {checkpoint_path}")
        ckpt = read_checkpoint_file(checkpoint_path)
        preprocess = ckpt.get("DATA", {}).get("PREPROCESSING", {})
        vox_size = preprocess.get("VOX_SIZE", "min")
        orientation = preprocess.get("ORIENTATION", "lia")
        img_size = preprocess.get("IMG_SIZE", "fov")
        logger.info(f"From checkpoint: vox_size={vox_size}, orientation={orientation}, img_size={img_size}")
    
    # Step 1: Determine target voxel size and image size
    logger.info(f"\n{'='*80}")
    logger.info("STEP 1: Determining target voxel size and image size")
    logger.info(f"{'='*80}")
    
    target_vox_size, target_img_size = conformed_vox_img_size(
        img, vox_size, img_size, vox_eps=1e-4
    )
    
    logger.info(f"Target voxel size: {target_vox_size}")
    logger.info(f"Target image size: {target_img_size}")
    
    # Calculate FOV
    orig_fov = np.array(orig_zooms) * np.array(orig_shape)
    if target_vox_size is not None:
        expected_fov = np.array(target_vox_size) * np.array(target_img_size)
        logger.info(f"Original FOV (mm): {orig_fov}")
        logger.info(f"Target FOV (mm): {expected_fov}")
        logger.info(f"FOV change: {expected_fov - orig_fov}")
    
    # Save step 1 info
    step1_info = {
        "target_vox_size": target_vox_size.tolist() if target_vox_size is not None else None,
        "target_img_size": target_img_size.tolist() if target_img_size is not None else None,
        "original_fov_mm": orig_fov.tolist(),
        "target_fov_mm": expected_fov.tolist() if target_vox_size is not None else None,
        "fov_change_mm": (expected_fov - orig_fov).tolist() if target_vox_size is not None else None,
    }
    with open(output_dir / "01_target_vox_img_size.json", 'w') as f:
        json.dump(convert_to_json_serializable(step1_info), f, indent=2)
    logger.info(f"Saved: {output_dir / '01_target_vox_img_size.json'}")
    
    # Step 2: Prepare target header (this calculates the target affine and center)
    logger.info(f"\n{'='*80}")
    logger.info("STEP 2: Preparing target header (calculating affine and center)")
    logger.info(f"{'='*80}")
    
    h1 = prepare_mgh_header(
        img,
        target_vox_size,
        target_img_size,
        orientation,
        vox_eps=1e-4,
        rot_eps=1e-6,
    )
    
    target_affine = h1.get_affine()
    target_shape = h1.get_data_shape()[:3]
    target_zooms = h1.get_zooms()[:3]
    target_orientation = "".join(nib.orientations.aff2axcodes(target_affine))
    
    # Get center from header
    if "Pxyz_c" in h1:
        target_center_world = np.array(h1["Pxyz_c"])
    else:
        target_center_vox = np.array(target_shape, dtype=float) / 2.0
        target_center_world = (target_affine @ np.hstack((target_center_vox, [1.0])))[:3]
    
    target_center_vox = np.array(target_shape, dtype=float) / 2.0
    
    logger.info(f"Target shape: {target_shape}")
    logger.info(f"Target voxel sizes: {target_zooms}")
    logger.info(f"Target orientation: {target_orientation}")
    logger.info(f"Target center (voxel): {target_center_vox}")
    logger.info(f"Target center (world): {target_center_world}")
    logger.info(f"Center shift (world): {target_center_world - orig_center_world}")
    
    # Calculate vox2vox transformation
    vox2vox = np.linalg.inv(target_affine) @ img.affine
    logger.info(f"\nVox2vox transformation matrix:")
    logger.info(f"{vox2vox}")
    
    # Save step 2 info
    step2_info = {
        "target_shape": list(target_shape),
        "target_voxel_sizes": list(target_zooms),
        "target_orientation": target_orientation,
        "target_center_voxel": list(target_center_vox),
        "target_center_world": list(target_center_world),
        "original_center_world": list(orig_center_world),
        "center_shift_world": list(target_center_world - orig_center_world),
        "target_affine": target_affine.tolist(),
        "vox2vox_matrix": vox2vox.tolist(),
        "mdc_matrix": h1["Mdc"].tolist() if "Mdc" in h1 else None,
    }
    with open(output_dir / "02_target_header.json", 'w') as f:
        json.dump(convert_to_json_serializable(step2_info), f, indent=2)
    logger.info(f"Saved: {output_dir / '02_target_header.json'}")
    
    # Create a "target space" image (empty, just to visualize the target space)
    target_space_data = np.zeros(target_shape, dtype=np.float32)
    target_space_img = nib.Nifti1Image(target_space_data, target_affine)
    save_image_with_info(
        target_space_img,
        output_dir / "02_target_space_empty.nii.gz",
        step2_info
    )
    
    # Step 3: Before resampling - show what the transformation will do
    logger.info(f"\n{'='*80}")
    logger.info("STEP 3: Analyzing transformation (before resampling)")
    logger.info(f"{'='*80}")
    
    # Calculate bounding box of original image in target space
    orig_corners_vox = np.array([
        [0, 0, 0, 1],
        [orig_shape[0], 0, 0, 1],
        [0, orig_shape[1], 0, 1],
        [0, 0, orig_shape[2], 1],
        [orig_shape[0], orig_shape[1], 0, 1],
        [orig_shape[0], 0, orig_shape[2], 1],
        [0, orig_shape[1], orig_shape[2], 1],
        [orig_shape[0], orig_shape[1], orig_shape[2], 1],
    ]).T
    
    orig_corners_world = img.affine @ orig_corners_vox
    target_corners_vox = np.linalg.inv(target_affine) @ orig_corners_world
    
    min_corner = np.min(target_corners_vox[:3], axis=1)
    max_corner = np.max(target_corners_vox[:3], axis=1)
    
    logger.info(f"Original image corners in target voxel space:")
    logger.info(f"  Min: {min_corner}")
    logger.info(f"  Max: {max_corner}")
    logger.info(f"  Target shape: {target_shape}")
    logger.info(f"  Will original image fit? Min >= 0: {np.all(min_corner >= -0.5)}, Max < shape: {np.all(max_corner < np.array(target_shape) + 0.5)}")
    
    # Save step 3 info
    step3_info = {
        "original_corners_in_target_voxel_space": {
            "min": min_corner.tolist(),
            "max": max_corner.tolist(),
        },
        "target_shape": list(target_shape),
        "fits_in_target": {
            "min_ok": bool(np.all(min_corner >= -0.5)),
            "max_ok": bool(np.all(max_corner < np.array(target_shape) + 0.5)),
        },
    }
    with open(output_dir / "03_transformation_analysis.json", 'w') as f:
        json.dump(convert_to_json_serializable(step3_info), f, indent=2)
    logger.info(f"Saved: {output_dir / '03_transformation_analysis.json'}")
    
    # Step 4: Perform resampling
    logger.info(f"\n{'='*80}")
    logger.info("STEP 4: Performing resampling (map_image)")
    logger.info(f"{'='*80}")
    
    mapped_data = map_image(
        img,
        target_affine,
        target_shape,
        order=1,  # linear interpolation
        dtype=float,
        vox_eps=1e-4,
        rot_eps=1e-6,
    )
    
    logger.info(f"Resampled data shape: {mapped_data.shape}")
    logger.info(f"Resampled data range: [{mapped_data.min():.2f}, {mapped_data.max():.2f}]")
    logger.info(f"Resampled data non-zero voxels: {np.count_nonzero(mapped_data)} / {mapped_data.size}")
    
    # Save resampled data (before rescaling)
    resampled_img = nib.Nifti1Image(mapped_data, target_affine)
    save_image_with_info(
        resampled_img,
        output_dir / "04_resampled_before_rescale.nii.gz",
        {
            "shape": list(mapped_data.shape),
            "data_range": [float(mapped_data.min()), float(mapped_data.max())],
            "non_zero_voxels": int(np.count_nonzero(mapped_data)),
            "total_voxels": int(mapped_data.size),
        }
    )
    
    # Step 5: Final conformed image (with rescaling, dtype conversion, and padding if cube)
    logger.info(f"\n{'='*80}")
    logger.info("STEP 5: Creating final conformed image")
    logger.info(f"{'='*80}")
    if img_size == "cube":
        logger.info("Note: img_size='cube' will pad FOV-based image to cube after resampling")
        logger.info("This preserves brain position by using FOV-based affine, then padding symmetrically")
    
    final_img = conform(
        img,
        order=1,
        vox_size=vox_size,
        img_size=img_size,
        dtype=np.uint8,
        orientation=orientation,
        rescale=255,
        verbose=True,
    )
    
    final_shape = final_img.shape[:3]
    final_zooms = final_img.header.get_zooms()[:3]
    final_affine = final_img.affine
    final_orientation = "".join(nib.orientations.aff2axcodes(final_affine))
    final_data = np.asanyarray(final_img.dataobj)
    
    logger.info(f"Final shape: {final_shape}")
    logger.info(f"Final voxel sizes: {final_zooms}")
    logger.info(f"Final orientation: {final_orientation}")
    logger.info(f"Final data range: [{final_data.min()}, {final_data.max()}]")
    logger.info(f"Final non-zero voxels: {np.count_nonzero(final_data)} / {final_data.size}")
    
    # Check if padding was applied (for img_size="cube")
    if img_size == "cube":
        is_cubic = len(set(final_shape)) == 1
        logger.info(f"Is cubic: {is_cubic}")
        if is_cubic:
            logger.info("✓ Successfully padded to cubic shape while preserving brain position")
    
    # Save final conformed image
    save_image_with_info(
        final_img,
        output_dir / "05_final_conformed.nii.gz",
        {
            "shape": list(final_shape),
            "voxel_sizes": list(final_zooms),
            "orientation": final_orientation,
            "data_range": [int(final_data.min()), int(final_data.max())],
            "non_zero_voxels": int(np.count_nonzero(final_data)),
            "total_voxels": int(final_data.size),
        }
    )
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Original: {orig_shape} @ {orig_zooms} mm, orientation: {orig_orientation}")
    logger.info(f"Final:    {final_shape} @ {final_zooms} mm, orientation: {final_orientation}")
    logger.info(f"Center shift (world space): {target_center_world - orig_center_world}")
    logger.info(f"\nAll intermediate files saved to: {output_dir}")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()

