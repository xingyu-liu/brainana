# %%
"""Run ANTs registration via ants_register (auto-runs FireANTs with GPU when available, else ANTs CPU)."""
import os
import sys
from pathlib import Path

# Add src/ to path for nhp_mri_prep package (scripts/ -> nhp_mri_prep -> src)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from nhp_mri_prep.operations.registration import ants_register
import logging

# %%
moving_f = '/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/T1wT2w/T2w.nii.gz'
fixed_f = '/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/T1wT2w/T1w.nii.gz'

method = 'ants'
xfm_type = 'rigid'

# %%
# Set up working directory and output prefix (ants_register auto-runs FireANTs with GPU when available)
working_dir = os.path.join(os.path.dirname(fixed_f), 'registration')
os.makedirs(working_dir, exist_ok=True)
output_prefix = f"{os.path.basename(moving_f).split('.nii')[0]}_{xfm_type}"

# setup logging so that it prints to the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Running ANTs registration:")
logger.info(f"  Moving image: {moving_f}")
logger.info(f"  Fixed image: {fixed_f}")
logger.info(f"  Working directory: {working_dir}")
logger.info(f"  Output prefix: {output_prefix}")
logger.info(f"  XFM type: {xfm_type}")

# Run ANTs registration
if method == 'ants':
    results = ants_register(
        fixedf=fixed_f,
        movingf=moving_f,
        working_dir=working_dir,
        output_prefix=output_prefix,
        xfm_type=xfm_type,
        compute_inverse=True,
        logger=logger
    )
