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
FreeSurfer subject preparation for FastSurfer.

Post-processes skullstripping outputs for FreeSurfer surface reconstruction by:
- Conforming T1w, mask, and aseg to FreeSurfer format
- Resampling images to conformed space
- Creating FreeSurfer-compatible output files (aseg, masks, etc.)

Note: Segmentation (including V1 white matter fixing) should be done
before calling this function using run_segmentation().
"""

import shutil
from pathlib import Path
from typing import Literal

import nibabel as nib
import numpy as np

import fastsurfer_nn.postprocessing.reduce_to_aseg as rta
from fastsurfer_nn.data_loader import data_utils as data_ultils
from fastsurfer_nn.data_loader.conform import conform, is_conform, map_image
from fastsurfer_nn.seg_statistics.quick_qc import check_volume
from fastsurfer_nn.utils.arg_types import vox_size as _vox_size
from fastsurfer_nn.utils import logging
from fastsurfer_nn.utils.arg_types import OrientationType, VoxSizeOption
from fastsurfer_nn.utils.logging import setup_logging

LOGGER = logging.getLogger(__name__)


def create_aseg(
    seg_file: Path,
    output_dir: Path,
    lut_path: Path,
) -> None:
    """
    Create and save aseg file from segmentation prediction.
    
    Converts the detailed segmentation to FreeSurfer aseg format and applies brain mask.
    
    Parameters
    ----------
    seg_file : Path
        Path to segmentation file
    output_dir : Path
        Subject directory
    lut_path : Path
        Path to LUT file
    """
    LOGGER.info("Creating aseg (converting to FreeSurfer label conventions)...")
    
    # Load segmentation and mask
    pred_img = nib.load(seg_file)
    pred_data = np.asarray(pred_img.dataobj).astype(np.int16)
    
    mask_path = output_dir / "mri" / "mask.mgz"
    if not mask_path.exists():
        raise FileNotFoundError(f"Brain mask not found at {mask_path}")
    brain_mask = nib.load(mask_path).get_fdata().astype(np.uint8)
    
    # Convert to aseg format
    aseg = rta.reduce_to_aseg(pred_data, lut_path=lut_path, verbose=True)
    aseg[brain_mask == 0] = 0
    
    # Save aseg
    aseg_path = output_dir / "mri" / "aseg.auto_noCCseg.mgz"
    aseg_dtype = np.int16 if np.any(aseg < 0) else np.uint8
    
    # Use the same header/affine as the segmentation
    data_ultils.save_image(
        pred_img.header.copy(),
        pred_img.affine,
        aseg,
        aseg_path,
        dtype=aseg_dtype
    )
    LOGGER.info(f"Saving aseg: {aseg_path.name}")


def _extract_atlas_name_from_lut(lut_path: Path) -> str:
    """
    Extract atlas name from LUT file path.
    
    Parameters
    ----------
    lut_path : Path
        Path to ColorLUT file (e.g., ARM2_ColorLUT.tsv)
    
    Returns
    -------
    str
        Atlas name (e.g., "ARM2")
    """
    # Extract from filename: remove _ColorLUT and extension
    atlas_name = lut_path.stem.replace('_ColorLUT', '').replace('ColorLUT', '')
    return atlas_name


def postprocess_for_freesurfer(
    t1w_image: Path | str,
    segmentation: Path | str,
    mask: Path | str,
    lut_path: Path | str,
    subject_dir: Path | str,
    vox_size: VoxSizeOption = "min",
    orientation: OrientationType = "lia",
) -> Literal[0] | str:
    """
    Post-process segmentation outputs for FreeSurfer surface reconstruction.
    
    This function takes the outputs from run_segmentation and:
    1. Creates FreeSurfer directory structure
    2. Conforms T1w, mask, and aseg to FreeSurfer format
    3. Saves all files in the correct FreeSurfer locations
    
    Parameters
    ----------
    t1w_image : Path | str
        Path to T1w image (native space, from skullstripping input)
    segmentation : Path | str
        Path to segmentation file (native space, from skullstripping output)
    mask : Path | str
        Path to brain mask (native space, from skullstripping output)
    lut_path : Path | str
        Path to atlas ColorLUT file (for reduce_to_aseg)
    subject_dir : Path | str
        FreeSurfer subject directory
    hemimask : Path | str | None, optional
        Path to hemisphere mask (native space, from skullstripping output)
    vox_size : VoxSizeOption, default="min"
        Voxel size option for conforming
    orientation : OrientationType, default="lia"
        Target orientation for conforming
    
    Returns
    -------
    Literal[0] | str
        0 on success, error message on failure
    """
    # init logger
    setup_logging(log_file_path=None)
    LOGGER = logging.getLogger(__name__)
    
    # Convert to Path objects
    t1w_image = Path(t1w_image)
    segmentation = Path(segmentation)
    mask = Path(mask)
    lut_path = Path(lut_path)
    subject_dir = Path(subject_dir)
    
    # Validate inputs
    for path, name in [(t1w_image, "T1w image"), (segmentation, "segmentation"), 
                       (mask, "mask"), (lut_path, "LUT")]:
        if not path.exists():
            return f"Error: {name} not found at {path}"
    
    # Extract atlas name from LUT path
    atlas_name = _extract_atlas_name_from_lut(lut_path)
    LOGGER.info(f"Detected atlas: {atlas_name}")
    
    # Create FreeSurfer directory structure
    LOGGER.info("=" * 80)
    LOGGER.info("Step 1: Creating FreeSurfer directory structure")
    LOGGER.info("=" * 80)
    subject_dir = subject_dir.resolve()
    mri_dir = subject_dir / "mri"
    mri_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Subject directory: {subject_dir}")
    
    # Step 2: Conform T1w image (defines target space)
    LOGGER.info("=" * 80)
    LOGGER.info("Step 2: Conforming T1w image to FreeSurfer standard space")
    LOGGER.info("=" * 80)
    orig_mgz = mri_dir / "orig.mgz"
    
    t1w_img = nib.load(t1w_image)
    
    # Hardcode to 'cube' for FreeSurfer compatibility (cubic images required)
    conform_img_size: int | str = 'cube'
    
    conform_kwargs = {
        "vox_size": _vox_size(vox_size) if isinstance(vox_size, str) else vox_size,
        "orientation": orientation,
        "img_size": conform_img_size,
    }
    
    if not is_conform(t1w_img, **conform_kwargs, verbose=True):
        LOGGER.info("Conforming T1w image to FreeSurfer standard space...")
        conformed_t1w = conform(t1w_img, **conform_kwargs)
    else:
        LOGGER.info("T1w image is already conformed")
        conformed_t1w = t1w_img
    
    # DIAGNOSTIC: Check shapes before saving
    LOGGER.info(f"DIAGNOSTIC: conformed_t1w.shape = {conformed_t1w.shape}")
    conformed_t1w_data = np.asanyarray(conformed_t1w.dataobj)
    LOGGER.info(f"DIAGNOSTIC: conformed_t1w_data.shape = {conformed_t1w_data.shape}")
    LOGGER.info(f"DIAGNOSTIC: conformed_t1w.affine.shape = {conformed_t1w.affine.shape}")
    
    # Save conformed T1w
    data_ultils.save_image(
        conformed_t1w.header.copy(),
        conformed_t1w.affine,
        conformed_t1w_data,
        orig_mgz,
        dtype=np.uint8
    )
    LOGGER.info(f"Saved conformed T1w: {orig_mgz}")
    
    # DIAGNOSTIC: Reload saved image to check what was actually saved
    conformed_t1w_reloaded = nib.load(orig_mgz)
    LOGGER.info(f"DIAGNOSTIC: After reload - conformed_t1w_reloaded.shape = {conformed_t1w_reloaded.shape}")
    reloaded_data = np.asanyarray(conformed_t1w_reloaded.dataobj)
    LOGGER.info(f"DIAGNOSTIC: After reload - reloaded_data.shape = {reloaded_data.shape}")
    
    # Get target affine and shape from conformed T1w (for resampling other images)
    # Use the data shape, not the image object shape, to ensure we get the actual dimensions
    target_affine = conformed_t1w_reloaded.affine
    target_shape = reloaded_data.shape[:3]  # Use actual data shape, not image.shape
    LOGGER.info(f"DIAGNOSTIC: target_shape = {target_shape}")
    LOGGER.info(f"DIAGNOSTIC: target_affine.shape = {target_affine.shape}")
    
    # Validate target_shape is 3D
    if len(target_shape) != 3:
        error_msg = f"Invalid target_shape: {target_shape} (expected 3D, got {len(target_shape)}D)"
        LOGGER.error(error_msg)
        return error_msg
    if any(s <= 0 for s in target_shape):
        error_msg = f"Invalid target_shape dimensions: {target_shape} (all must be > 0)"
        LOGGER.error(error_msg)
        return error_msg
    
    # Step 3: Create aseg from segmentation (in native space first)
    LOGGER.info("=" * 80)
    LOGGER.info("Step 3: Creating aseg from segmentation")
    LOGGER.info("=" * 80)
    
    seg_img = nib.load(segmentation)
    seg_data = np.asarray(seg_img.dataobj).astype(np.int16)
    
    # Create aseg in native space
    aseg_data = rta.reduce_to_aseg(seg_data, lut_path=lut_path, verbose=True)
    
    # Apply mask to aseg (in native space)
    mask_img = nib.load(mask)
    mask_data = np.asarray(mask_img.dataobj).astype(np.uint8)
    aseg_data[mask_data == 0] = 0
    
    # Step 4: Resample segmentation, mask, and aseg to conformed space
    LOGGER.info("=" * 80)
    LOGGER.info("Step 4: Resampling images to conformed space")
    LOGGER.info("=" * 80)
    
    # Resample segmentation (use nearest neighbor for labels)
    LOGGER.info("Resampling segmentation to conformed space...")
    LOGGER.info(f"DIAGNOSTIC: seg_img.shape = {seg_img.shape}, target_shape = {target_shape}")
    seg_resampled = map_image(
        seg_img,
        out_affine=target_affine,
        out_shape=target_shape,
        order=0,  # Nearest neighbor for labels
        dtype=np.int16
    )
    LOGGER.info(f"DIAGNOSTIC: seg_resampled.shape = {seg_resampled.shape}")
    
    # Resample mask (use nearest neighbor)
    LOGGER.info("Resampling mask to conformed space...")
    LOGGER.info(f"DIAGNOSTIC: mask_img.shape = {mask_img.shape}, target_shape = {target_shape}")
    mask_resampled = map_image(
        mask_img,
        out_affine=target_affine,
        out_shape=target_shape,
        order=0,  # Nearest neighbor
        dtype=np.uint8
    )
    LOGGER.info(f"DIAGNOSTIC: mask_resampled.shape = {mask_resampled.shape}")
    
    # Resample aseg (use nearest neighbor)
    LOGGER.info("Resampling aseg to conformed space...")
    aseg_img_native = nib.nifti1.Nifti1Image(aseg_data, mask_img.affine, mask_img.header)
    LOGGER.info(f"DIAGNOSTIC: aseg_data.shape = {aseg_data.shape}, target_shape = {target_shape}")
    aseg_resampled = map_image(
        aseg_img_native,
        out_affine=target_affine,
        out_shape=target_shape,
        order=0,  # Nearest neighbor for labels
        dtype=np.int16
    )
    LOGGER.info(f"DIAGNOSTIC: aseg_resampled.shape = {aseg_resampled.shape}")
    
    # Apply mask to aseg in conformed space
    aseg_resampled[mask_resampled == 0] = 0
    
    # Step 5: Save all files in FreeSurfer structure
    LOGGER.info("=" * 80)
    LOGGER.info("Step 5: Saving files in FreeSurfer structure")
    LOGGER.info("=" * 80)
    
    # Save segmentation (both naming conventions)
    seg_file_generic = mri_dir / "aparc+aseg.orig.mgz"
    seg_file_atlas = mri_dir / f"aparc.{atlas_name}atlas+aseg.orig.mgz"
    
    # Use reloaded conformed image header for consistency
    aseg_dtype = np.int16 if np.any(seg_resampled < 0) else np.uint8
    LOGGER.info(f"DIAGNOSTIC: Saving segmentation with shape {seg_resampled.shape}, dtype {aseg_dtype}")
    data_ultils.save_image(
        conformed_t1w_reloaded.header.copy(),
        target_affine,
        seg_resampled.astype(aseg_dtype),
        seg_file_generic,
        dtype=aseg_dtype
    )
    LOGGER.info(f"Saved segmentation: {seg_file_generic.name}")
    
    # Copy to atlas-specific name
    shutil.copy2(seg_file_generic, seg_file_atlas)
    LOGGER.info(f"Saved segmentation: {seg_file_atlas.name}")
    
    # Save mask
    mask_path = mri_dir / "mask.mgz"
    LOGGER.info(f"DIAGNOSTIC: Saving mask with shape {mask_resampled.shape}")
    data_ultils.save_image(
        conformed_t1w_reloaded.header.copy(),
        target_affine,
        mask_resampled,
        mask_path,
        dtype=np.uint8
    )
    LOGGER.info(f"Saved mask: {mask_path.name}")
    
    # Save aseg
    aseg_path = mri_dir / "aseg.auto_noCCseg.mgz"
    aseg_dtype = np.int16 if np.any(aseg_resampled < 0) else np.uint8
    LOGGER.info(f"DIAGNOSTIC: Saving aseg with shape {aseg_resampled.shape}, dtype {aseg_dtype}")
    data_ultils.save_image(
        conformed_t1w_reloaded.header.copy(),
        target_affine,
        aseg_resampled.astype(aseg_dtype),
        aseg_path,
        dtype=aseg_dtype
    )
    LOGGER.info(f"Saved aseg: {aseg_path.name}")
    
    # Run QC statistics
    LOGGER.info("Computing segmentation volume statistics...")
    seg_voxvol = np.prod(conformed_t1w.header.get_zooms())
    check_volume(seg_resampled, seg_voxvol)
    
    LOGGER.info("=" * 80)
    LOGGER.info("Post-processing completed successfully!")
    LOGGER.info("=" * 80)
    
    return 0
