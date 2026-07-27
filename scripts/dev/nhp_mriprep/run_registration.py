# %%
"""Run ANTs registration via ants_register (auto-runs FireANTs with GPU when available, else ANTs CPU)."""
import logging
import os
import sys
from pathlib import Path

# Add src/ to path (scripts/dev/nhp_mriprep/ -> scripts/dev/ -> scripts/ -> repo root)
_src = Path(__file__).resolve().parents[3] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from nhp_mri_prep.operations.registration import ants_register

# %%
fixed_f = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/input_T2w/fixed_newcastle.nii.gz"
)
moving_f = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/input_T2w/moving_newcastle.nii.gz"
)
working_dir = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/test_T2w"
)

method = "ants"
xfm_type = "translation"
enable_fireants = True

# %%
# Set up working directory and output prefix (ants_register auto-runs FireANTs with GPU when available)
os.makedirs(working_dir, exist_ok=True)
output_prefix = f"{os.path.basename(moving_f).split('.nii')[0]}_{xfm_type}"

# setup logging so that it prints to the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Running ANTs registration:")
logger.info(f"  Moving image: {moving_f}")
logger.info(f"  Fixed image: {fixed_f}")
logger.info(f"  Working directory: {working_dir}")
logger.info(f"  Output prefix: {output_prefix}")
logger.info(f"  XFM type: {xfm_type}")

# Run ANTs registration
if method == "ants":
    results = ants_register(
        fixedf=fixed_f,
        movingf=moving_f,
        working_dir=working_dir,
        output_prefix=output_prefix,
        xfm_type=xfm_type,
        compute_inverse=True,
        enable_fireants=enable_fireants,
        logger=logger,
    )
