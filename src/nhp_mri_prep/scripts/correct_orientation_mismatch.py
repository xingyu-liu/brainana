"""
Simple script to correct orientation mismatch in MRI images.

This script corrects the orientation mismatch by updating the affine matrix
based on the actual physical orientation of the axes.
"""
# %%
import sys
import logging
from pathlib import Path
import os

# Add src/ to path for nhp_mri_prep imports (scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.operations.preprocessing import correct_orientation_mismatch
from nhp_mri_prep.utils import get_logger, setup_logging

# %%
# Configuration
# input_f = '/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_reorient/sub-baby31/ses-240710/anat/sub-baby31_ses-240710_run-5_T1w.nii.gz'
# real_A_is_actually_labeled_as = "L"
# real_P_is_actually_labeled_as = "R"
# real_S_is_actually_labeled_as = "S"
# real_I_is_actually_labeled_as = "I"

input_f = '/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_reorient/sub-baby31/ses-240710/func/sub-baby31_ses-240710_run-2_bold.nii.gz'
real_A_is_actually_labeled_as = "I"
real_P_is_actually_labeled_as = "S"
real_S_is_actually_labeled_as = "A"
real_I_is_actually_labeled_as = "P"

# # princeton
# input_f = '/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/test_orient/sub-freddie_T1w.nii.gz'
# real_A_is_actually_labeled_as = "S"
# real_P_is_actually_labeled_as = "I"
# real_S_is_actually_labeled_as = "A"
# real_I_is_actually_labeled_as = "P"

# 
output_f = input_f.replace(".nii.gz", "_ortcorrected.nii.gz")

# %%
# Setup logging
setup_logging(level=logging.INFO)
logger = get_logger(__name__)

# Validate input file exists
input_path = Path(input_f)
if not input_path.exists():
    raise FileNotFoundError(f"Input file does not exist: {input_f}")

# Create output directory if it doesn't exist
output_path = Path(output_f)
output_path.parent.mkdir(parents=True, exist_ok=True)

# Create working directory (use output directory)
working_dir = output_path.parent
output_name = output_path.name

# Create config dictionary
config = {
    "orientation_mismatch_correction": {
        "enabled": True,
        "real_A_is_actually_labeled_as": real_A_is_actually_labeled_as,
        "real_P_is_actually_labeled_as": real_P_is_actually_labeled_as,
        "real_S_is_actually_labeled_as": real_S_is_actually_labeled_as,
        "real_I_is_actually_labeled_as": real_I_is_actually_labeled_as,
    }
}

# Perform orientation mismatch correction
logger.info(f"Starting orientation mismatch correction")
logger.info(f"Input: {input_f}")
logger.info(f"Output: {output_f}")
logger.info(f"real_A_is_actually_labeled_as: {real_A_is_actually_labeled_as}")
logger.info(f"real_S_is_actually_labeled_as: {real_S_is_actually_labeled_as}")

outputs = correct_orientation_mismatch(
    imagef=str(input_path),
    working_dir=str(working_dir),
    output_name=output_name,
    logger=logger,
    config=config,
    generate_tmean=False
)

if outputs.get("imagef_orientation_corrected"):
    logger.info(f"Successfully corrected orientation: {outputs['imagef_orientation_corrected']}")
    # If the output path is different from what was created, move it
    corrected_path = Path(outputs["imagef_orientation_corrected"])
    if corrected_path != output_path:
        import shutil
        shutil.move(str(corrected_path), str(output_path))
        logger.info(f"Moved output to: {output_path}")
else:
    logger.info("Orientation mismatch correction was skipped (orientation already correct)")
    # If correction was skipped, just copy the input to output
    import shutil
    shutil.copy2(str(input_path), str(output_path))
    logger.info(f"Copied input to output: {output_path}")

logger.info("Orientation mismatch correction completed successfully")

# %%
output_f = input_f.replace(".nii.gz", "_ortcorrected.nii.gz")