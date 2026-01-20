"""
Improve brain masks by applying simple 3D morphological operations.

This script is intended to clean up rough/manual EPI brainmasks by:
  - Binarizing the mask
  - Removing small isolated components
  - Keeping only the largest connected component (or components above a size threshold)
  - Filling internal holes
  - Applying a small closing/opening to smooth the mask

The defaults are conservative and should be reasonably safe, but you may want to
adjust thresholds depending on voxel size and acquisition.
"""

# %%
import logging
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

from FastSurferCNN.postprocessing.postseg_utils import create_mask
from FastSurferCNN.utils.constants import (
    MASK_DILATION_SIZE_MM,
    ROUNDS_OF_MORPHOLOGICAL_OPERATIONS,
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Directory containing input mask volumes
root_dir = Path(
    "/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/test_BC/func"
)

# If set to a relative path (starting with '/'), only that file will be processed,
# using the *same* morphological parameters as the FastSurferCNN `create_mask` pipeline.
# Example (relative to root_dir): "/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI_brainmask_manual.nii.gz"
# If set to None, all *.nii.gz files under root_dir will be processed.
input_f = 'input_mask.nii.gz' 
output_suffix = "_improved"

# If False, existing improved masks are not overwritten
overwrite = True


# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CORE FUNCTIONS
# ============================================================================
def _improve_mask(mask_data: np.ndarray, zooms: tuple[float, float, float]) -> np.ndarray:
    """Apply the same morphological pipeline as `create_mask` with its parameters.

    We compute the dilation/erosion/rounds exactly as in `FastSurferCNN.inference.api.segmentation`,
    i.e. based on `MASK_DILATION_SIZE_MM`, `ROUNDS_OF_MORPHOLOGICAL_OPERATIONS`, and the voxel size.
    """
    # Compute voxel-wise dilation/erosion parameters exactly like in the main API
    resolution = float(np.mean(zooms[:3]))
    dnum = int(MASK_DILATION_SIZE_MM / resolution)
    enum = 0

    if dnum <= 0 and enum <= 0:
        # Degenerate case: just binarize
        return (mask_data != 0).astype(np.uint8)

    mask = create_mask(
        seg_data=(mask_data != 0).astype(int),
        dnum=dnum,
        enum=enum,
        rounds=ROUNDS_OF_MORPHOLOGICAL_OPERATIONS,
        voxel_size=zooms[:3],  # Pass voxel size for volume calculation
    )

    return mask.astype(np.uint8)


def process_mask_file(mask_path: Path) -> None:
    """Load a mask, improve it, and save to a new file."""
    if not mask_path.exists():
        logger.warning(f"Mask not found, skipping: {mask_path}")
        return

    if mask_path.suffixes[-2:] == [".nii", ".gz"]:
        stem = mask_path.name.replace(".nii.gz", "")
        out_name = f"{stem}{output_suffix}.nii.gz"
    else:
        # Fallback for unusual extensions
        out_name = mask_path.name + output_suffix

    out_path = mask_path.parent / out_name

    if out_path.exists() and not overwrite:
        logger.info(f"Output exists, skipping: {out_path.name}")
        return

    logger.info(f"Processing mask: {mask_path.name}")

    img = nib.load(str(mask_path))
    data = img.get_fdata()
    zooms = img.header.get_zooms()[:3]

    improved = _improve_mask(data, zooms)

    # Preserve affine and header as much as possible
    new_img = nib.Nifti1Image(improved, affine=img.affine, header=img.header)
    # Ensure data type is uint8
    new_img.set_data_dtype(np.uint8)

    nib.save(new_img, str(out_path))
    logger.info(f"Saved improved mask -> {out_path.name}")


def main() -> None:
    if not root_dir.exists():
        logger.error(f"Root directory does not exist: {root_dir}")
        return

    # Decide which files to process
    if input_f:
        # Treat input_f as path relative to root_dir (strip leading '/')
        rel = input_f.lstrip("/")
        mask_paths = [root_dir / rel]
    else:
        mask_paths = sorted(root_dir.glob("*.nii.gz"))

    if not mask_paths:
        logger.warning(f"No mask files found in: {root_dir}")
        return

    logger.info(f"Found {len(mask_paths)} mask file(s) to process")

    for mask_path in mask_paths:
        process_mask_file(mask_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()
