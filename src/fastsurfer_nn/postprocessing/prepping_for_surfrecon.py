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
        pred_img.header.copy(), pred_img.affine, aseg, aseg_path, dtype=aseg_dtype
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
    atlas_name = lut_path.stem.replace("_ColorLUT", "").replace("ColorLUT", "")
    return atlas_name


def _enhance_arm2_wm_with_arm6(
    arm2_data: np.ndarray,
    arm6_data: np.ndarray,
    wm_keys: tuple[int, ...],
) -> tuple[np.ndarray, dict[int, int]]:
    """
    Enhance ARM2 WM labels from ARM6 using constrained fill behavior.

    ARM6 WM voxels are eligible only if they have at least one 26-neighbor
    voxel in ARM2 labeled 16 or 1016. Eligible voxels are then filled into
    ARM2 only where ARM2 does not already have a tracked WM key.

    Parameters
    ----------
    arm2_data : np.ndarray
        Conformed ARM2 segmentation.
    arm6_data : np.ndarray
        Conformed ARM6 segmentation.
    wm_keys : tuple[int, ...]
        WM label keys to enhance.

    Returns
    -------
    tuple[np.ndarray, dict[int, int]]
        Enhanced ARM2 segmentation and per-label added voxel counts.
    """
    if arm2_data.shape != arm6_data.shape:
        raise ValueError(
            f"ARM2/ARM6 shape mismatch for WM enhancement: "
            f"{arm2_data.shape} vs {arm6_data.shape}"
        )

    enhanced = arm2_data.copy().astype(np.int16, copy=False)
    added_voxels: dict[int, int] = {}

    # Build a 26-neighbor gate from certain ARM2 labels
    arm2_neighbor_labels = (16, 1016, 50, 1050)  #
    neighbor_seed = np.isin(enhanced, arm2_neighbor_labels)
    neighbor_ok = np.zeros_like(neighbor_seed, dtype=bool)
    padded = np.pad(neighbor_seed, 1, mode="constant", constant_values=False)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == 0 and dy == 0 and dz == 0:
                    continue
                neighbor_ok |= padded[
                    1 + dx : 1 + dx + enhanced.shape[0],
                    1 + dy : 1 + dy + enhanced.shape[1],
                    1 + dz : 1 + dz + enhanced.shape[2],
                ]

    # Preserve any existing ARM2 WM assignment. ARM6 can only fill voxels where
    # ARM2 has no WM label from the tracked WM keys.
    arm2_has_any_wm = np.isin(enhanced, wm_keys)

    for wm_key in wm_keys:
        arm6_mask = arm6_data == wm_key
        fill_mask = arm6_mask & neighbor_ok & (~arm2_has_any_wm)
        added_voxels[wm_key] = int(np.count_nonzero(fill_mask))
        enhanced[fill_mask] = wm_key

    return enhanced, added_voxels


def postprocess_for_freesurfer(
    t1w_image: Path | str,
    segmentation: Path | str,
    mask: Path | str,
    lut_path: Path | str,
    subject_dir: Path | str,
    vox_size: VoxSizeOption = "min",
    orientation: OrientationType = "lia",
    arm6_atlas: Path | str | None = None,
) -> Literal[0] | str:
    """
    Post-process segmentation outputs for FreeSurfer surface reconstruction.

    This function takes the outputs from run_segmentation and:
    1. Creates FreeSurfer directory structure
    2. Conforms T1w, mask, and aseg to FreeSurfer format
    3. Saves all files in the correct FreeSurfer locations
    4. Optionally conforms and saves an ARM6 atlas for claustrum fixing

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
    vox_size : VoxSizeOption, default="min"
        Voxel size option for conforming
    orientation : OrientationType, default="lia"
        Target orientation for conforming
    arm6_atlas : Path | str | None, optional
        Path to ARM6 atlas file (native space). If provided and the file exists,
        it will be resampled to conformed space and saved as
        ``mri/aparc.ARM6atlas+aseg.orig.mgz``. The surface reconstruction
        pipeline uses this file to run the claustrum fix after stage s07.

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
    if arm6_atlas is not None:
        arm6_atlas = Path(arm6_atlas)

    # Validate inputs
    for path, name in [
        (t1w_image, "T1w image"),
        (segmentation, "segmentation"),
        (mask, "mask"),
        (lut_path, "LUT"),
    ]:
        if not path.exists():
            return f"Error: {name} not found at {path}"

    # Extract atlas name from LUT path
    atlas_name = _extract_atlas_name_from_lut(lut_path)
    LOGGER.info(f"Detected atlas: {atlas_name}")

    # 1. Create FreeSurfer directory structure
    LOGGER.info("=" * 80)
    LOGGER.info("Step 1: Creating FreeSurfer directory structure")
    LOGGER.info("=" * 80)
    subject_dir = subject_dir.resolve()
    mri_dir = subject_dir / "mri"
    mri_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Subject directory: {subject_dir}")

    # 1: Conform T1w image (defines target space)
    LOGGER.info("=" * 80)
    LOGGER.info("Step 2: Conforming T1w image to FreeSurfer standard space")
    LOGGER.info("=" * 80)
    orig_mgz = mri_dir / "orig.mgz"

    t1w_img = nib.load(t1w_image)

    # Hardcode to 'cube' for FreeSurfer compatibility (cubic images required)
    conform_img_size: int | str = "cube"

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
    LOGGER.info(
        f"DIAGNOSTIC: conformed_t1w.affine.shape = {conformed_t1w.affine.shape}"
    )

    # Save conformed T1w
    data_ultils.save_image(
        conformed_t1w.header.copy(),
        conformed_t1w.affine,
        conformed_t1w_data,
        orig_mgz,
        dtype=np.uint8,
    )
    LOGGER.info(f"Saved conformed T1w: {orig_mgz}")

    # DIAGNOSTIC: Reload saved image to check what was actually saved
    conformed_t1w_reloaded = nib.load(orig_mgz)
    LOGGER.info(
        f"DIAGNOSTIC: After reload - conformed_t1w_reloaded.shape = {conformed_t1w_reloaded.shape}"
    )
    reloaded_data = np.asanyarray(conformed_t1w_reloaded.dataobj)
    LOGGER.info(
        f"DIAGNOSTIC: After reload - reloaded_data.shape = {reloaded_data.shape}"
    )
    # Get target affine and shape from conformed T1w (for resampling other images)
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

    # 3: Resample segmentation and mask to conformed space
    LOGGER.info("=" * 80)
    LOGGER.info("Step 3: Resampling ARM2 segmentation and mask to conformed space")
    LOGGER.info("=" * 80)

    seg_img = nib.load(segmentation)
    mask_img = nib.load(mask)
    LOGGER.info("Resampling segmentation to conformed space...")
    LOGGER.info(
        f"DIAGNOSTIC: seg_img.shape = {seg_img.shape}, target_shape = {target_shape}"
    )
    arm2_resampled = map_image(
        seg_img,
        out_affine=target_affine,
        out_shape=target_shape,
        order=0,  # Nearest neighbor for labels
        dtype=np.int16,
    )
    LOGGER.info(f"DIAGNOSTIC: arm2_resampled.shape = {arm2_resampled.shape}")

    LOGGER.info("Resampling mask to conformed space...")
    LOGGER.info(
        f"DIAGNOSTIC: mask_img.shape = {mask_img.shape}, target_shape = {target_shape}"
    )
    mask_resampled = map_image(
        mask_img,
        out_affine=target_affine,
        out_shape=target_shape,
        order=0,  # Nearest neighbor
        dtype=np.uint8,
    )
    LOGGER.info(f"DIAGNOSTIC: mask_resampled.shape = {mask_resampled.shape}")

    # Step 4: Optionally resample ARM6 and enhance ARM2 WM labels
    LOGGER.info("=" * 80)
    LOGGER.info("Step 4: Optional ARM6 WM enhancement in conformed space")
    LOGGER.info("=" * 80)

    wm_enhance_keys = (-1, -501, -1001, -1501)
    arm2_for_output = arm2_resampled.astype(np.int16, copy=False)
    arm6_resampled: np.ndarray | None = None

    if arm6_atlas is not None:
        if not arm6_atlas.exists():
            LOGGER.warning(
                f"ARM6 atlas not found at {arm6_atlas} — skipping ARM6 WM enhancement"
            )
        else:
            arm6_img = nib.load(arm6_atlas)
            LOGGER.info(f"Resampling ARM6 atlas: {arm6_atlas.name} → conformed space")
            arm6_resampled = map_image(
                arm6_img,
                out_affine=target_affine,
                out_shape=target_shape,
                order=0,  # Nearest neighbor for label image
                dtype=np.int16,
            )
            arm6_resampled[mask_resampled == 0] = 0

            arm2_backup_path = (
                mri_dir / f"aparc.{atlas_name}atlas+aseg.orig.pre_arm6_wm_enhance.mgz"
            )
            data_ultils.save_image(
                conformed_t1w_reloaded.header.copy(),
                target_affine,
                arm2_for_output.astype(np.int16),
                arm2_backup_path,
                dtype=np.int16,
            )
            LOGGER.info(
                f"Saved ARM2 backup before WM enhancement: {arm2_backup_path.name}"
            )

            arm2_for_output, added_voxels = _enhance_arm2_wm_with_arm6(
                arm2_for_output,
                arm6_resampled,
                wm_enhance_keys,
            )
            for wm_key, added_count in added_voxels.items():
                LOGGER.info(
                    f"WM enhancement key {wm_key}: added {added_count} voxels from ARM6 union"
                )

    # Enforce brain mask after optional enhancement
    arm2_for_output[mask_resampled == 0] = 0

    # Step 5: Create aseg from enhanced conformed ARM2
    LOGGER.info("=" * 80)
    LOGGER.info("Step 5: Creating aseg from enhanced conformed ARM2")
    LOGGER.info("=" * 80)
    aseg_resampled = rta.reduce_to_aseg(
        arm2_for_output, lut_path=lut_path, verbose=True
    )
    aseg_resampled[mask_resampled == 0] = 0

    # Step 6: Save all files in FreeSurfer structure
    LOGGER.info("=" * 80)
    LOGGER.info("Step 6: Saving files in FreeSurfer structure")
    LOGGER.info("=" * 80)

    # Save segmentation (both naming conventions)
    seg_file_generic = mri_dir / "aparc+aseg.orig.mgz"
    seg_file_atlas = mri_dir / f"aparc.{atlas_name}atlas+aseg.orig.mgz"

    # Use reloaded conformed image header for consistency
    aseg_dtype = np.int16 if np.any(arm2_for_output < 0) else np.uint8
    LOGGER.info(
        f"DIAGNOSTIC: Saving segmentation with shape {arm2_for_output.shape}, dtype {aseg_dtype}"
    )
    data_ultils.save_image(
        conformed_t1w_reloaded.header.copy(),
        target_affine,
        arm2_for_output.astype(aseg_dtype),
        seg_file_generic,
        dtype=aseg_dtype,
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
        dtype=np.uint8,
    )
    LOGGER.info(f"Saved mask: {mask_path.name}")

    # Save aseg
    aseg_path = mri_dir / "aseg.auto_noCCseg.mgz"
    aseg_dtype = np.int16 if np.any(aseg_resampled < 0) else np.uint8
    LOGGER.info(
        f"DIAGNOSTIC: Saving aseg with shape {aseg_resampled.shape}, dtype {aseg_dtype}"
    )
    data_ultils.save_image(
        conformed_t1w_reloaded.header.copy(),
        target_affine,
        aseg_resampled.astype(aseg_dtype),
        aseg_path,
        dtype=aseg_dtype,
    )
    LOGGER.info(f"Saved aseg: {aseg_path.name}")

    # Save ARM6 conformed export for claustrum fix (if available)
    if arm6_resampled is not None:
        arm6_out = mri_dir / "aparc.ARM6atlas+aseg.orig.mgz"
        data_ultils.save_image(
            conformed_t1w_reloaded.header.copy(),
            target_affine,
            arm6_resampled.astype(np.int16),
            arm6_out,
            dtype=np.int16,
        )
        LOGGER.info(f"Saved ARM6 atlas: {arm6_out.name}")

    # Run QC statistics
    LOGGER.info("Computing segmentation volume statistics...")
    seg_voxvol = np.prod(conformed_t1w.header.get_zooms())
    check_volume(arm2_for_output, seg_voxvol)

    LOGGER.info("=" * 80)
    LOGGER.info("Post-processing completed successfully!")
    LOGGER.info("=" * 80)

    return 0
