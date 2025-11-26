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

Prepares subjects for FreeSurfer surface reconstruction by:
- Conforming input images to FreeSurfer space
- Running CNN-based brain segmentation
- Creating FreeSurfer-compatible output files (aseg, masks, etc.)
- Optionally applying V1 white matter correction
"""

import argparse
import copy
import shutil
import sys
from pathlib import Path
from typing import Any, Literal

# Add parent directory to path for module imports
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent))

import tempfile

import nibabel as nib
import numpy as np

import FastSurferCNN.postprocessing.fix_v1_wm as fix_v1_wm
import FastSurferCNN.postprocessing.reduce_to_aseg as rta
from FastSurferCNN.data_loader import data_utils as data_ultils
from FastSurferCNN.data_loader.conform import conform, is_conform, map_image
from FastSurferCNN.inference.api import run_segmentation
from FastSurferCNN.inference.predictor_utils import (
    setup_atlas_from_checkpoints,
    validate_checkpoints,
)
from FastSurferCNN.inference.skullstripping import skullstrip_fastsurfercnn
from FastSurferCNN.seg_statistics.quick_qc import check_volume
from FastSurferCNN.utils.arg_types import vox_size as _vox_size
from FastSurferCNN.utils import PLANES, Plane, logging, parser_defaults
from FastSurferCNN.utils.arg_types import OrientationType, VoxSizeOption
from FastSurferCNN.utils.checkpoint import get_checkpoints, get_paths_from_yaml
from FastSurferCNN.utils.common import find_device, handle_cuda_memory_exception
from FastSurferCNN.utils.constants import FASTSURFER_ROOT
from FastSurferCNN.utils.logging import setup_logging

LOGGER = logging.getLogger(__name__)
CHECKPOINT_PATHS_FILE = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"


def _conform_and_save_orig_mgz(
    input_image: Path | str,
    output_dir: Path,
    vox_size: VoxSizeOption = "min",
    orientation: OrientationType = "lia",
    image_size: bool = True,
) -> Path:
    """
    Conform input image to FreeSurfer standard space and save as orig.mgz.
    
    Parameters
    ----------
    input_image : Path | str
        Path to input image
    output_dir : Path
        Output directory (FreeSurfer subject directory)
    vox_size : VoxSizeOption
        Voxel size option
    orientation : OrientationType
        Target orientation
    image_size : bool
        Whether to enforce standard image size
    
    Returns
    -------
    Path
        Path to saved orig.mgz file
    """
    input_image = Path(input_image)
    mri_dir = output_dir / "mri"
    mri_dir.mkdir(parents=True, exist_ok=True)
    orig_mgz = mri_dir / "orig.mgz"
    
    LOGGER.info(f"Loading and conforming input image: {input_image}")
    orig_img = nib.load(input_image)
    
    # Check if conforming is needed
    conform_kwargs = {
        "vox_size": _vox_size(vox_size) if isinstance(vox_size, str) else vox_size,
        "orientation": orientation,
        "img_size": image_size,
    }
    
    if not is_conform(orig_img, **conform_kwargs, verbose=True):
        LOGGER.info("Conforming image to FreeSurfer standard space...")
        conformed_img = conform(orig_img, **conform_kwargs)
    else:
        LOGGER.info("Image is already conformed")
        conformed_img = orig_img
    
    # Save conformed image as orig.mgz (in conformed space, not resampled to native)
    conformed_data = np.asanyarray(conformed_img.dataobj)
    data_ultils.save_image(
        conformed_img.header.copy(),
        conformed_img.affine,
        conformed_data,
        orig_mgz,
        dtype=np.uint8
    )
    LOGGER.info(f"Saved conformed image: {orig_mgz}")
    
    return orig_mgz


def apply_v1_wm_fixing(
    seg_file: Path,
    output_dir: Path,
    lut_path: Path,
    tpl_t1w: str,
    tpl_wm: str,
) -> None:
    """
    Apply V1 white matter fixing using template registration.
    
    Parameters
    ----------
    seg_file : Path
        Path to segmentation file
    output_dir : Path
        Subject directory
    lut_path : Path
        Path to LUT file
    tpl_t1w : str
        Path to template T1w image
    tpl_wm : str
        Path to template WM probability map
    """
    LOGGER.info("Applying V1 white matter correction...")
    
    try:
        # File paths
        t1w_file = output_dir / "mri" / "orig.mgz"
        mask_file = output_dir / "mri" / "mask.mgz"
        hemi_mask_file = output_dir / "mri" / "mask_hemi.mgz"
        
        # Ensure required files exist
        if not all(f.exists() for f in [seg_file, t1w_file, mask_file, hemi_mask_file]):
            raise FileNotFoundError(
                f"Required files missing for V1 fixing. "
                f"Need: {seg_file}, {t1w_file}, {mask_file}, {hemi_mask_file}"
            )
        
        # Run V1 WM fixing
        fix_v1_wm(
            seg_f=str(seg_file),
            t1w_f=str(t1w_file),
            mask_f=str(mask_file),
            hemi_mask_f=str(hemi_mask_file),
            lut_path=str(lut_path),
            tpl_t1w_f=tpl_t1w,
            tpl_wm_f=tpl_wm,
            roi_name='V1',
            wm_thr=0.5,
            backup_original=True,
            verbose=True
        )
        
        LOGGER.info("  ✓ V1 WM correction completed")
        
    except Exception as e:
        LOGGER.error(f"  ✗ V1 WM correction failed: {e}")
        raise


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


def _validate_v1_templates(tpl_t1w: str, tpl_wm: str) -> None:
    """Validate that V1 template files exist."""
    missing_files = []
    if not Path(tpl_t1w).exists():
        missing_files.append(f"Template T1w: {tpl_t1w}")
    if not Path(tpl_wm).exists():
        missing_files.append(f"Template WM: {tpl_wm}")
    
    if missing_files:
        raise FileNotFoundError(
            "--fixv1 requires the following template files:\n  " + "\n  ".join(missing_files)
        )


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
    hemimask: Path | str | None = None,
    vox_size: VoxSizeOption = "min",
    orientation: OrientationType = "lia",
    image_size: bool = True,
    fixv1: bool = False,
    tpl_t1w: str | None = None,
    tpl_wm: str | None = None,
) -> Literal[0] | str:
    """
    Post-process skullstripping outputs for FreeSurfer surface reconstruction.
    
    This function takes the outputs from skullstrip_fastsurfercnn and:
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
    image_size : bool, default=True
        Whether to enforce standard image size
    fixv1 : bool, default=False
        Apply V1 white matter correction
    tpl_t1w : str | None, optional
        Path to template T1w image for V1 fixing (required if fixv1=True)
    tpl_wm : str | None, optional
        Path to template WM probability map for V1 fixing (required if fixv1=True)
    
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
    
    if fixv1:
        _validate_v1_templates(tpl_t1w, tpl_wm)
    
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
    
    # Convert boolean image_size to proper img_size parameter for conform function
    # image_size=True means use None (no size constraint, minimum size needed)
    # image_size=False means don't enforce size (None)
    if isinstance(image_size, bool):
        conform_img_size: int | str | None = 'auto' if image_size else None
    
    conform_kwargs = {
        "vox_size": _vox_size(vox_size) if isinstance(vox_size, str) else vox_size,
        "orientation": orientation,
        "img_size": conform_img_size,
    }
    
    LOGGER.info(f"DIAGNOSTIC: image_size parameter: {image_size} -> conform_img_size: {conform_img_size}")
    
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
    
    # Resample hemimask if provided
    hemi_resampled = None
    if hemimask is not None:
        hemimask_path = Path(hemimask)
        if hemimask_path.exists():
            LOGGER.info("Resampling hemisphere mask to conformed space...")
            hemi_img = nib.load(hemimask_path)
            hemi_resampled = map_image(
                hemi_img,
                out_affine=target_affine,
                out_shape=target_shape,
                order=0,  # Nearest neighbor
                dtype=np.uint8
            )
        else:
            LOGGER.warning(f"Hemisphere mask not found at {hemimask_path}, skipping")
    
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
    
    # Save hemimask if available
    if hemi_resampled is not None:
        hemi_mask_path = mri_dir / "mask_hemi.mgz"
        LOGGER.info(f"DIAGNOSTIC: Saving hemimask with shape {hemi_resampled.shape}")
        data_ultils.save_image(
            conformed_t1w_reloaded.header.copy(),
            target_affine,
            hemi_resampled,
            hemi_mask_path,
            dtype=np.uint8
        )
        LOGGER.info(f"Saved hemisphere mask: {hemi_mask_path.name}")
    
    # Step 6: Optionally apply V1 WM fixing
    if fixv1:
        LOGGER.info("=" * 80)
        LOGGER.info("Step 6: Applying V1 white matter correction")
        LOGGER.info("=" * 80)
        apply_v1_wm_fixing(
            seg_file=seg_file_atlas,  # Use atlas-specific name
            output_dir=subject_dir,
            lut_path=lut_path,
            tpl_t1w=tpl_t1w,
            tpl_wm=tpl_wm,
        )
        # Also update the generic name file
        shutil.copy2(seg_file_atlas, seg_file_generic)
    
    # Run QC statistics
    LOGGER.info("Computing segmentation volume statistics...")
    seg_voxvol = np.prod(conformed_t1w.header.get_zooms())
    check_volume(seg_resampled, seg_voxvol)
    
    LOGGER.info("=" * 80)
    LOGGER.info("Post-processing completed successfully!")
    LOGGER.info("=" * 80)
    
    return 0

def prepare_freesurfer_subject(
        *,
        orig_name: Path | str,
        output_dir: Path,
        pred_name: str = "mri/aparc+aseg.orig.mgz",
        ckpt_ax: Path | None,
        ckpt_sag: Path | None,
        ckpt_cor: Path | None,
        qc_log: str = "",
        vox_size: VoxSizeOption = "min",
        device: str = "auto",
        viewagg_device: str = "auto",
        batch_size: int = 1,
        orientation: OrientationType = "lia",
        image_size: bool = True,
        threads: int = -1,
        plane_weight_coronal: float | None = None,
        plane_weight_axial: float | None = None,
        plane_weight_sagittal: float | None = None,
        skip_wm_correction: bool = False,
        fixv1: bool = False,
        tpl_t1w: str | None = None,
        tpl_wm: str | None = None,
        **kwargs,
) -> Literal[0] | str:
    """
    Prepare a subject for FreeSurfer surface reconstruction.
    
    Runs the complete pipeline:
    1. Conforms input image
    2. Runs segmentation prediction
    3. Optionally applies V1 WM fixing
    4. Creates aseg and brain mask files
    
    Parameters
    ----------
    orig_name : Path | str
        Path to input T1 image
    output_dir : Path
        Output subject directory (FreeSurfer structure)
    pred_name : str
        Relative path for prediction file
    ckpt_ax, ckpt_sag, ckpt_cor : Path | None
        Checkpoint paths for each plane
    fixv1 : bool
        Apply V1 white matter correction
    skip_wm_correction : bool
        Skip WM island correction during prediction
    
    Returns
    -------
    Literal[0] | str
        0 on success, error message on failure
    """
    if kwargs:
        LOGGER.warning(f"Unknown arguments: {list(kwargs.keys())}")

    # Validate inputs
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)
    if fixv1:
        _validate_v1_templates(tpl_t1w, tpl_wm)
    
    # Log plane configuration
    provided_planes = [p for ckpt, p in [(ckpt_ax, "axial"), (ckpt_cor, "coronal"), (ckpt_sag, "sagittal")] if ckpt]
    LOGGER.info(f"Running inference with {len(provided_planes)} plane(s): {', '.join(provided_planes)}")

    # Set up QC logging
    qc_file_handle = None
    if qc_log:
        try:
            qc_file_handle = open(qc_log, "w")
        except (NotADirectoryError, FileNotFoundError):
            LOGGER.warning("QC log directory does not exist. QC log will not be saved.")

    try:
        # Download checkpoints if needed
        LOGGER.info("Checking or downloading checkpoints...")
        urls = get_paths_from_yaml("url", filename=CHECKPOINT_PATHS_FILE)
        get_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag, urls=urls)
        
        # Extract atlas information from checkpoints
        atlas_name, atlas_metadata = setup_atlas_from_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)

        # Update pred_name to include atlas name
        if pred_name == "mri/aparc+aseg.orig.mgz":
            pred_name = f"mri/aparc.{atlas_name}atlas+aseg.orig.mgz"
            LOGGER.info(f"Updated output filename to: {pred_name}")

        # Prepare subject directory
        subject_dir = Path(output_dir).resolve()
        subject_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info(f"Subject directory: {subject_dir}")

        # Step 1: Conform and save orig.mgz
        LOGGER.info("=" * 80)
        LOGGER.info("Step 1: Conforming input image to FreeSurfer standard space")
        LOGGER.info("=" * 80)
        orig_mgz = _conform_and_save_orig_mgz(
            input_image=orig_name,
            output_dir=subject_dir,
            vox_size=vox_size,
            orientation=orientation,
            image_size=image_size,
        )

        # Step 2: Run skullstripping on conformed image
        LOGGER.info("=" * 80)
        LOGGER.info("Step 2: Running skullstripping on conformed image")
        LOGGER.info("=" * 80)
        mask_path = subject_dir / "mri" / "mask.mgz"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert device to device_id format for skullstripping
        if device == "auto":
            device_id = "auto"
        elif device == "cpu":
            device_id = -1
        else:
            # Extract GPU index from "cuda:0" format
            device_id = int(device.split(":")[-1]) if ":" in device else 0
        
        skullstripping_config = {
            'atlas': atlas_name,
            'batch_size': batch_size,
            'threads': threads if threads > 0 else 1,
        }
        # Only add preprocessing params if not defaults
        if vox_size != "min":
            skullstripping_config['vox_size'] = vox_size
        if orientation != "lia":
            skullstripping_config['orientation'] = orientation
        if image_size is not True:
            skullstripping_config['image_size'] = image_size
        # Add plane weights to config if provided
        if plane_weight_coronal is not None:
            skullstripping_config['plane_weight_coronal'] = plane_weight_coronal
        if plane_weight_axial is not None:
            skullstripping_config['plane_weight_axial'] = plane_weight_axial
        if plane_weight_sagittal is not None:
            skullstripping_config['plane_weight_sagittal'] = plane_weight_sagittal
        
        # Create temporary directory for skullstripping outputs
        temp_skull_dir = Path(tempfile.mkdtemp(prefix="fastsurfer_skull_"))
        try:
            skullstrip_fastsurfercnn(
                input_image=str(orig_mgz),
                modal="anat",  # Always anat for T1w
                output_dir=temp_skull_dir,
                device_id=device_id,
                logger=LOGGER,
                config=skullstripping_config,
                plane_weight_coronal=plane_weight_coronal,
                plane_weight_axial=plane_weight_axial,
                plane_weight_sagittal=plane_weight_sagittal,
            )
            # Copy mask from temp directory to final location
            temp_mask = temp_skull_dir / "mask.mgz"
            if temp_mask.exists():
                shutil.copy2(temp_mask, mask_path)
            else:
                # Try .nii.gz format
                temp_mask = temp_skull_dir / "mask.nii.gz"
                if temp_mask.exists():
                    # Convert to .mgz if needed
                    img = nib.load(temp_mask)
                    nib.save(img, mask_path)
                else:
                    raise FileNotFoundError(f"Mask not found in {temp_skull_dir}")
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_skull_dir)
            except Exception as e:
                LOGGER.warning(f"Could not clean up temporary skullstripping directory {temp_skull_dir}: {e}")
        LOGGER.info(f"Brain mask saved: {mask_path}")

        # Step 3: Run segmentation on conformed image
        LOGGER.info("=" * 80)
        LOGGER.info("Step 3: Running segmentation on conformed image")
        LOGGER.info("=" * 80)
        
        # Create temporary directory for segmentation outputs
        temp_seg_dir = Path(tempfile.mkdtemp(prefix="fastsurfer_seg_"))
        
        try:
            # Run segmentation (will create seg, mask, hemimask)
            seg_results = run_segmentation(
                input_image=str(orig_mgz),
                output_dir=temp_seg_dir,
                atlas_name=atlas_name,
                atlas_metadata=atlas_metadata,
                ckpt_ax=ckpt_ax,
                ckpt_cor=ckpt_cor,
                ckpt_sag=ckpt_sag,
                device=device,
                viewagg_device=viewagg_device,
                threads=threads if threads > 0 else 1,
                batch_size=batch_size,
                plane_weight_coronal=plane_weight_coronal,
                plane_weight_axial=plane_weight_axial,
                plane_weight_sagittal=plane_weight_sagittal,
                fix_wm_islands=not skip_wm_correction,
            )
            
            # Step 4: Reorganize outputs to FS structure
            LOGGER.info("=" * 80)
            LOGGER.info("Step 4: Reorganizing outputs to FreeSurfer structure")
            LOGGER.info("=" * 80)
            
            mri_dir = subject_dir / "mri"
            mri_dir.mkdir(parents=True, exist_ok=True)
            
            # Move segmentation to FS structure
            seg_file = mri_dir / pred_name
            seg_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seg_results['segmentation'], seg_file)
            LOGGER.info(f"Segmentation saved: {seg_file}")
            
            # Copy mask (overwrite the one from skullstripping with the one from segmentation)
            shutil.copy2(seg_results['mask'], mask_path)
            LOGGER.info(f"Brain mask saved: {mask_path}")
            
            # Copy hemisphere mask if available
            if 'hemimask' in seg_results:
                hemi_mask_path = mri_dir / "mask_hemi.mgz"
                shutil.copy2(seg_results['hemimask'], hemi_mask_path)
                LOGGER.info(f"Hemisphere mask saved: {hemi_mask_path}")
            
            # Get LUT path for aseg creation
            fastsurfercnn_dir = Path(__file__).resolve().parent.parent
            atlas_dir = fastsurfercnn_dir / f"atlas/atlas-{atlas_name}"
            lut_path = atlas_dir / f"{atlas_name}_ColorLUT.tsv"
            
            # Apply V1 WM fixing if requested
            if fixv1:
                LOGGER.info("=" * 80)
                LOGGER.info("Step 5: Applying V1 white matter correction")
                LOGGER.info("=" * 80)
                apply_v1_wm_fixing(
                    seg_file=seg_file,
                    output_dir=subject_dir,
                    lut_path=lut_path,
                    tpl_t1w=tpl_t1w,
                    tpl_wm=tpl_wm,
                )

            # Create aseg
            LOGGER.info("=" * 80)
            LOGGER.info("Step 6: Creating aseg file")
            LOGGER.info("=" * 80)
            create_aseg(
                seg_file=seg_file,
                output_dir=subject_dir,
                lut_path=lut_path,
            )

            # Run QC statistics
            LOGGER.info("Computing segmentation volume statistics...")
            conformed_img = nib.load(orig_mgz)
            pred_img = nib.load(seg_file)
            pred_data = np.asarray(pred_img.dataobj)
            seg_voxvol = np.prod(conformed_img.header.get_zooms())
            check_volume(pred_data, seg_voxvol)
            
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_seg_dir)
                LOGGER.debug(f"Cleaned up temporary directory: {temp_seg_dir}")
            except Exception as e:
                LOGGER.warning(f"Could not clean up temporary directory {temp_seg_dir}: {e}")
            
    except RuntimeError as e:
        if not handle_cuda_memory_exception(e):
            return e.args[0]
    finally:
        if qc_file_handle is not None:
            qc_file_handle.close()

    return 0


def make_parser():
    """Create argument parser for FreeSurfer preparation."""
    parser = argparse.ArgumentParser(
        description="FastSurfer FreeSurfer preparation - conform, segment, and prepare for surface reconstruction"
    )

    # Input/output
    parser = parser_defaults.add_arguments(parser, ["t1"])
    parser.add_argument(
        "--output_dir",
        type=Path,
        required=True,
        help="Output subject directory (FreeSurfer structure)"
    )
    parser = parser_defaults.add_arguments(
        parser,
        ["conformed_name", "aseg_name", "seg_log", "qc_log"],
    )

    # Checkpoints (optional - user can specify 1, 2, or 3 planes)
    files: dict[Plane, str | Path | None] = {k: None for k in PLANES}
    parser = parser_defaults.add_plane_flags(parser, "checkpoint", files, CHECKPOINT_PATHS_FILE)

    # Technical parameters
    parser = parser_defaults.add_arguments(
        parser,
        ["vox_size", "orientation", "image_size",
         "device", "viewagg_device", "batch_size", "async_io", "threads"]
    )
    
    # Multi-view prediction weights
    parser.add_argument(
        "--plane_weight_coronal",
        type=float,
        default=None,
        help="Weight for coronal plane in multi-view prediction (default: 0.4)",
    )
    parser.add_argument(
        "--plane_weight_axial",
        type=float,
        default=None,
        help="Weight for axial plane in multi-view prediction (default: 0.4)",
    )
    parser.add_argument(
        "--plane_weight_sagittal",
        type=float,
        default=None,
        help="Weight for sagittal plane in multi-view prediction (default: 0.2)",
    )
    
    # Post-processing
    parser.add_argument(
        "--no_wm_island_correction",
        dest="skip_wm_correction",
        action="store_true",
        help="Skip WM island correction during segmentation. By default, WM island "
             "correction is enabled to fix occasional CNN mislabeling.",
    )
    
    # V1 WM fixing
    parser.add_argument(
        "--fixv1",
        action="store_true",
        help="Fix missing thin WM in V1 using template registration",
    )
    parser.add_argument(
        "--tpl_t1w",
        default=str(FASTSURFER_ROOT / "FastSurferCNN/atlas/template/tpl-NMT2Sym_res-05_T1w_brain_V1.nii.gz"),
        help="Path to template T1w image for V1 fixing",
    )
    parser.add_argument(
        "--tpl_wm",
        default=str(FASTSURFER_ROOT / "FastSurferCNN/atlas/template/atlas-ARM_level-2_space-NMT2Sym_res-05_calcarine_WM.nii.gz"),
        help="Path to template WM probability map for V1 fixing",
    )
    
    return parser


def main(**kwargs) -> Literal[0] | str:
    """
    Main entry point for FreeSurfer preparation.
    
    Resolves output directory path and delegates to prepare_freesurfer_subject.
    """
    # Resolve output directory
    output_dir = Path(kwargs['output_dir']).resolve()
    kwargs['output_dir'] = output_dir
    
    LOGGER.info("=" * 80)
    LOGGER.info("FastSurfer FreeSurfer Preparation")
    LOGGER.info(f"Output directory: {output_dir}")
    LOGGER.info("=" * 80)
    
    return prepare_freesurfer_subject(**kwargs)


if __name__ == "__main__":
    parser = make_parser()
    _args = parser.parse_args()

    # Set up logging
    setup_logging(_args.log_name)

    # Remove log_name from args before passing to main (it's only used for logging setup)
    main_args = vars(_args)
    main_args.pop("log_name", None)

    sys.exit(main(**main_args))

